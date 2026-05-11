# Guide de setup — Atlas

Ce guide couvre tout ce qu'il faut faire après un `git clone` pour avoir Atlas opérationnel.

---

## Prérequis

- **Python 3.10+** — [python.org](https://www.python.org/downloads/)
- **Ollama** — [ollama.com](https://ollama.com) (installer et lancer `ollama serve`)
- **Git**

Vérifiez que tout est accessible :

```bash
python --version   # >= 3.10
ollama --version
```

---

## 1. Cloner le projet

```bash
git clone https://github.com/Gab-sys-cry/atlas-ai-GabrielF.git
cd atlas-ai-GabrielF/
```

---

## 2. Créer un environnement virtuel

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

---

## 3. Installer les dépendances

Deux options équivalentes :

**Option A — depuis `requirements.txt` (recommandée pour démarrer vite) :**

```bash
pip install -r requirements.txt
```

**Option B — depuis `pyproject.toml` :**

```bash
pip install -e .          # dépendances core
pip install -e ".[dev]"   # + outils de dev (pytest, ruff, mypy)
```

---

## 4. Créer le modèle Atlas dans Ollama

### Option A — Script automatique (recommandé)

Le script détecte votre RAM et choisit le bon modèle de base automatiquement :

| RAM disponible | Modèle de base choisi |
|---|---|
| >= 16 GB | `qwen3:8b` — qualité maximale |
| 8 – 16 GB | `llama3.2:3b` — bon compromis |
| < 8 GB | `qwen2.5:1.5b` — mode dégradé |

```bash
# Windows (PowerShell, depuis la racine du projet)
.\scripts\setup-atlas.ps1

# macOS / Linux
bash scripts/setup-atlas.sh
```

Le script fait dans l'ordre :
1. Détecte la RAM
2. Télécharge le bon modèle de base via `ollama pull`
3. Génère le `Modelfile` avec le bon `FROM`
4. Crée le modèle `atlas` via `ollama create atlas -f Modelfile`

### Option B — Manuellement

Si vous préférez choisir vous-même :

```bash
# Choisir et télécharger un modèle de base
ollama pull qwen3:8b          # ou llama3.2:3b, ou qwen2.5:1.5b

# Éditer la première ligne du Modelfile si besoin
# FROM qwen3:8b  <- changer ici

# Créer le modèle atlas
ollama create atlas -f Modelfile

# Vérifier
ollama list   # atlas doit apparaître
```

Si config faite à la main, alors lancer le script de cette maniere : 

```bash
python scripts/atlas_chat.py --config config/default.yml
```
et modifier le default.yml

---

## 5. Vérifier l'installation

```bash
# Tester que le modèle répond
ollama run atlas "Bonjour, qui es-tu ?"

# Lancer Atlas
python scripts/atlas_chat.py
```

---

## 6. Configuration

La configuration vit dans `config/atlas.yml`. Vous pouvez y modifier :

- `model.name` — le modèle à utiliser (défaut : `atlas`)
- `model.temperature` — créativité des réponses (0 = déterministe, 1 = créatif)
- `persona.system_prompt` — personnalité de l'assistant
- `guardrails.blocked_topics` — sujets à refuser
- `memory.long_term_enabled` — activer/désactiver la mémoire inter-sessions

Pour le développement, utilisez `config/default.yml` :

```bash
python scripts/atlas_chat.py --config config/default.yml
```

---

## 7. Structure du projet

```
atlas-ai/
├── atlas/                  # Package principal
│   ├── config.py
│   ├── llm.py
│   ├── memory.py
│   ├── monitoring.py
│   └── guardrails.py
├── scripts/
│   ├── atlas_chat.py
│   ├── analyze_traces.py
│   ├── setup-atlas.ps1
│   └── setup-atlas.sh
├── config/
│   ├── atlas.yml
│   └── default.yml
├── pyproject.toml
├── requirements.txt
├── Modelfile
└── venv/
```

---

## Commandes utiles

```bash
# Lancer Atlas
python scripts/atlas_chat.py

# Lancer avec un autre modèle (surcharge le YAML)
python scripts/atlas_chat.py --model llama3.2:3b

# Afficher les métriques après chaque réponse
python scripts/atlas_chat.py --show-metrics

# Lister les modèles Ollama disponibles
python scripts/atlas_chat.py --list-models

# Analyser les traces de session
python scripts/analyze_traces.py
```

---

## Problèmes fréquents

**`Impossible de joindre Ollama`**
-> Vérifiez qu'Ollama est démarré : `ollama serve` (Windows : l'app Ollama doit être lancée)

**`Erreur de configuration dans config/atlas.yml`**
-> Un champ est invalide ou manquant. Le message indique exactement lequel.

**`ModuleNotFoundError: atlas`**
-> L'environnement virtuel n'est pas activé, ou les dépendances ne sont pas installées.

**Modèle trop lent / out of memory**
-> Relancez `setup-atlas.ps1` / `setup-atlas.sh` pour choisir un modèle adapté à votre RAM.