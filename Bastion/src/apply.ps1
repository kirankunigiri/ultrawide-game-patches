<#
.SYNOPSIS
  Convenience wrapper to build+run the Bastion ultrawide patcher.
.EXAMPLE
  ./apply.ps1
  ./apply.ps1 -Exe "D:\Games\Bastion\Bastion.exe" -Width 3440 -Height 1440
#>
param(
  [string]$Exe    = "C:\Games\Solo\Bastion\Bastion.exe",
  [int]   $Width  = 5120,
  [int]   $Height = 1440
)
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
  dotnet run -- --exe "$Exe" --width $Width --height $Height
}
finally {
  Pop-Location
}
