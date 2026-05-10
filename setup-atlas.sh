#!/usr/bin/env bash
set -euo pipefail

#   chmod +x ./setup-atlas.sh
#   ./setup-atlas.sh
#
# Optionnel :
#   ./setup-atlas.sh 2

MODEL_CHOICE="${1:-}"

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

get_total_ram_gb() {
  local os
  os="$(uname -s)"

  if [[ "$os" == "Linux" ]]; then
    local mem_kb
    mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
    echo $(( mem_kb / 1024 / 1024 ))
    return
  fi

  if [[ "$os" == "Darwin" ]]; then
    local mem_bytes
    mem_bytes="$(sysctl -n hw.memsize)"
    echo $(( mem_bytes / 1024 / 1024 / 1024 ))
    return
  fi

  echo "Système non supporté automatiquement: $os" >&2
  exit 1
}

echo "=== Setup ATLAS ==="

# 1) Vérifier Ollama
if ! command_exists ollama; then
  echo "Erreur: Ollama n'est pas installé ou pas dans le PATH." >&2
  echo "Installe Ollama d'abord: https://ollama.com/download" >&2
  exit 1
fi

# 2) Vérifier Python
if ! command_exists python3 && ! command_exists python; then
  echo "Erreur: Python n'est pas installé ou pas dans le PATH." >&2
  exit 1
fi

if command_exists python3; then
  PYTHON_CMD="python3"
else
  PYTHON_CMD="python"
fi

echo "Python détecté: $($PYTHON_CMD --version 2>&1)"

# 3) Détecter la RAM
RAM_GB="$(get_total_ram_gb)"
echo "RAM détectée: ${RAM_GB} Go"

# 4) Choisir les modèles
RECOMMENDED_MODELS=()

if (( RAM_GB < 8 )); then
  RECOMMENDED_MODELS=("gemma3:1b")
elif (( RAM_GB < 16 )); then
  RECOMMENDED_MODELS=("llama3.2:3b" "qwen3:4b")
else
  RECOMMENDED_MODELS=("qwen3:8b" "phi4-mini")
fi

echo
echo "Modèles recommandés pour cette machine:"
for i in "${!RECOMMENDED_MODELS[@]}"; do
  printf '[%d] %s\n' "$((i + 1))" "${RECOMMENDED_MODELS[$i]}"
done

if [[ -z "$MODEL_CHOICE" ]]; then
  if [[ "${#RECOMMENDED_MODELS[@]}" -eq 1 ]]; then
    SELECTED_MODEL="${RECOMMENDED_MODELS[0]}"
    echo "Sélection automatique: $SELECTED_MODEL"
  else
    read -r -p "Choisis un modèle (1 ou 2): " choice
    if [[ "$choice" != "1" && "$choice" != "2" ]]; then
      echo "Erreur: choix invalide." >&2
      exit 1
    fi
    SELECTED_MODEL="${RECOMMENDED_MODELS[$((choice - 1))]}"
  fi
else
  if [[ "$MODEL_CHOICE" != "1" && "$MODEL_CHOICE" != "2" ]]; then
    echo "Erreur: choix invalide." >&2
    exit 1
  fi

  index=$((MODEL_CHOICE - 1))
  if (( index >= ${#RECOMMENDED_MODELS[@]} )); then
    echo "Erreur: le choix $MODEL_CHOICE n'est pas valide pour cette machine." >&2
    exit 1
  fi

  SELECTED_MODEL="${RECOMMENDED_MODELS[$index]}"
fi

echo
echo "Téléchargement du modèle: $SELECTED_MODEL"
ollama pull "$SELECTED_MODEL"

echo
echo "Installation du projet Python avec 'pip install -e .'"

if command_exists pip3; then
  pip3 install -e .
elif command_exists pip; then
  pip install -e .
else
  "$PYTHON_CMD" -m pip install -e .
fi

echo
echo "Setup terminé avec succès."
echo "Modèle installé: $SELECTED_MODEL"
echo "Projet installé en mode editable."