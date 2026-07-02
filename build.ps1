# Packages Focus Overlay into a single standalone .exe (no Python required to run it).
# Usage: powershell -File build.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

py -3.13 -m pip install -r requirements.txt
py -3.13 -m pip install pyinstaller

py -3.13 -m PyInstaller `
    --onefile `
    --windowed `
    --name FocusOverlay `
    --distpath dist `
    --workpath build `
    --specpath build `
    main.py

Write-Output "Built: $PSScriptRoot\dist\FocusOverlay.exe"
