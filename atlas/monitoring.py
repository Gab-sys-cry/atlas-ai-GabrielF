"""
atlas/monitoring.py -- Métriques, traces JSONL et logging structuré.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Callable

# Logger interne

def setup_logger(name: str = "atlas", level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s -- %(message)s", # timestamp + level + logger name
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


logger = setup_logger()



# Métriques en mémoire


@dataclass
class TurnMetrics:
    """Métriques d'un seul échange user <-> assistant."""
    turn_index: int
    input_chars: int
    output_chars: int
    latency_s: float
    model: str
    prompt_tokens: int = 0        # prompt_eval_count Ollama
    completion_tokens: int = 0    # eval_count Ollama
    timestamp: float = field(default_factory=time.time)

    @property
    def chars_per_second(self) -> float:
        return self.output_chars / self.latency_s if self.latency_s > 0 else 0.0


@dataclass
class SessionMetrics:
    """Agrégat des métriques pour toute la session."""
    turns: list[TurnMetrics] = field(default_factory=list)

    def record(self, metrics: TurnMetrics) -> None:
        self.turns.append(metrics)
        logger.debug(
            "Tour %d -- latence=%.2fs | %d pt | %d ct | %.1f c/s",
            metrics.turn_index,
            metrics.latency_s,
            metrics.prompt_tokens,
            metrics.completion_tokens,
            metrics.chars_per_second,
        )

    def summary(self) -> str:
        if not self.turns:
            return "Aucun échange enregistré."
        total_latency = sum(t.latency_s for t in self.turns)
        total_out = sum(t.output_chars for t in self.turns)
        total_pt = sum(t.prompt_tokens for t in self.turns)
        total_ct = sum(t.completion_tokens for t in self.turns)
        lines = [
            f"  Nombre de tours     : {len(self.turns)}",
            f"  Latence totale      : {total_latency:.2f}s",
            f"  Latence moyenne     : {total_latency/len(self.turns):.2f}s",
            f"  Prompt tokens total : {total_pt}",
            f"  Completion tokens   : {total_ct}",
            f"  Caractères générés  : {total_out}",
        ]
        return "\n".join(lines)



# Timer contextuel


class Timer:
    """Chronomètre simple via context manager."""

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_) -> None:
        self.elapsed = time.perf_counter() - self._start

    @property
    def elapsed_s(self) -> float:
        return getattr(self, "elapsed", 0.0)

# Trace JSONL -- une ligne par interaction

class TraceLogger:
    """
    Écrit une trace JSONL par interaction dans un fichier rotatif.
    """

    # Longueurs max stockées en clair
    USER_MSG_MAX    = 200
    ASSISTANT_MSG_MAX = 500

    def __init__(self, log_path: str | Path, session_id: str | None = None) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or uuid.uuid4().hex[:8]

    def write(
        self,
        *,
        model: str,
        user_message: str,
        assistant_message: str,
        latency_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        memory_hits: int = 0,
        guardrails_triggered: list[str] | None = None,
    ) -> None:
        """Écrit une ligne JSONL atomiquement."""
        record = {
            "timestamp":            datetime.now(timezone.utc).isoformat(),
            "session_id":           self.session_id,
            "model":                model,
            "prompt_tokens":        prompt_tokens,
            "completion_tokens":    completion_tokens,
            "latency_ms":           round(latency_ms),
            "user_message":         user_message[:self.USER_MSG_MAX],
            "assistant_message":    assistant_message[:self.ASSISTANT_MSG_MAX],
            "memory_hits":          memory_hits,
            "guardrails_triggered": guardrails_triggered or [],
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# Décorateur

def traced(log_path: str | Path, session_id: str | None = None):
    """
    Décorateur qui trace automatiquement un appel LLM dans un fichier JSONL.
    """
    tracer = TraceLogger(log_path, session_id)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            latency_ms = (time.perf_counter() - start) * 1000

            tracer.write(
                model=result.get("model", "unknown"),
                user_message=result.get("user_message", ""),
                assistant_message=result.get("response", ""),
                latency_ms=latency_ms,
                prompt_tokens=result.get("prompt_tokens", 0),
                completion_tokens=result.get("completion_tokens", 0),
                memory_hits=result.get("memory_hits", 0),
                guardrails_triggered=result.get("guardrails_triggered", []),
            )
            return result

        return wrapper
    return decorator