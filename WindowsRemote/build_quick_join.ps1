$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistDir = Join-Path $ProjectDir "dist"
$BuildDir = Join-Path $ProjectDir ".pyinstaller-build\quick-join"

Push-Location -LiteralPath $ProjectDir
try {
    try {
        python -m PyInstaller --version | Out-Null
    } catch {
        throw "未安装 PyInstaller。请先执行: python -m pip install pyinstaller"
    }

    python -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name "DreadHungerQuickJoin" `
        --icon (Join-Path $ProjectDir "assets\quick_join_icon.ico") `
        --add-data "$ProjectDir\connect_client_win64.js;." `
        --add-data "$ProjectDir\assets\quick_join_icon.png;assets" `
        --add-data "$ProjectDir\assets\quick_join_icon.ico;assets" `
        --distpath $DistDir --workpath $BuildDir `
        --specpath (Join-Path $ProjectDir ".pyinstaller-build") "quick_join_client.py"
    if ($LASTEXITCODE -ne 0) { throw "快速进服器打包失败" }

    Write-Host "`n打包完成：" -ForegroundColor Green
    Get-Item -LiteralPath (Join-Path $DistDir "DreadHungerQuickJoin.exe") | Select-Object FullName, Length
} finally {
    Pop-Location
}
