"""
atlas/memory.py -- Gestion de l'historique de conversation.

Deux niveaux de mémoire coexistent :

  ConversationMemory  -- mémoire courte (session en cours)
      Liste de messages Ollama [{role, content}], trimmée à max_turns.

  LongTermMemory      -- mémoire longue (inter-sessions, vectorielle)
      Stocke des paires Q/R dans ChromaDB avec embeddings maison.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter
from pathlib import Path
from typing import Literal

import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

Role = Literal["system", "user", "assistant"]


class _TFIDFEmbedder(EmbeddingFunction):
    """
    Embedder simplifié, récupéré sur internet, permettant d'obtenir des embeddings de dimension fixe à partir de texte brut,
    à la place d'utiliser all-MiniLM-L6-v2 de SentenceTransformers par xemple.
    """

    DIM = 512

    def __call__(self, input: Documents) -> Embeddings:
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> list[float]:
        tokens = re.findall(r"[a-záàâäéèêëíìîïóòôöúùûüçñ]+", text.lower()) # mots simples, sans ponctuation ni chiffres
        if not tokens:
            return [0.0] * self.DIM

        tf = Counter(tokens)
        vec = [0.0] * self.DIM

        for token, count in tf.items():
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            idx = h % self.DIM
            sign = 1 if (h >> 16) & 1 else -1
            vec[idx] += sign * (count / len(tokens))

        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def __init__(self) -> None:
        pass



# Mémoire courte -- session en cours


class ConversationMemory:
    """
    Stocke et gère l'historique de la conversation en cours.

    Paramètres
    ----------
    system_prompt : str | None
        Prompt système injecté au début de chaque session.
    max_turns : int
        Conserve uniquement les N derniers échanges pour rester
        dans la fenêtre de contexte du modèle.
    persist_path : Path | str | None
        Chemin JSON pour persister l'historique entre sessions.
    """

    def __init__(
        self,
        system_prompt: str | None = None,
        max_turns: int = 20,
        persist_path: Path | str | None = None,
    ) -> None:
        self._history: list[dict] = []
        self._system_prompt = system_prompt
        self.max_turns = max_turns
        self.persist_path = Path(persist_path) if persist_path else None

        if system_prompt:
            self._history.append({"role": "system", "content": system_prompt})

        if self.persist_path and self.persist_path.exists():
            self._load()

    
    # Interface principale
    

    def add_user(self, content: str) -> None:
        """Ajoute un message utilisateur à l'historique."""
        self._history.append({"role": "user", "content": content})
        self._trim()

    def add_assistant(self, content: str) -> None:
        """Ajoute une réponse assistant à l'historique."""
        self._history.append({"role": "assistant", "content": content})
        self._trim()
        if self.persist_path:
            self._save()

    def get_messages(self) -> list[dict]:
        """Retourne une copie de l'historique complet."""
        return list(self._history)

    def update_system_prompt(self, new_prompt: str) -> None:
        """
        Remplace le message système.
        """
        if self._history and self._history[0]["role"] == "system":
            self._history[0]["content"] = new_prompt
        else:
            self._history.insert(0, {"role": "system", "content": new_prompt})

    def clear(self, keep_system: bool = True) -> None:
        """Réinitialise l'historique."""
        if keep_system and self._system_prompt:
            self._history = [{"role": "system", "content": self._system_prompt}]
        else:
            self._history = []

    @property
    def turn_count(self) -> int:
        """Nombre d'échanges user/assistant (hors message système)."""
        return sum(1 for m in self._history if m["role"] == "user")

    def estimate_tokens(self) -> int:
        """
        Estimation approximative du nombre de tokens dans l'historique.
        Formule : len(words) * 1.3.
        """
        total_words = sum(
            len(m["content"].split()) for m in self._history
        )
        return int(total_words * 1.3)

    def summary(self) -> str:
        """Résumé lisible de l'historique pour /history."""
        lines = []
        for i, msg in enumerate(self._history):
            role = msg["role"].upper()
            preview = msg["content"][:80].replace("\n", " ")
            ellipsis = "…" if len(msg["content"]) > 80 else ""
            lines.append(f"  [{i:02d}] {role}: {preview}{ellipsis}")
        tokens = self.estimate_tokens()
        lines.append(f"\n  ~{tokens} tokens estimés | {self.turn_count} tours")
        return "\n".join(lines) if lines else "  (historique vide)"

    
    # Persistance
    

    def _save(self) -> None:
        if self.persist_path:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        with open(self.persist_path, encoding="utf-8") as f:
            self._history = json.load(f)

    
    # Gestion de la fenêtre de contexte
    

    def _trim(self) -> None:
        """Conserve uniquement max_turns échanges (hors système)."""
        system_msgs = [m for m in self._history if m["role"] == "system"]
        other_msgs  = [m for m in self._history if m["role"] != "system"]

        max_msgs = self.max_turns * 2
        if len(other_msgs) > max_msgs:
            other_msgs = other_msgs[-max_msgs:]

        self._history = system_msgs + other_msgs


# Mémoire longue -- inter-sessions, vectorielle (ChromaDB)

class LongTermMemory:
    def __init__(
        self,
        db_path: str | Path,
        collection_name: str = "conversations",
        top_k: int = 5,
        min_similarity: float = 0.3,
    ) -> None:
        self.top_k = top_k
        self.min_similarity = min_similarity
        self._embedder = _TFIDFEmbedder()

        db_path = Path(db_path)
        db_path.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(db_path))
        self._col = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._embedder,
        )

    # Écriture
    
    def store(
        self,
        user_msg: str,
        assistant_msg: str,
        metadata: dict | None = None,
    ) -> str:
        """
        Stocke une paire Q/R comme un seul souvenir.

        Le document stocké est la concaténation des deux pour que
        l'embedding capture le contexte complet de l'échange.
        Retourne l'ID du souvenir créé.
        """
        document = f"Q: {user_msg}\nR: {assistant_msg}"
        doc_id = hashlib.sha256(document.encode()).hexdigest()[:16]

        meta = {
            "timestamp": time.time(),
            "user_msg":  user_msg[:500],   # tronqué pour ChromaDB
            "client":    "",
            "topic":     "",
        }
        if metadata:
            meta.update(metadata)

        # add() ignore silencieusement les IDs déjà présents -> déduplication
        try:
            self._col.add(
                documents=[document],
                ids=[doc_id],
                metadatas=[meta],
            )
        except Exception:
            # ID déjà existant : ChromaDB lève une erreur, on l'ignore
            pass

        return doc_id

    # Lecture
    
    def recall(self, query: str, filter_meta: dict | None = None) -> list[dict]:
        """
        Recherche les souvenirs les plus pertinents pour une requête.

        Retourne une liste de dicts :
          {"document": str, "distance": float, "metadata": dict}
        triée par pertinence décroissante, filtrée par min_similarity.
        """
        total = self._col.count()
        if total == 0:
            return []

        n = min(self.top_k, total)

        kwargs: dict = {"query_texts": [query], "n_results": n}
        if filter_meta:
            kwargs["where"] = filter_meta

        results = self._col.query(**kwargs)

        memories = []
        for doc, dist, meta in zip(
            results["documents"][0],
            results["distances"][0],
            results["metadatas"][0],
        ):
            # ChromaDB retourne des distances L2 normalisées (0=identique, 2=opposé)
            similarity = 1.0 - (dist / 2.0)
            if similarity >= self.min_similarity:
                memories.append({
                    "document":   doc,
                    "similarity": round(similarity, 3),
                    "metadata":   meta,
                })

        return memories

    def forget(self, query: str) -> int:
        """
        Supprime les souvenirs matchant la requête (commande /forget).
        Retourne le nombre de souvenirs supprimés.
        """
        matches = self.recall(query)
        if not matches:
            return 0

        # Récupérer les IDs correspondants
        results = self._col.query(
            query_texts=[query],
            n_results=min(self.top_k, self._col.count()),
            include=["documents"],
        )
        ids_to_delete = results["ids"][0]
        self._col.delete(ids=ids_to_delete)
        return len(ids_to_delete)

    @property
    def count(self) -> int:
        """Nombre total de souvenirs stockés."""
        return self._col.count()

    
    # Injection dans le system prompt
    

    def build_memory_block(self, query: str) -> str:
        """
        Construit le bloc texte à injecter dans le system prompt.
        Retourne une chaîne vide si aucun souvenir pertinent.
        """
        memories = self.recall(query)
        if not memories:
            return ""

        lines = ["--- Souvenirs de sessions précédentes ---"]
        for i, m in enumerate(memories, 1):
            lines.append(f"[{i}] (similarité {m['similarity']}) {m['document']}")
        lines.append("--- Fin des souvenirs ---")
        return "\n".join(lines)