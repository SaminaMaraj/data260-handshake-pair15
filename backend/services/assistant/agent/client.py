import json
import os
import time
import urllib.request


def usage_from(data: dict, started: float, num_ctx: int) -> dict:
    """Tokens and timings from an Ollama /api/chat response.

    Ollama reports durations in nanoseconds: total_duration covers loading
    the model, reading the prompt and generating; the rest of the wall time
    was spent waiting (Ollama's queue and the network).
    """
    def ms(key):
        return round(data.get(key, 0) / 1e6, 1)

    wall_ms = round((time.perf_counter() - started) * 1000, 1)
    prompt = int(data.get("prompt_eval_count") or 0)
    completion = int(data.get("eval_count") or 0)
    return {
        "prompt_tokens": prompt, "completion_tokens": completion,
        "context_window": num_ctx, "estimated": False,
        "wall_ms": wall_ms, "inference_ms": ms("total_duration"),
        "load_ms": ms("load_duration"), "prompt_eval_ms": ms("prompt_eval_duration"),
        "eval_ms": ms("eval_duration"),
        "queue_wait_ms": round(max(0.0, wall_ms - ms("total_duration")), 1),
    }


class OllamaClient:
    """
    One client responsible for all communication with Ollama.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        num_ctx: int | None = None,
        think: bool | None = None,
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

        # Seconds per model call. The agent loop lowers it to whatever is
        # left of the request deadline (Guardrail 7).
        self.timeout = float(timeout or os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))

        # Context window requested from Ollama; token tracking reports usage
        # against it (Part 6). qwen3:8b supports far more, but a fixed
        # window makes "context %" meaningful and predictable.
        self.num_ctx = int(num_ctx or os.getenv("OLLAMA_NUM_CTX", "8192"))

        # qwen3 "thinking": None = the model's default. False skips the hidden
        # reasoning tokens, which matters for long JSON jobs (consolidation).
        self.think = think

        # Filled after every call: tokens and Ollama's own timings.
        self.last_usage: dict | None = None

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

        payload["options"] = {"num_ctx": self.num_ctx}

        if self.think is not None:
            payload["think"] = self.think

        request = urllib.request.Request(
            url=f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        self.last_usage = None
        started = time.perf_counter()

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                response_data = json.loads(
                    response.read().decode("utf-8")
                )

            self.last_usage = usage_from(response_data, started, self.num_ctx)

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