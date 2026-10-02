$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistDir = Join-Path $ProjectDir "dist"
$BuildDir = Join-Path $ProjectDir ".pyinstaller-build\quick-join"

Push-Location -LiteralPath $ProjectDir
try {
    try {
        python -m PyInstaller --version | Out-Null
    } catch {
        throw "PyInstaller is not installed. Run: python -m pip install pyinstaller"
    }

    python -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name "恐惧饥饿进服器-v2.0.0" `
        --version-file (Join-Path $ProjectDir "assets\quick_join_version.txt") `
        --icon (Join-Path $ProjectDir "assets\quick_join_taskbar.ico") `
        --add-data "$ProjectDir\app\connect_client_win64.js;." `
        --add-data "$ProjectDir\app\quick_join_announce_hook.js;." `
        --add-data "$ProjectDir\assets\quick_join_icon_v2.png;assets" `
        --add-data "$ProjectDir\assets\quick_join_taskbar.png;assets" `
        --add-data "$ProjectDir\assets\quick_join_taskbar.ico;assets" `
        --distpath $DistDir --workpath $BuildDir `
        --specpath (Join-Path $ProjectDir ".pyinstaller-build") "app/quick_join_client.py"
    if ($LASTEXITCODE -ne 0) { throw "Quick join build failed" }

    Copy-Item -LiteralPath (Join-Path $ProjectDir "..\LICENSE") -Destination (Join-Path $DistDir "LICENSE")

    Write-Host "`nBuild completed:" -ForegroundColor Green
    Get-Item -LiteralPath (Join-Path $DistDir "恐惧饥饿进服器-v2.0.0.exe") | Select-Object FullName, Length
} finally {
    Pop-Location
}
