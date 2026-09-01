$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$studioCommand = Join-Path $projectRoot ".venv\Scripts\anime-studio.exe"

if (-not (Test-Path -LiteralPath $studioCommand)) {
    throw "Anime Studioの仮想環境が見つかりません。READMEの導入手順を先に実行してください。"
}

Set-Location -LiteralPath $projectRoot
& $studioCommand status --open
