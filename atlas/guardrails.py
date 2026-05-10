"""
atlas/guardrails.py -- Filtres et garde-fous sur les entrées/sorties.
"""
from __future__ import annotations

import re
import time
from collections import deque

# Exceptions

class GuardrailError(Exception):
    """Règle technique violée -- message bloqué, rien n'est envoyé au LLM."""

class TopicBlocked(Exception):
    """Sujet hors périmètre -- refus poli généré localement."""
    def __init__(self, topic: str, polite_reply: str) -> None:
        super().__init__(polite_reply)
        self.topic = topic
        self.polite_reply = polite_reply

class PIIMasked(Exception):
    """
    Levée quand une PII a été détectée et masquée.
    """
    def __init__(self, original: str, cleaned: str, triggered: list[str]) -> None:
        super().__init__(f"PII masquée : {triggered}")
        self.original_text = original
        self.cleaned_text  = cleaned
        self.triggered     = triggered



# Patterns PII

#regles recuperées sur le web, pas parfaites mais couvrent les cas courants
_PII_RULES: list[tuple[str, re.Pattern, str]] = [
    # (nom_règle, pattern, remplacement)
    (
        "pii_card",
        re.compile(r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12})\b"),
        "[CARTE_MASQUÉE]",
    ),
    (
        "pii_email",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "[EMAIL_MASQUÉ]",
    ),
    (
        "pii_iban",
        re.compile(r"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{4}[0-9]{7}(?:[A-Z0-9]?){0,16}\b"),
        "[IBAN_MASQUÉ]",
    ),
    (
        "pii_secu",
        # Numéro de sécurité sociale français : 13 chiffres + clé 2 chiffres
        re.compile(r"\b[12][0-9]{2}(?:0[1-9]|1[0-2]|20)[0-9]{2}[0-9]{3}[0-9]{3}(?:[0-9]{2})?\b"),
        "[SECU_MASQUÉE]",
    ),
]

# Patterns de prompt injection
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"ignore\s+(all\s+)?previous\s+instructions?",
        r"tu\s+es\s+maintenant",
        r"oublie\s+(tout|tes\s+instructions)",
        r"<\|system\|>",
        r"\[INST\]",
        r"disregard\s+(all\s+)?previous",
        r"new\s+persona",
        r"act\s+as\s+(?:if\s+you\s+(?:are|were)|a)",
        r"jailbreak",
        r"dan\s+mode",
    ]
]



# Guardrails d'entrée


class InputGuardrails:
    """
    Valide et nettoie les messages utilisateur avant envoi au LLM.
    """

    def __init__(
        self,
        max_length: int = 4000,
        blocked_patterns: list[str] | None = None,
        blocked_topics: list[str] | None = None,
        persona_name: str = "Atlas",
        pii_detection: bool = True,
        prompt_injection: bool = True,
        rate_limit_enabled: bool = True,
        rate_limit_max: int = 20,
        rate_limit_window_s: float = 60.0,
    ) -> None:
        self.max_length  = max_length
        self.persona_name = persona_name
        self.pii_detection     = pii_detection
        self.prompt_injection  = prompt_injection
        self.rate_limit_enabled = rate_limit_enabled
        self.rate_limit_max    = rate_limit_max
        self.rate_limit_window_s = rate_limit_window_s

        # Regex techniques bloquantes
        self._patterns = [re.compile(p, re.IGNORECASE) for p in (blocked_patterns or [])]

        # Topics hors périmètre : \b pour éviter les faux positifs
        self._topics: list[tuple[str, re.Pattern]] = [
            (topic, re.compile(rf"\b{re.escape(topic)}\b", re.IGNORECASE))
            for topic in (blocked_topics or [])
        ]

        # Fenêtre glissante pour le rate limiting
        self._timestamps: deque[float] = deque()

    # Point d'entrée principal

    def validate(self, text: str) -> tuple[str, list[str]]:
        """
        Valide et retourne (texte_nettoyé, règles_déclenchées).
        """
        triggered: list[str] = []
        text = text.strip()

        # Vide
        if not text:
            raise GuardrailError("Le message est vide.")

        # Longueur max
        if len(text) > self.max_length:
            raise GuardrailError(
                f"Message trop long ({len(text)} caractères, max {self.max_length})."
            )

        # Rate limiting
        if self.rate_limit_enabled:
            self._check_rate_limit()  # lève GuardrailError si dépassé

        # Prompt injection
        if self.prompt_injection:
            for pattern in _INJECTION_PATTERNS:
                if pattern.search(text):
                    triggered.append("prompt_injection")
                    raise GuardrailError(
                        "Tentative d'injection de prompt détectée et bloquée."
                    )

        # Patterns techniques bloquants
        for pattern in self._patterns:
            if pattern.search(text):
                raise GuardrailError("Message bloqué par le filtre de sécurité.")

        # Topics hors périmètre
        for topic, pattern in self._topics:
            if pattern.search(text):
                reply = (
                    f"Je suis désolé, mais ce sujet ({topic}) est en dehors de mon "
                    f"périmètre en tant qu'{self.persona_name}. "
                    f"Je suis ici pour vous aider sur des sujets professionnels. "
                    f"N'hésitez pas à me poser une autre question !"
                )
                raise TopicBlocked(topic=topic, polite_reply=reply)

        # Masquage PII (ne bloque pas -- retourne le texte nettoyé)
        if self.pii_detection:
            text, pii_triggered = _mask_pii(text)
            triggered.extend(pii_triggered)

        return text, triggered

    
    # Rate limit

    def _check_rate_limit(self) -> None:
        now = time.monotonic()
        # Supprimer les timestamps hors fenêtre
        while self._timestamps and self._timestamps[0] < now - self.rate_limit_window_s:
            self._timestamps.popleft()

        if len(self._timestamps) >= self.rate_limit_max:
            wait = round(self.rate_limit_window_s - (now - self._timestamps[0]), 1)
            raise GuardrailError(
                f"Trop de requêtes ({self.rate_limit_max}/{int(self.rate_limit_window_s)}s). "
                f"Réessayez dans ~{wait}s."
            )
        self._timestamps.append(now)

# Guardrails de sortie

class OutputGuardrails:
    """
    Post-traitement des réponses du LLM.
    """

    def __init__(self, pii_detection: bool = True) -> None:
        self.pii_detection = pii_detection

    def process(self, text: str) -> tuple[str, list[str]]:
        """
        Retourne (texte_nettoyé, règles_déclenchées).
        """
        triggered: list[str] = []
        text = text.strip()

        if self.pii_detection:
            text, pii_triggered = _mask_pii(text)
            triggered.extend([f"output_{r}" for r in pii_triggered])

        return text, triggered


# Fonction utilitaire de masquage PII (partagée entrée/sortie)

def _mask_pii(text: str) -> tuple[str, list[str]]:
    """
    Applique tous les patterns PII sur le texte.
    Retourne (texte_masqué, liste_règles_déclenchées).
    """
    triggered: list[str] = []
    for rule_name, pattern, replacement in _PII_RULES:
        new_text, count = pattern.subn(replacement, text)
        if count > 0:
            triggered.append(rule_name)
            text = new_text
    return text, triggered