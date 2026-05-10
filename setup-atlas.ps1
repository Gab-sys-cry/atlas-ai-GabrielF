#   powershell -ExecutionPolicy Bypass -File .\setup-atlas.ps1
# Optionnel :
#   powershell -ExecutionPolicy Bypass -File .\setup-atlas.ps1 -ModelChoice 2

param(
    [ValidateSet("1", "2")]
    [string]$ModelChoice
)

$ErrorActionPreference = "Stop"

function Test-CommandExists {
    param([string]$CommandName)
    return [bool](Get-Command $CommandName -ErrorAction SilentlyContinue)
}

function Get-TotalRamGB {
    $memoryModules = Get-CimInstance -ClassName Win32_PhysicalMemory
    if (-not $memoryModules) {
        throw "Impossible de récupérer la RAM installée."
    }

    $totalBytes = ($memoryModules | Measure-Object -Property Capacity -Sum).Sum
    return [math]::Floor($totalBytes / 1GB)
}

Write-Host "=== Setup ATLAS ===" -ForegroundColor Cyan

# 1) Vérifier Ollama
if (-not (Test-CommandExists "ollama")) {
    Write-Error "Ollama n'est pas installé ou n'est pas dans le PATH. Installe Ollama d'abord : https://ollama.com/download/windows"
    exit 1
}

# 2) Vérifier pip/python
if (-not (Test-CommandExists "python")) {
    Write-Error "Python n'est pas installé ou n'est pas dans le PATH."
    exit 1
}

$pythonVersion = & python --version 2>&1
Write-Host "Python détecté : $pythonVersion"

if (-not (Test-CommandExists "pip")) {
    Write-Host "pip non trouvé directement, tentative via 'python -m pip'..." -ForegroundColor Yellow
}

# 3) Détecter la RAM
$ramGB = Get-TotalRamGB
Write-Host "RAM détectée : $ramGB Go" -ForegroundColor Green

# 4) Choisir le modèle
$recommendedModels = @()

if ($ramGB -lt 8) {
    $selectedModel = "gemma3:1b"
}
elseif ($ramGB -lt 16) {
    $selectedModel = "qwen3:4b"
}
else {
    $selectedModel = "qwen3:8b"
}

Write-Host ""
Write-Host "Modèles recommandés pour cette machine :" -ForegroundColor Cyan
for ($i = 0; $i -lt $recommendedModels.Count; $i++) {
    Write-Host "[$($i + 1)] $($recommendedModels[$i])"
}

if (-not $ModelChoice) {
    if ($recommendedModels.Count -eq 1) {
        $selectedModel = $recommendedModels[0]
        Write-Host "Sélection automatique : $selectedModel" -ForegroundColor Green
    }
    else {
        $choice = Read-Host "Choisis un modèle (1 ou 2)"
        if ($choice -notin @("1", "2")) {
            Write-Error "Choix invalide."
            exit 1
        }
        $selectedModel = $recommendedModels[[int]$choice - 1]
    }
}
else {
    $index = [int]$ModelChoice - 1
    if ($index -ge $recommendedModels.Count) {
        Write-Error "Le choix $ModelChoice n'est pas valide pour cette machine."
        exit 1
    }
    $selectedModel = $recommendedModels[$index]
}

Write-Host ""
Write-Host "Téléchargement du modèle : $selectedModel" -ForegroundColor Cyan
& ollama pull $selectedModel
if ($LASTEXITCODE -ne 0) {
    Write-Error "Échec du téléchargement du modèle Ollama."
    exit 1
}

# 5) Installer le projet Python en editable
Write-Host ""
Write-Host "Installation du projet Python avec 'pip install -e .'" -ForegroundColor Cyan

if (Test-CommandExists "pip") {
    & pip install -e .
}
else {
    & python -m pip install -e .
}

if ($LASTEXITCODE -ne 0) {
    Write-Error "Échec de 'pip install -e .'"
    exit 1
}

Write-Host ""
Write-Host "Setup terminé avec succès." -ForegroundColor Green
Write-Host "Modèle installé : $selectedModel"
Write-Host "Projet installé en mode editable."