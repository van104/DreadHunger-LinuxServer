$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistDir = Join-Path $ProjectDir "dist"
$BuildDir = Join-Path $ProjectDir ".pyinstaller-build"

Push-Location -LiteralPath $ProjectDir
try {
    try {
        python -m PyInstaller --version | Out-Null
    } catch {
        throw "未安装 PyInstaller。请先执行: python -m pip install pyinstaller"
    }

    python -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name "DreadHungerLinuxRemoteManager" `
        --distpath $DistDir --workpath (Join-Path $BuildDir "manager") `
        --specpath $BuildDir "server_manager_client.py"
    if ($LASTEXITCODE -ne 0) { throw "开服器客户端打包失败" }

    python -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name "DreadHungerLinuxGMConsole" `
        --distpath $DistDir --workpath (Join-Path $BuildDir "gm") `
        --specpath $BuildDir "gm_console_client.py"
    if ($LASTEXITCODE -ne 0) { throw "GM 控制台客户端打包失败" }

    Write-Host "`n打包完成：" -ForegroundColor Green
    Get-ChildItem -LiteralPath $DistDir -Filter *.exe | Select-Object FullName, Length
} finally {
    Pop-Location
}
