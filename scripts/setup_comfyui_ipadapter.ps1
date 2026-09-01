param(
    [string]$ComfyUiRoot = "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI",
    [string]$SharedModelsRoot = "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Shared\models",
    [switch]$Update
)

$ErrorActionPreference = "Stop"

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required but was not found on PATH."
    }
}

function Get-ModelFile(
    [string]$Url,
    [string]$Destination,
    [long]$ExpectedBytes
) {
    if (Test-Path -LiteralPath $Destination) {
        $actual = (Get-Item -LiteralPath $Destination).Length
        if ($actual -eq $ExpectedBytes) {
            Write-Host "Ready: $Destination"
            return
        }
        throw "Existing model has an unexpected size: $Destination ($actual bytes)"
    }

    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force $parent | Out-Null
    $partial = "$Destination.partial"
    & curl.exe -L --fail --retry 4 --continue-at - --output $partial $Url
    if ($LASTEXITCODE -ne 0) {
        throw "Download failed: $Url"
    }
    $actual = (Get-Item -LiteralPath $partial).Length
    if ($actual -ne $ExpectedBytes) {
        throw "Downloaded model size mismatch: $partial ($actual / $ExpectedBytes bytes)"
    }
    Move-Item -LiteralPath $partial -Destination $Destination
    Write-Host "Installed: $Destination"
}

Assert-Command git
Assert-Command curl.exe

if (-not (Test-Path -LiteralPath $ComfyUiRoot)) {
    throw "ComfyUI root does not exist: $ComfyUiRoot"
}

$customNodes = Join-Path $ComfyUiRoot "custom_nodes"
$extension = Join-Path $customNodes "ComfyUI_IPAdapter_plus"
if (-not (Test-Path -LiteralPath $extension)) {
    & git clone --depth 1 https://github.com/cubiq/ComfyUI_IPAdapter_plus.git $extension
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to clone ComfyUI_IPAdapter_plus."
    }
} elseif ($Update) {
    & git -C $extension pull --ff-only
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to fast-forward ComfyUI_IPAdapter_plus."
    }
} else {
    Write-Host "Ready: $extension"
}

Get-ModelFile `
    -Url "https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors" `
    -Destination (Join-Path $SharedModelsRoot "clip_vision\CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors") `
    -ExpectedBytes 2528373448

Get-ModelFile `
    -Url "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus-face_sd15.safetensors" `
    -Destination (Join-Path $SharedModelsRoot "ipadapter\ip-adapter-plus-face_sd15.safetensors") `
    -ExpectedBytes 98183288

Write-Host "IPAdapter setup complete. Restart Comfy Desktop before generating."
