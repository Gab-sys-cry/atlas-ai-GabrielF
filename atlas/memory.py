"""
atlas/memory.py Gestion de l'historique de conversation.

L'historique est une liste de messages au format Ollama :
  [{"role": "user"|"assistant"|"system", "content": "..."}]

Optionnellement persisté sur disque en JSON.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

Role = Literal["system", "user", "assistant"]


class ConversationMemory:
    """
    Stocke et gère l'historique de la conversation.

    Paramètres
    ----------
    system_prompt : str | None
        Prompt système injecté au début de chaque session.
    max_turns : int | None
        Si défini, conserve uniquement les N derniers échanges
        (en plus du message système) pour éviter de dépasser
        la fenêtre de contexte.
    persist_path : Path | str | None
        Chemin fichier pour persister l'historique entre sessions.
    """

    def __init__(
        self,
        system_prompt: str | None = None,
        max_turns: int | None = None,
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

    # Méthodes publiques pour manipuler l'historique

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

    def get_messages(self) -> list[dict]: # fonction app au moment du /history
        """Retourne une copie de l'historique complet."""
        return list(self._history)

    def clear(self, keep_system: bool = True) -> None: # fonction app lors du /clear
        """Réinitialise l'historique."""
        if keep_system and self._system_prompt:
            self._history = [{"role": "system", "content": self._system_prompt}]
        else:
            self._history = []

    @property # propriété pour calculer à la volée, ce qui veut dire sans stocker une variable supplémentaire
    def turn_count(self) -> int:
        """Nombre d'échanges user/assistant (hors message système)."""
        return sum(1 for m in self._history if m["role"] == "user")

    def summary(self) -> str:
        """Résumé lisible de l'historique pour débogage."""
        lines = []
        for i, msg in enumerate(self._history):
            role = msg["role"].upper()
            preview = msg["content"][:80].replace("\n", " ")
            lines.append(f"  [{i:02d}] {role}: {preview}{'…' if len(msg['content']) > 80 else ''}") # affichage synthétique de chaque message (index, rôle, début du contenu)
        return "\n".join(lines) if lines else "  (historique vide)"

    # Persistence de l'historique sur disque

    def _save(self) -> None:
        if self.persist_path:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        with open(self.persist_path, encoding="utf-8") as f:
            self._history = json.load(f)

   # Méthode privée pour limiter l'historique à max_turns échanges (hors système)

    def _trim(self) -> None:
        """Conserve uniquement max_turns échanges (hors système)."""
        if self.max_turns is None:
            return

        # Séparer le message système du reste
        system_msgs = [m for m in self._history if m["role"] == "system"]
        other_msgs = [m for m in self._history if m["role"] != "system"]

        # Chaque tour = 1 user + 1 assistant → 2 messages
        max_msgs = self.max_turns * 2
        if len(other_msgs) > max_msgs:
            other_msgs = other_msgs[-max_msgs:]

        self._history = system_msgs + other_msgs