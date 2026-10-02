<#
.SYNOPSIS
  Builds the ready-to-extract Fatal Claw ultrawide bundle (the GitHub Release asset).

.DESCRIPTION
  Downloads the pinned UE4SS build (hash-checked), applies the two settings this game needs
  ([EngineVersionOverride] 4.27, bundled example mods off), adds the UltrawideFix mod from
  ../dist and zips it so that extracting into the Fatal Claw folder (the one containing
  FatalClaw.exe) puts everything in FatalClaw\Binaries\Win64\.

.EXAMPLE
  ./package.ps1                  # -> out/FatalClaw-Ultrawide-v1.0.zip
  ./package.ps1 -Version 1.1
#>
param(
  [string]$Version = "1.0",
  [string]$OutDir  = (Join-Path $PSScriptRoot "out")
)
$ErrorActionPreference = "Stop"

# Pinned, tested UE4SS build. "experimental-latest" is a rolling release, so this exact file
# may disappear upstream; the published bundle keeps it available.
$Ue4ssName   = "UE4SS_v3.0.1-1152-ge3ba1016.zip"
$Ue4ssUrl    = "https://github.com/UE4SS-RE/RE-UE4SS/releases/download/experimental-latest/$Ue4ssName"
$Ue4ssSha256 = "AF8EA9D8975E8EFF7967423F43B8B50875E66A29A0F434CFFCE6E0867EA17252"

$modSrc  = Join-Path $PSScriptRoot "..\dist\UltrawideFix"
$work    = Join-Path $OutDir "work"
$stage   = Join-Path $work "stage"
$win64   = Join-Path $stage "FatalClaw\Binaries\Win64"
$zipName = "FatalClaw-Ultrawide-v$Version.zip"

New-Item -ItemType Directory -Force $OutDir | Out-Null
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory -Force $win64 | Out-Null

# 1. UE4SS (cached in out/, hash-checked)
$ue4ssZip = Join-Path $OutDir $Ue4ssName
if (-not (Test-Path $ue4ssZip)) {
  Write-Host "Downloading $Ue4ssName"
  Invoke-WebRequest -UseBasicParsing $Ue4ssUrl -OutFile $ue4ssZip
}
$hash = (Get-FileHash $ue4ssZip -Algorithm SHA256).Hash
if ($hash -ne $Ue4ssSha256) { throw "UE4SS hash mismatch: got $hash, expected $Ue4ssSha256" }
Expand-Archive $ue4ssZip $win64

# 2. Engine version override (the stock lines are empty: "MajorVersion =")
$ini = Join-Path $win64 "ue4ss\UE4SS-settings.ini"
$t = [IO.File]::ReadAllText($ini)
$t = $t -replace "(?m)^MajorVersion =[ \t]*(\r?)$", 'MajorVersion = 4$1'
$t = $t -replace "(?m)^MinorVersion =[ \t]*(\r?)$", 'MinorVersion = 27$1'
[IO.File]::WriteAllText($ini, $t)
if ($t -notmatch "(?m)^MajorVersion = 4\r?$" -or $t -notmatch "(?m)^MinorVersion = 27\r?$") { throw "EngineVersionOverride not applied" }

# 3. Bundled example mods off (mods.txt and mods.json)
$mt = Join-Path $win64 "ue4ss\Mods\mods.txt"
[IO.File]::WriteAllText($mt, ([IO.File]::ReadAllText($mt) -replace ":[ \t]*1", ": 0"))
$mj = Join-Path $win64 "ue4ss\Mods\mods.json"
[IO.File]::WriteAllText($mj, ([IO.File]::ReadAllText($mj) -replace '"mod_enabled":[ \t]*true', '"mod_enabled": false'))

# 4. The mod
Copy-Item $modSrc (Join-Path $win64 "ue4ss\Mods\") -Recurse

# 5. Zip (top level of the archive = the game folder)
$zip = Join-Path $OutDir $zipName
if (Test-Path $zip) { Remove-Item $zip -Force }
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::Open($zip, [IO.Compression.ZipArchiveMode]::Create)
try {
  $root = (Resolve-Path $stage).Path.TrimEnd('\') + '\'
  foreach ($f in Get-ChildItem $stage -Recurse -File) {
    $entry = $f.FullName.Substring($root.Length).Replace('\', '/')   # zip paths use "/"
    [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $f.FullName, $entry, [IO.Compression.CompressionLevel]::Optimal)
  }
} finally { $archive.Dispose() }
Remove-Item $work -Recurse -Force
Write-Host "Built $zip ($([math]::Round((Get-Item $zip).Length / 1MB, 1)) MB)"
