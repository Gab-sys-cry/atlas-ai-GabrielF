"""
atlas/guardrails.py Filtres sur les entrées & sorties.

On bloque : 
- blocked_patterns : regex (rien n'est env au LLM)
- blocked_topics   : sujets hors périmètre (refus généré localement)
"""
from __future__ import annotations

import re # module pour les regex

class GuardrailError(Exception):
    """Levée quand une règle technique est violée (message vide, trop long etc...)."""


class TopicBlocked(Exception):
    """
    Levée quand le message touche un topic hors périmètre.
    """
    def __init__(self, topic: str, polite_reply: str) -> None:
        super().__init__(polite_reply)
        self.topic = topic
        self.polite_reply = polite_reply


class InputGuardrails:
    """
    Valide les messages utilisateur avant envoi au LLM.

    Paramètres
    ----------
    max_length : int
        Longueur maximale du message.
    blocked_patterns : list[str]
        Regex techniques bloquées.
    blocked_topics : list[str]
        Mots-clés de sujets hors périmètre
        avec un refus.
    persona_name : str
        Nom de l'assistant utilisé dans le message de refus.
    """

    def __init__(
        self,
        max_length: int = 4000,
        blocked_patterns: list[str] | None = None,
        blocked_topics: list[str] | None = None,
        persona_name: str = "Atlas",
    ) -> None:
        self.max_length = max_length
        self.persona_name = persona_name

        # Regex techniques
        self._patterns = [
            re.compile(p, re.IGNORECASE)
            for p in (blocked_patterns or [])
        ]

        # on cherche le mot entier (\b) pour éviter
        # de bloquer "politique" dans "géopolitique" si non souhaité
        self._topics: list[tuple[str, re.Pattern]] = [
            (topic, re.compile(rf"\b{re.escape(topic)}\b", re.IGNORECASE)) # rf pour raw + interpolation, re.escape pour échapper les caractères spéciaux dans le topic
            for topic in (blocked_topics or [])
        ]

    def validate(self, text: str) -> str:
        """
        Valide le texte et le retourne nettoyé.
        """
        text = text.strip()

        if not text:
            raise GuardrailError("Le message est vide.")

        if len(text) > self.max_length:
            raise GuardrailError(
                f"Message trop long ({len(text)} caractères, max {self.max_length})."
            )

        # Vérification patterns techniques
        for pattern in self._patterns:
            if pattern.search(text):
                raise GuardrailError(
                    f"Message bloqué par le filtre de sécurité."
                )

        # Vérification topics hors périmètre
        for topic, pattern in self._topics:
            if pattern.search(text):
                reply = (
                    f"Je suis désolé, mais ce sujet ({topic}) est en dehors de mon "
                    f"périmètre en tant qu'{self.persona_name}. "
                    f"Je suis ici pour vous aider sur des sujets professionnels. "
                    f"N'hésitez pas à me poser une autre question !"
                )
                raise TopicBlocked(topic=topic, polite_reply=reply)

        return text


class OutputGuardrails:
    """Post-traitement des réponses du LLM."""

    def process(self, text: str) -> str:
        """Retourne la réponse nettoyée."""
        return text.strip() # Nettoie les espaces superflus en début et fin de réponse