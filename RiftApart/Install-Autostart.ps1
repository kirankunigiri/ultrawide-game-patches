# Start the helper automatically with Rift Apart: adds a shortcut to your Startup folder
# that runs autostart.pyw at logon (no admin rights, no scheduled task).
#   .\Install-Autostart.ps1              install (helper silent)
#   .\Install-Autostart.ps1 -DebugLogging    install with --debug logs in research\
#   .\Install-Autostart.ps1 -Remove      uninstall
param([switch]$Remove, [switch]$DebugLogging)
$link = Join-Path ([Environment]::GetFolderPath('Startup')) 'Rift Apart minimap helper.lnk'
if ($Remove) {
    if (Test-Path $link) { Remove-Item $link }
    Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
        Where-Object { $_.CommandLine -match 'autostart\.pyw' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId }
    'Removed autostart.'
    return
}
$pythonw = (Get-Command pythonw.exe -ErrorAction Stop).Source
$script = Join-Path $PSScriptRoot 'autostart.pyw'
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($link)
$s.TargetPath = $pythonw
$s.Arguments = '"' + $script + '"' + $(if ($DebugLogging) { ' --debug' } else { '' })
$s.WorkingDirectory = $PSScriptRoot
$s.WindowStyle = 7
$s.Description = 'Starts the Rift Apart minimap/sprint helper whenever the game runs'
$s.Save()
# Start the watcher now too, unless one is already running.
$running = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -match 'autostart\.pyw' }
if (-not $running) { Start-Process -FilePath $link }
"Installed: $link"
