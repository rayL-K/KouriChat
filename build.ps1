<# KouriChat 打包脚本：构建前端 + 打成 uv 包（wheel/sdist），供客户机安装。

用法（在项目根目录）：
    .\build.ps1              # 全量：npm 构建前端 + uv build
    .\build.ps1 -SkipFrontend  # 跳过前端构建（复用已填充的 kourichat/webui/static）
    .\build.ps1 -Clean         # 先清理 dist/ 与 kourichat/webui/static/ 再构建

产物：
    dist/kourichat-<version>-py3-none-any.whl
    dist/kourichat-<version>.tar.gz
    dist/elixir-0.1.0-py3-none-any.whl   （已复制，客户机安装必需——elixir 不在 PyPI）

客户机全局安装（需 Python 3.14+ 与 uv）：
    uv tool install dist\kourichat-<version>-py3-none-any.whl --with dist\elixir-*.whl
    kourichat run                      # 首次运行自动生成 kourichat.toml
    uv tool uninstall kourichat        # 全局卸载
#>

param(
    [switch]$Clean,          # 清理 dist/ 与包内 static/ 后重建
    [switch]$SkipFrontend    # 跳过前端构建
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "== KouriChat 打包 ==" -ForegroundColor Cyan

# 0) 工具检查
foreach ($t in @("uv", "node", "npm")) {
    if (-not (Get-Command $t -ErrorAction SilentlyContinue)) {
        throw "缺少工具：$t（请先安装 uv 与 Node.js）"
    }
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Warning "未检测到 python（打包本身不需要，客户机安装时需要 3.14+）"
}

# 1) 前端构建 → 填充 kourichat/webui/static/
$static = Join-Path $Root "kourichat/webui/static"
if ($Clean) {
    Remove-Item (Join-Path $Root "dist") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $static -Recurse -Force -ErrorAction SilentlyContinue
}
if (-not $SkipFrontend) {
    Write-Host "[1/3] 构建前端..." -ForegroundColor Cyan
    Push-Location (Join-Path $Root "frontend")
    if (-not (Test-Path "node_modules")) {
        npm install --no-audit --no-fund
    }
    npm run build
    Pop-Location
    Remove-Item $static -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force $static | Out-Null
    Copy-Item (Join-Path $Root "frontend/dist/*") $static -Recurse
    Write-Host "      前端产物已填充到 kourichat/webui/static/" -ForegroundColor Green
} else {
    if (-not (Test-Path (Join-Path $static "index.html"))) {
        throw "kourichat/webui/static/ 缺失：请先运行 .\build.ps1（去掉 -SkipFrontend）"
    }
    Write-Host "[1/3] 跳过前端构建（复用现有 static）" -ForegroundColor Yellow
}

# 2) uv build
Write-Host "[2/3] uv build..." -ForegroundColor Cyan
uv build --out-dir dist
# elixir 为本地 wheel（PyPI 无此包），复制进产物目录供客户机一并安装
$elixir = Get-ChildItem -Path $Root -Filter "elixir-*.whl" | Select-Object -First 1
if ($elixir) {
    Copy-Item $elixir.FullName (Join-Path $Root "dist") -Force
    Write-Host "      已复制 $($elixir.Name) 到 dist/" -ForegroundColor Green
} else {
    Write-Warning "未找到 elixir-*.whl：客户机安装时 elixir 依赖会解析失败（需手工提供）"
}

# 3) 汇总
Write-Host "[3/3] 产物清单：" -ForegroundColor Cyan
$wheels = Get-ChildItem (Join-Path $Root "dist") -Filter "*.whl" | Sort-Object Name
$wheels | ForEach-Object {
    Write-Host ("      {0}  ({1:N0} bytes)" -f $_.Name, $_.Length) -ForegroundColor Gray
}

# 取最新 wheel 文件名（避免通配符匹配到旧版本）
$kwhl = ($wheels | Where-Object { $_.Name -like "kourichat-*-py3-none-any.whl" } | Select-Object -Last 1)
$ewhl = ($wheels | Where-Object { $_.Name -like "elixir-*.whl" } | Select-Object -Last 1)
if (-not $kwhl) { throw "未找到 kourichat wheel 产物" }

Write-Host ""
Write-Host "== 完成。客户机全局安装/卸载（Python 3.14+，uv）：" -ForegroundColor Green
if ($ewhl) {
    Write-Host "    全局安装：uv tool install dist\$($kwhl.Name) --with dist\$($ewhl.Name)"
} else {
    Write-Host "    全局安装：uv tool install dist\$($kwhl.Name)   # 需先自行提供 elixir 依赖"
}
Write-Host "    启动：kourichat run   （首次自动生成 kourichat.toml，浏览器打开 http://127.0.0.1:8080）"
Write-Host "    查看：kourichat --help"
Write-Host "    全局卸载：uv tool uninstall kourichat"
