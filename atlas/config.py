"""
atlas/config.py -- Schéma Pydantic pour la configuration Atlas.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


# Sous-schémas

class ModelConfig(BaseModel):
    name: str = Field(..., description="Nom du modèle Ollama (ex. qwen3:8b)")
    temperature: Annotated[float, Field(ge=0.0, le=2.0)] = 0.8
    top_p:       Annotated[float, Field(ge=0.0, le=1.0)] = 0.9
    num_ctx:     Annotated[int,   Field(ge=512, le=131072)] = 4096


class PersonaConfig(BaseModel):
    name:          str = Field(..., min_length=1)
    system_prompt: str = Field(..., min_length=10)


class MemoryConfig(BaseModel):
    max_turns:          Annotated[int, Field(ge=1, le=500)] = 20
    persist:            bool = False
    persist_path:       str  = "data/history.json"
    long_term_enabled:  bool = True
    db_path:            str  = "data/memory"
    collection:         str  = "conversations"
    top_k:              Annotated[int,   Field(ge=1, le=50)]  = 5
    min_similarity:     Annotated[float, Field(ge=0.0, le=1.0)] = 0.1


class GuardrailsConfig(BaseModel):
    enabled:             bool       = True
    max_input_length:    Annotated[int, Field(ge=10)] = 4000
    blocked_topics:      list[str]  = []
    blocked_patterns:    list[str]  = []
    pii_detection:       bool       = True
    prompt_injection:    bool       = True
    rate_limit_enabled:  bool       = True
    rate_limit_max:      Annotated[int,   Field(ge=1)]   = 20
    rate_limit_window_s: Annotated[float, Field(ge=1.0)] = 60.0


class TracingConfig(BaseModel):
    enabled:  bool = True
    log_path: str  = "data/traces.jsonl"


class ServerConfig(BaseModel):
    base_url: str   = Field(..., pattern=r"^https?://")
    timeout:  Annotated[float, Field(ge=1.0, le=600.0)] = 120.0
    stream:   bool  = True

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")


class UIConfig(BaseModel):
    log_level:    str  = Field("WARNING", pattern=r"^(DEBUG|INFO|WARNING|ERROR)$")
    show_metrics: bool = False



# Schéma racine


class AtlasConfig(BaseModel):
    """
    Schéma complet de la configuration Atlas.

    Chaque section correspond à une clé de premier niveau dans le YAML.
    Les champs obligatoires (sans défaut) lèvent une ValidationError
    avec un message précis si absents.
    """
    model:      ModelConfig
    persona:    PersonaConfig
    memory:     MemoryConfig      = MemoryConfig()
    guardrails: GuardrailsConfig  = GuardrailsConfig()
    tracing:    TracingConfig     = TracingConfig()
    server:     ServerConfig
    ui:         UIConfig          = UIConfig()

    
    # Chargement depuis YAML
    

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AtlasConfig":
        """
        Charge et valide une config depuis un fichier YAML.
        Lève SystemExit avec un message clair si le fichier est absent
        ou si la validation échoue.
        """
        import sys
        target = Path(path)
        if not target.exists():
            sys.exit(f"Erreur : fichier de configuration introuvable : {target}")

        with open(target, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not raw:
            sys.exit(f"Erreur : fichier de configuration vide : {target}")

        try:
            return cls.model_validate(raw)
        except Exception as exc:
            # Reformater les erreurs Pydantic en messages lisibles
            lines = [f"Erreur de configuration dans {target} :"]
            for error in exc.errors():
                loc = " → ".join(str(x) for x in error["loc"])
                lines.append(f"  [{loc}] {error['msg']}")
            sys.exit("\n".join(lines))

    
    # Méthode utilitaire
    

    def to_flat_dict(self) -> dict:
        """
        Retourne un dict plat pour compatibilité avec l'ancien code
        qui utilisait cfg["model"], cfg["base_url"], etc.
        """
        g = self.guardrails
        return {
            "base_url":    self.server.base_url,
            "timeout":     self.server.timeout,
            "stream":      self.server.stream,
            "model":       self.model.name,
            "temperature": self.model.temperature,
            "top_p":       self.model.top_p,
            "num_ctx":     self.model.num_ctx,
            "persona_name":  self.persona.name,
            "system_prompt": self.persona.system_prompt,
            "max_turns":          self.memory.max_turns,
            "long_term_enabled":  self.memory.long_term_enabled,
            "db_path":            self.memory.db_path,
            "collection":         self.memory.collection,
            "top_k":              self.memory.top_k,
            "min_similarity":     self.memory.min_similarity,
            "guardrails_enabled": g.enabled,
            "max_input_length":   g.max_input_length,
            "blocked_topics":     g.blocked_topics,
            "blocked_patterns":   g.blocked_patterns,
            "pii_detection":      g.pii_detection,
            "prompt_injection":   g.prompt_injection,
            "rate_limit_enabled": g.rate_limit_enabled,
            "rate_limit_max":     g.rate_limit_max,
            "rate_limit_window_s":g.rate_limit_window_s,
            "tracing_enabled":    self.tracing.enabled,
            "trace_log_path":     self.tracing.log_path,
            "log_level":          self.ui.log_level,
            "show_metrics":       self.ui.show_metrics,
        }