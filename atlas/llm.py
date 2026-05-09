"""
atlas/llm.py  Wrapper bas niveau pour l'API Ollama.

Utilise uniquement httpx.
Toute configuration (modèle, timeout, url) vient de config/default.yml.
"""
from __future__ import annotations

import json

import httpx


class OllamaError(Exception):
    """Erreur levée lors d'un appel à l'API Ollama."""


class OllamaClient:
    """
    Client HTTP direct vers Ollama (/api/chat).

    Tous les paramètres sont obligatoires : les valeurs par défaut
    sont définies une seule fois dans config/default.yml.

    Paramètres
    ----------
    base_url : str
        URL de base du serveur Ollama.
    model : str
        Nom du modèle tel que retourné par /api/tags.
    timeout : float
        Timeout en secondes pour chaque requête HTTP.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float,
    ) -> None:
        self.base_url = base_url.rstrip("/") # rstrip pour éviter les doubles slash
        self.model = model
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)


    # Mthodes publiques

    def chat(
        self,
        messages: list[dict],
        stream: bool = True,
        options: dict | None = None,
    ) -> str:
        """
        Envoie un historique de messages et retourne la réponse complète.

        En mode streaming, print chaque token dès réception et renvoie
        la chaîne complète à la fin.
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
                f"Timeout ({self.timeout}s) atteint, serveur trop lent ou modèle trop lourd."
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

    # Méthodes privées

    def _stream_chat(self, url: str, payload: dict) -> str:
        """Streaming NDJSON : chaque ligne est un objet JSON partiel.""" # NDJSON = Newline Delimited JSON
        full_response = ""

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
                    print(token, end="", flush=True) # flush pour forcer l'affichage immédiat
                    full_response += token

                if chunk.get("done", False):
                    break

        print()  # saut de ligne final
        return full_response

    def _blocking_chat(self, url: str, payload: dict) -> str:
        """Appel bloquant sans streaming."""
        response = self._client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "")

    def __del__(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass