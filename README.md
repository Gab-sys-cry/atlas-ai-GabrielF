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

```bash
git clone https://github.com/Gab-sys-cry/atlas-ai-GabrielF.git
cd atlas
python -m venv venv && venv\Scripts\activate  # Windows
pip install -r requirements.txt
.\scripts\setup-atlas.ps1                     # crée le modèle Ollama
python scripts/atlas_chat.py
```

-> **Guide complet : [SETUP.md](SETUP.md)**

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