# Architecture Atlas — Décisions techniques

## Vue d'ensemble

```
config/atlas.yml          Modelfile
       │                      │
       ▼                      ▼
  AtlasConfig           ollama create atlas
  (Pydantic)                  │
       │                      ▼
       └──────► atlas_chat.py ◄──── Ollama API
                    │
          ┌─────────┼──────────┐
          ▼         ▼          ▼
   ConversationMemory  LongTermMemory  TraceLogger
   (session)           (ChromaDB)      (JSONL)
```

---

## Decisions

### D1 — Où vit le system prompt ?

**Décision : en deux endroits, avec des rôles distincts.**

| Endroit | Rôle | Modifié par |
|---|---|---|
| `Modelfile` | Personnalité de base, embedée dans le modèle | Ops / MLOps |
| `config/atlas.yml` → `persona.system_prompt` | Enrichissement dynamique (souvenirs, contexte métier) | Dev / Product |

Le `Modelfile` contient le socle minimal : identité, langue, refus hors périmètre. Il est compilé dans le modèle une fois pour toutes via `ollama create atlas`.

`atlas_chat.py` enrichit ce prompt à chaque tour avec les souvenirs pertinents issus de ChromaDB. Cet enrichissement ne peut pas vivre dans le Modelfile car il est dynamique par nature.

**Conséquence** : si les deux sont actifs, le `SYSTEM` du Modelfile est l'instruction de base, et le system prompt applicatif vient s'y ajouter. En pratique, on pointe vers le modèle `atlas` (Modelfile compilé) et le YAML gère uniquement l'enrichissement.

---

### D2 — CLI : `atlas` (Modelfile) ou `qwen3:8b` + system prompt code ?

**Décision : pointer vers `atlas` en production, `qwen3:8b` en développement.**

- `config/atlas.yml` → `model.name: "atlas"` — profil prod, modèle compilé
- `config/default.yml` → `model.name: "qwen3:8b"` — profil dev, modèle de base

Raisons :
1. **Séparation des responsabilités** : l'équipe Ops contrôle le Modelfile et le publie via `ollama create`. Les devs ne touchent pas au modèle.
2. **Cohérence** : un consultant qui lance `ollama run atlas` directement (sans la CLI) obtient le même comportement de base.
3. **Sécurité** : les paramètres `stop` dans le Modelfile (`"Human:"`, `"User:"`) évitent certaines attaques de prompt injection de bas niveau.

---

### D3 — Que se passe-t-il si un consultant change le YAML mais pas le Modelfile ?

**Scénario** : consultant modifie `persona.system_prompt` dans `atlas.yml`.

**Impact** : le nouveau prompt est injecté *en plus* du SYSTEM du Modelfile, pas *à la place*. Le modèle `atlas` garde toujours son comportement de base (langue, refus hors périmètre). La couche YAML ne peut pas annuler ce que le Modelfile a compilé.

**Conséquence intentionnelle** : les garde-fous fondamentaux (identité, langue) sont dans le Modelfile et ne peuvent pas être effacés par erreur via la config. Seul un `ollama create atlas` avec un nouveau Modelfile les modifie.

---

### D4 — Validation Pydantic

`AtlasConfig.from_yaml()` valide la config avant tout démarrage. Exemples d'erreurs claires :

```
Erreur de configuration dans config/atlas.yml :
  [model → temperature] Input should be less than or equal to 2.0
  [server → base_url] String should match pattern '^https?://'
```

Cela évite les bugs silencieux où une valeur invalide se propage jusqu'à l'appel LLM.

---

## Structure des fichiers

```
atlas/
├── atlas/
│   ├── config.py       ← Schéma Pydantic (S4) — source de vérité des types
│   ├── llm.py          ← Client Ollama httpx pur
│   ├── memory.py       ← Mémoire courte + longue (ChromaDB)
│   ├── monitoring.py   ← Traces JSONL + métriques session
│   └── guardrails.py   ← PII, injection, rate limit, topics
├── scripts/
│   ├── atlas_chat.py   ← CLI principale
│   └── analyze_traces.py ← Analyse JSONL (pandas + matplotlib)
├── config/
│   ├── atlas.yml       ← Profil production (pointe vers modèle `atlas`)
│   └── default.yml     ← Profil développement (modèle de base)
├── Modelfile           ← Définition du modèle `atlas` pour Ollama
├── docs/
│   └── architecture.md ← Ce fichier
└── tests/
```