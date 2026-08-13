using System;
using System.IO;
using System.Linq;
using Mono.Cecil;
using Mono.Cecil.Cil;

// Bastion ultrawide patcher.
// Applies all IL + resolution-table edits needed to run Bastion at an ultrawide
// (e.g. 5120x1440 / 32:9) with full-width gameplay, a correctly-sized HUD/menus/
// subtitles centered in a 16:9 band, and a full-width parallax backdrop.
//
// The IL edits are RESOLUTION-INDEPENDENT (they derive from SCREEN_WIDTH/HEIGHT at
// runtime, using the game's own 1920x1080 design base). Only the resolution-TABLE
// entry is resolution-specific: we repurpose the stock 1920x1200 slot to W x H so
// it appears in Options > Video.
//
// Usage:
//   dotnet run -- --exe "C:\Games\Solo\Bastion\Bastion.exe" --width 5120 --height 1440
//
// Idempotent: on every run it restores from <exe>.orig-backup (created on first run,
// assumed to be stock) before applying, so re-running never double-applies offsets.

class Program
{
    const int DESIGN_W = 1920;   // game's 16:9 design width  (do not change)
    const int DESIGN_H = 1080;   // game's 16:9 design height (do not change)

    static int Main(string[] args)
    {
        string exe = GetArg(args, "--exe", @"C:\Games\Solo\Bastion\Bastion.exe");
        int width  = int.Parse(GetArg(args, "--width", "5120"));
        int height = int.Parse(GetArg(args, "--height", "1440"));
        bool bakeWindowed = !args.Contains("--keep-fullscreen"); // bake in borderless windowed by default

        if (!File.Exists(exe)) { Console.Error.WriteLine($"exe not found: {exe}"); return 1; }

        string orig = exe + ".orig-backup";
        if (!File.Exists(orig))
        {
            File.Copy(exe, orig);
            Console.WriteLine($"Created stock backup: {orig}");
        }
        else
        {
            File.Copy(orig, exe, overwrite: true);
            Console.WriteLine("Restored stock exe from backup (clean base for idempotent re-run).");
        }

        // ---- IL edits via Cecil ----
        var asm = AssemblyDefinition.ReadAssembly(exe, new ReaderParameters { InMemory = true, ReadingMode = ReadingMode.Immediate });
        var module = asm.MainModule;

        PatchViewport(module);
        PatchScale(module);
        PatchCenter(module, "setScaledLocation", instanceLocationField: true);
        PatchCenter(module, "getScaledLocation", instanceLocationField: false);
        PatchBackdrop(module);
        if (bakeWindowed) PatchWindowed(module);

        asm.Write(exe);
        Console.WriteLine("IL patches written.");

        // ---- Resolution table (raw bytes, after Cecil save) ----
        PatchResolutionTable(exe, width, height);

        Console.WriteLine($"\nDone. Bastion patched for {width}x{height}. Select it in Options > Video.");
        return 0;
    }

    // 1) setLetterBoxViewports(width,height): make m_viewport == m_fullViewport == full screen.
    //    Original derived a 16:9 box from WIDTH (Height = width*1080/1920), which at 32:9 is
    //    taller than the screen and crops the HUD. Full-screen viewport fixes the crop and
    //    gives full-width (hor+) gameplay.
    static void PatchViewport(ModuleDefinition module)
    {
        var app = module.Types.First(t => t.FullName == "GSGE.App");
        var m = app.Methods.First(x => x.Name == "setLetterBoxViewports");
        FieldReference fFull = null, fView = null; MethodReference setX = null, setY = null, setW = null, setH = null;
        foreach (var il in m.Body.Instructions)
        {
            if (il.Operand is FieldReference fr) { if (fr.Name == "m_fullViewport") fFull = fr; if (fr.Name == "m_viewport") fView = fr; }
            if (il.Operand is MethodReference mr) { if (mr.Name == "set_X") setX = mr; if (mr.Name == "set_Y") setY = mr; if (mr.Name == "set_Width") setW = mr; if (mr.Name == "set_Height") setH = mr; }
        }
        var b = m.Body; b.Instructions.Clear(); b.Variables.Clear(); b.ExceptionHandlers.Clear();
        var p = b.GetILProcessor();
        void SetInt(FieldReference fld, MethodReference setter, Instruction val)
        {
            p.Append(Instruction.Create(OpCodes.Ldarg_0));
            p.Append(Instruction.Create(OpCodes.Ldflda, fld));
            p.Append(val);
            p.Append(Instruction.Create(OpCodes.Call, setter));
        }
        foreach (var fld in new[] { fFull, fView })
        {
            SetInt(fld, setX, Instruction.Create(OpCodes.Ldc_I4_0));
            SetInt(fld, setY, Instruction.Create(OpCodes.Ldc_I4_0));
            SetInt(fld, setW, Instruction.Create(OpCodes.Ldarg_1)); // width
            SetInt(fld, setH, Instruction.Create(OpCodes.Ldarg_2)); // height
        }
        p.Append(Instruction.Create(OpCodes.Ret));
        Console.WriteLine("  [1] setLetterBoxViewports -> full screen");
    }

    // 2) getResolutionScale(): SCREEN_WIDTH/1920 -> SCREEN_HEIGHT/1080 (height-based).
    //    Width-based scaling inflated the UI by (ultrawide width / 1920). Height-based is
    //    identical on any 16:9 display; only differs on non-16:9, giving correct UI size.
    static void PatchScale(ModuleDefinition module)
    {
        var gui = module.Types.First(t => t.FullName == "GSGE.Code.GUI.GUIConstants");
        var m = gui.Methods.First(x => x.Name == "getResolutionScale");
        var fHeight = gui.Fields.First(f => f.Name == "SCREEN_HEIGHT");
        int changed = 0;
        foreach (var il in m.Body.Instructions)
        {
            if (il.OpCode == OpCodes.Ldsfld && il.Operand is FieldReference fr && fr.Name == "SCREEN_WIDTH") { il.Operand = fHeight; changed++; }
            if (il.OpCode == OpCodes.Ldc_R4 && il.Operand is float f && f == (float)DESIGN_W) { il.Operand = (float)DESIGN_H; changed++; }
        }
        if (changed != 2) throw new Exception($"getResolutionScale: expected 2 edits, made {changed}");
        Console.WriteLine("  [2] getResolutionScale -> SCREEN_HEIGHT/1080");
    }

    // 3+4) Horizontal centering: X += (SCREEN_WIDTH - scale*1920) * 0.5.
    //    The two methods below map design coords -> screen and only ever adjusted Y (flush).
    //    We add the mirror-image X centering so the 1920-wide UI design space is centered
    //    within the real screen width. Must be inserted AFTER the X assignment and BEFORE the
    //    flush branch (getScaledLocation's flush==2 path branches straight to the return and
    //    would otherwise skip the offset -- this bit us with subtitles).
    static void PatchCenter(ModuleDefinition module, string methodName, bool instanceLocationField)
    {
        var gc = module.Types.First(t => t.FullName == "GSGE.GUIComponent");
        var gui = module.Types.First(t => t.FullName == "GSGE.Code.GUI.GUIConstants");
        var fWidth = gui.Fields.First(f => f.Name == "SCREEN_WIDTH");

        MethodDefinition m; Instruction loadScale; FieldReference locField = null;
        if (instanceLocationField)
        {
            // setScaledLocation(float x, float y, Flush flush): writes instance field m_location.
            m = gc.Methods.First(x => x.Name == methodName && x.Parameters.Count == 3
                && x.Parameters[0].ParameterType.Name == "Single" && x.Parameters[2].ParameterType.Name == "Flush");
            locField = m.Body.Instructions.First(il => il.Operand is FieldReference fr && fr.Name == "m_location").Operand as FieldReference;
            loadScale = Instruction.Create(OpCodes.Ldloc_0); // local V_0 = getResolutionScale()
        }
        else
        {
            // getScaledLocation(float x, float y, Flush flush, float xScale): builds local V_0.
            m = gc.Methods.First(x => x.Name == methodName && x.Parameters.Count == 4);
            loadScale = Instruction.Create(OpCodes.Ldarg, m.Parameters[3]); // xScale
        }

        var vecX = m.Body.Instructions.First(il => il.Operand is FieldReference fr && fr.Name == "X" && fr.DeclaringType.Name == "Vector2").Operand as FieldReference;
        var xset = m.Body.Instructions.First(il => il.OpCode == OpCodes.Stfld && il.Operand is FieldReference fr && fr.Name == "X" && fr.DeclaringType.Name == "Vector2");
        var p = m.Body.GetILProcessor();

        // Load the address of the vector we are modifying (instance field vs local V_0).
        Instruction ldAddr1, ldAddr2;
        if (instanceLocationField) { ldAddr1 = Instruction.Create(OpCodes.Ldarg_0); ldAddr2 = Instruction.Create(OpCodes.Ldflda, locField); }
        else { ldAddr1 = Instruction.Create(OpCodes.Ldloca_S, m.Body.Variables[0]); ldAddr2 = null; }

        var seq = new System.Collections.Generic.List<Instruction>();
        seq.Add(ldAddr1);
        if (ldAddr2 != null) seq.Add(ldAddr2);
        seq.Add(Instruction.Create(OpCodes.Dup));
        seq.Add(Instruction.Create(OpCodes.Ldfld, vecX));
        seq.Add(Instruction.Create(OpCodes.Ldsfld, fWidth));
        seq.Add(Instruction.Create(OpCodes.Conv_R4));
        seq.Add(loadScale);
        seq.Add(Instruction.Create(OpCodes.Ldc_R4, (float)DESIGN_W));
        seq.Add(Instruction.Create(OpCodes.Mul));
        seq.Add(Instruction.Create(OpCodes.Sub));
        seq.Add(Instruction.Create(OpCodes.Ldc_R4, 0.5f));
        seq.Add(Instruction.Create(OpCodes.Mul));
        seq.Add(Instruction.Create(OpCodes.Add));
        seq.Add(Instruction.Create(OpCodes.Stfld, vecX));

        var cursor = xset;
        foreach (var ins in seq) { p.InsertAfter(cursor, ins); cursor = ins; }
        Console.WriteLine($"  [{(instanceLocationField ? "3" : "4")}] {methodName} -> +horizontal centering");
    }

    // 5) drawBackdrop: BackdropScale uses getResolutionScale() (now height-based) so the
    //    parallax backdrop only covered a 16:9 slice. Replace that call with an inline
    //    SCREEN_WIDTH/1920 (width-based) so the backdrop fills the full width again.
    //    NOTE: GSGE.Code.Things.Flyer::getDrawScale() also calls getResolutionScale() and is
    //    left height-based on purpose (the drifting background "flyers" weren't visibly wrong).
    //    If they ever look mis-scaled, apply this same width-based swap there.
    static void PatchBackdrop(ModuleDefinition module)
    {
        var mb = module.Types.First(t => t.FullName == "GSGE.MapBackground");
        var m = mb.Methods.First(x => x.Name == "drawBackdrop");
        var gui = module.Types.First(t => t.FullName == "GSGE.Code.GUI.GUIConstants");
        var fWidth = gui.Fields.First(f => f.Name == "SCREEN_WIDTH");
        var calls = m.Body.Instructions.Where(il => il.OpCode == OpCodes.Call && il.Operand is MethodReference mr && mr.Name == "getResolutionScale").ToList();
        if (calls.Count != 1) throw new Exception($"drawBackdrop: expected 1 getResolutionScale call, found {calls.Count}");
        var p = m.Body.GetILProcessor();
        var first = Instruction.Create(OpCodes.Ldsfld, fWidth);
        p.Replace(calls[0], first);
        var conv = Instruction.Create(OpCodes.Conv_R4);
        var ld = Instruction.Create(OpCodes.Ldc_R4, (float)DESIGN_W);
        var div = Instruction.Create(OpCodes.Div);
        p.InsertAfter(first, conv); p.InsertAfter(conv, ld); p.InsertAfter(ld, div);
        Console.WriteLine("  [5] drawBackdrop -> width-based scale (SCREEN_WIDTH/1920)");
    }

    // 7) Bake in borderless windowed: force m_commandLineWindowed and m_commandLineNoBorder
    //    true at the start of App::Main, exactly as if launched with "-windowed -noborder".
    //    The arg-parse loop only ever sets these flags true (never false), so setting them
    //    true up front can't be undone. Removes the need for a launcher .bat / Steam launch
    //    options. Pass --keep-fullscreen to skip this and leave the game's default mode.
    static void PatchWindowed(ModuleDefinition module)
    {
        var app = module.Types.First(t => t.FullName == "GSGE.App");
        var m = app.Methods.First(x => x.Name == "Main");
        var fWin = m.Body.Instructions.First(il => il.Operand is FieldReference fr && fr.Name == "m_commandLineWindowed").Operand as FieldReference;
        var fBorder = m.Body.Instructions.First(il => il.Operand is FieldReference fr && fr.Name == "m_commandLineNoBorder").Operand as FieldReference;
        var p = m.Body.GetILProcessor();
        var first = m.Body.Instructions[0];
        foreach (var ins in new[]
        {
            Instruction.Create(OpCodes.Ldc_I4_1), Instruction.Create(OpCodes.Stsfld, fWin),
            Instruction.Create(OpCodes.Ldc_I4_1), Instruction.Create(OpCodes.Stsfld, fBorder),
        }) p.InsertBefore(first, ins);
        Console.WriteLine("  [7] Main -> force borderless windowed (-windowed -noborder)");
    }

    // 6) Resolution table (raw bytes). Two parallel int32 arrays (widths then heights) of the
    //    stock resolutions. We repurpose the last stock slot (1920x1200) -> width x height so it
    //    shows up in Options > Video without removing 1920x1080.
    static void PatchResolutionTable(string exe, int width, int height)
    {
        byte[] b = File.ReadAllBytes(exe);
        // stock widths:  1024,1280,1366,1440,1600,1600,1680,1920,1920
        byte[] widths = Ints(1024, 1280, 1366, 1440, 1600, 1600, 1680, 1920, 1920);
        // stock heights:  768,1024, 768, 900, 900,1200,1050,1080,1200
        byte[] heights = Ints(768, 1024, 768, 900, 900, 1200, 1050, 1080, 1200);
        int wi = Find(b, widths); int hi = Find(b, heights);
        if (wi < 0 || hi < 0) throw new Exception("resolution table not found (game version mismatch?)");
        // idx8 (the 1920x1200 slot) is the 9th int -> offset +32 within each array.
        WriteInt(b, wi + 32, width);
        WriteInt(b, hi + 32, height);
        File.WriteAllBytes(exe, b);
        Console.WriteLine($"  [6] resolution table: 1920x1200 slot -> {width}x{height}");
    }

    // ---- helpers ----
    static string GetArg(string[] a, string k, string def)
    { int i = Array.IndexOf(a, k); return (i >= 0 && i + 1 < a.Length) ? a[i + 1] : def; }
    static byte[] Ints(params int[] v)
    { var o = new byte[v.Length * 4]; for (int i = 0; i < v.Length; i++) BitConverter.GetBytes(v[i]).CopyTo(o, i * 4); return o; }
    static void WriteInt(byte[] b, int off, int val) => BitConverter.GetBytes(val).CopyTo(b, off);
    static int Find(byte[] hay, byte[] needle)
    {
        for (int i = 0; i <= hay.Length - needle.Length; i++)
        {
            bool m = true;
            for (int j = 0; j < needle.Length; j++) if (hay[i + j] != needle[j]) { m = false; break; }
            if (m) return i;
        }
        return -1;
    }
}
