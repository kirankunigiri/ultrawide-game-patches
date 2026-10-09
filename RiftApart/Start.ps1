param([switch]$DebugLogging)
$sourcePath = Join-Path $PSScriptRoot 'src'
if ($DebugLogging) {
    Push-Location -LiteralPath $sourcePath
    try { & python -u minimap.py --debug } finally { Pop-Location }
} else {
    Start-Process -FilePath 'pythonw.exe' -ArgumentList 'minimap.py' -WorkingDirectory $sourcePath -WindowStyle Hidden
}
