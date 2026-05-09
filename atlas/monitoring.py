"""
atlas/monitoring.py Métriques légères et logging.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional


# Config du logger ici

def setup_logger(name: str = "atlas", level: str = "INFO") -> logging.Logger:
    """Configure et retourne le logger Atlas."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO)) # getattr pour convertir "INFO" en logging.INFO
    return logger


logger = setup_logger()


# Métriques d'échange et de session

@dataclass
class TurnMetrics:
    """Métriques d'un seul échange user <-> assistant."""
    turn_index: int
    input_chars: int
    output_chars: int
    latency_s: float
    model: str
    timestamp: float = field(default_factory=time.time)

    @property # @property pour calculer à la volée
    def chars_per_second(self) -> float:
        return self.output_chars / self.latency_s if self.latency_s > 0 else 0.0 # éviter la division par zéro


@dataclass
class SessionMetrics:
    """Agrégat des métriques pour toute la session."""
    turns: list[TurnMetrics] = field(default_factory=list)

    def record(self, metrics: TurnMetrics) -> None:
        self.turns.append(metrics)
        logger.debug(
            "Tour %d - latence=%.2fs | entrée=%d c | sortie=%d c | %.1f c/s", # log détaillé pour chaque tour
            metrics.turn_index,
            metrics.latency_s,
            metrics.input_chars,
            metrics.output_chars,
            metrics.chars_per_second,
        )

    def summary(self) -> str: # affichage synthétique à la fin de la session
        if not self.turns:
            return "Aucun échange enregistré."
        total_latency = sum(t.latency_s for t in self.turns)
        total_out = sum(t.output_chars for t in self.turns)
        avg_latency = total_latency / len(self.turns)
        lines = [
            f"  Nombre de tours     : {len(self.turns)}",
            f"  Latence totale      : {total_latency:.2f}s",
            f"  Latence moyenne     : {avg_latency:.2f}s",
            f"  Caractères générés  : {total_out}",
        ]
        return "\n".join(lines)


# Timer simple pour mesurer la durée d'une opération (ex: appel à l'API)

class Timer:
    """Chronomètre simple via context manager."""

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter() # perf_counter pour une mesure précise du temps écoulé
        return self

    def __exit__(self, *_) -> None:
        self.elapsed = time.perf_counter() - self._start

    @property
    def elapsed_s(self) -> float:
        return getattr(self, "elapsed", 0.0)