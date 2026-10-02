-- UltrawideFix settings for Fatal Claw. Edit, save, then restart the game.

return {
    -- Your screen resolution in pixels. Run the game at this same resolution.
    --   32:9  ->  5120 x 1440,  3840 x 1080,  7680 x 2160
    --   21:9  ->  3440 x 1440,  2560 x 1080,  3840 x 1600,  5120 x 2160
    ScreenWidth  = 5120,
    ScreenHeight = 1440,

    -- Optional FOV tuning. 1.0 keeps the game's 16:9 vertical view and shows more to the
    -- sides (recommended). Above 1.0 zooms out further, below 1.0 zooms in (0.5 - 2.0).
    FovScale = 1.0,

    -- Debug logging. false = the mod writes nothing (default). true = it writes what it
    -- does to ue4ss\UE4SS.log. Only turn this on when troubleshooting.
    Debug = false,
}
