# ATLAS — Assistant IA Local

## Objectif du projet

**ATLAS** est un assistant IA 100% local développé pour **ATLAS Consulting**, cabinet de conseil IT.

Face aux contraintes de confidentialité (clients bancaires et santé), cet assistant permet aux consultants de :

- Poser des questions techniques et métier
- Bénéficier d’une mémoire courte (dans la session) et longue (persistante)
- Respecter des règles strictes de sécurité et de gouvernance (guardrails)
- Garder toutes les données sur site (aucun envoi vers OpenAI, Anthropic, etc.)

**Contraintes du projet** : tout doit être codé "from scratch" (pas de LangChain/LlamaIndex), en une journée.

---

## 🚀 Comment lancer le projet

### 1. Prérequis
- Python 3.10+
- Ollama installé et lancé (`ollama serve`)
- Modèle recommandé : `llama3.2:3b` ou `qwen2:7b` (selon la RAM)

### 2. Installation

```bash
# 1. Cloner le repo
git clone https://github.com/Gab-sys-cry/atlas-ai-GabrielF.git
cd atlas-ai-GabrielF

# 2. Créer l'environnement virtuel
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Linux / Mac

# 3. Installer les dépendances
pip install -e .

# 4. (Optionnel) Télécharger le modèle
ollama pull llama3.2:3b