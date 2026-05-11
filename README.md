# Atlas — Assistant IA on-premise pour ATLAS Consulting

Atlas est un assistant conversationnel qui tourne entièrement en local, sans envoyer de données vers le cloud.

---

## Ce qu'il fait

- Répond à vos questions professionnelles en français
- Se souvient du contexte de la conversation en cours
- Retrouve des informations de sessions précédentes
- Refuse les sujets hors périmètre (politique, religion…)
- Masque automatiquement les données sensibles (numéros de CB, emails…)

---

## Démarrage rapide

## Démarrage rapide

```bash
git clone https://github.com/Gab-sys-cry/atlas-ai-GabrielF.git
cd atlas-ai-GabrielF

# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# macOS / Linux
python3 -m venv venv
source venv/bin/activate

# Windows
.\scripts\setup-atlas.ps1

# macOS / Linux
bash scripts/setup-atlas.sh
```

## Ces scripts automatisent tout :

- Détection de la RAM installée
- Choix intelligent du modèle Ollama selon votre matériel (qwen3:8b, qwen3:4b ou gemma3:1b)
- Téléchargement du modèle de base via ollama pull
- Création du Modelfile avec le prompt système Atlas
- Création du modèle optimisé atlas
- Création de l’environnement virtuel (venv) si nécessaire
- Installation du projet en mode éditable (pip install -e .)
- Mise à jour de pip

-> **Guide complet : [SETUP.md](docs/setup.md)**

---

## Commandes en session

| Commande | Description |
|---|---|
| `/memory` | Voir les souvenirs des sessions précédentes |
| `/forget <sujet>` | Supprimer des souvenirs |
| `/history` | Historique de la session en cours |
| `/metrics` | Statistiques de la session |
| `/help` | Toutes les commandes |
| `/quit` | Quitter |

---

## Stack technique

- **LLM** : Ollama (modèle local, aucune donnée externe)
- **Mémoire** : ChromaDB (recherche vectorielle locale)
- **Config** : YAML + validation Pydantic
- **Traces** : JSONL (`data/traces.jsonl`)

---

## Prérequis

- Python 3.10+
- [Ollama](https://ollama.com)
- 8 GB de RAM minimum (16 GB recommandés)