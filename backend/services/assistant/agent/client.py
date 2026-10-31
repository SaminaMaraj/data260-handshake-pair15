import json
import os
import urllib.request


class OllamaClient:
    """
    One client responsible for all communication with Ollama.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.base_url = (
            base_url
            or os.getenv(
                "OLLAMA_BASE_URL",
                "http://localhost:11434",
            )
        ).rstrip("/")

        self.model = (
            model
            or os.getenv(
                "OLLAMA_MODEL",
                "qwen3:8b",
            )
        )

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        response_format: str | None = None,
    ) -> dict:
        """
        Send messages and optional tool schemas to Ollama.

        response_format="json" asks Ollama for a JSON-only reply (used by
        memory consolidation). Returns the assistant message as a dictionary.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        if tools:
            payload["tools"] = tools

        if response_format == "json":
            payload["format"] = "json"

        request = urllib.request.Request(
            url=f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=180,
            ) as response:
                response_data = json.loads(
                    response.read().decode("utf-8")
                )

            return response_data.get(
                "message",
                {
                    "role": "assistant",
                    "content": "",
                },
            )

        except Exception as error:
            return {
                "role": "assistant",
                "content": f"Ollama request failed: {error}",
            }