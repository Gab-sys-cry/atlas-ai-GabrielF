"""
atlas/llm.py -- Wrapper bas niveau pour l'API Ollama.
"""
from __future__ import annotations

import json

import httpx


class OllamaError(Exception):
    """Erreur levée lors d'un appel à l'API Ollama."""


# Type de retour de chat()
ChatResult = dict  # {"response": str, "prompt_tokens": int, "completion_tokens": int}


class OllamaClient:
    """
    Client HTTP direct vers Ollama (/api/chat).
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    # Méthodes publiques

    def chat(
        self,
        messages: list[dict],
        stream: bool = True,
        options: dict | None = None,
    ) -> ChatResult:
        """
        Envoie un historique de messages et retourne un dict :
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": options or {},
        }
        url = f"{self.base_url}/api/chat"

        try:
            if stream:
                return self._stream_chat(url, payload)
            else:
                return self._blocking_chat(url, payload)
        except httpx.TimeoutException as exc:
            raise OllamaError(
                f"Timeout ({self.timeout}s) atteint -- serveur trop lent ou modèle trop lourd."
            ) from exc
        except httpx.ConnectError as exc:
            raise OllamaError(
                f"Impossible de joindre Ollama sur {self.base_url}. "
                "Vérifiez que le serveur est démarré (`ollama serve`)."
            ) from exc

    def list_models(self) -> list[dict]:
        """Retourne la liste des modèles disponibles (GET /api/tags)."""
        try:
            resp = self._client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            return resp.json().get("models", [])
        except httpx.HTTPError as exc:
            raise OllamaError(f"Erreur lors de la récupération des modèles : {exc}") from exc

    def health_check(self) -> bool:
        """Retourne True si le serveur répond correctement."""
        try:
            resp = self._client.get(self.base_url, timeout=5)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    # Méthodes internes
    
    def _stream_chat(self, url: str, payload: dict) -> ChatResult:
        """
        Streaming NDJSON.
        Le dernier chunk (done=True) contient prompt_eval_count et eval_count.
        """
        full_response = ""
        prompt_tokens = 0
        completion_tokens = 0

        with self._client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                token = chunk.get("message", {}).get("content", "")
                if token:
                    print(token, end="", flush=True)
                    full_response += token

                if chunk.get("done", False):
                    # Le chunk final contient les compteurs de tokens
                    prompt_tokens     = chunk.get("prompt_eval_count", 0)
                    completion_tokens = chunk.get("eval_count", 0)
                    break

        print()  # saut de ligne final
        return {
            "response":          full_response,
            "prompt_tokens":     prompt_tokens,
            "completion_tokens": completion_tokens,
        }

    def _blocking_chat(self, url: str, payload: dict) -> ChatResult:
        """Appel bloquant sans streaming."""
        response = self._client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return {
            "response":          data.get("message", {}).get("content", ""),
            "prompt_tokens":     data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
        }

    def __del__(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass