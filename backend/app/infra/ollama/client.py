from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import settings
from app.infra.ollama.errors import OllamaHTTPStatusError, OllamaNetworkError, OllamaTimeoutError
from app.infra.ollama.schemas import OllamaGenerateResponse


def normalize_ollama_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


class OllamaClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = normalize_ollama_base_url(base_url or settings.OLLAMA_BASE_URL)

    def generate(self, request_body: dict[str, Any], *, timeout_seconds: float) -> OllamaGenerateResponse:
        started = time.monotonic()
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json=request_body,
                timeout=httpx.Timeout(
                    timeout=timeout_seconds,
                    connect=10.0,
                    read=timeout_seconds,
                    write=30.0,
                    pool=10.0,
                ),
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            raise OllamaTimeoutError("Ollama request timed out.", elapsed_ms=elapsed_ms) from exc
        except httpx.HTTPStatusError as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            response = exc.response
            raise OllamaHTTPStatusError(
                "Ollama returned an unsuccessful HTTP status.",
                status_code=response.status_code if response is not None else None,
                response_text=response.text[:1000] if response is not None else "",
                elapsed_ms=elapsed_ms,
            ) from exc
        except httpx.HTTPError as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            raise OllamaNetworkError("Ollama request failed.", elapsed_ms=elapsed_ms) from exc

        return OllamaGenerateResponse(
            payload=response.json(),
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            response_text=response.text,
        )
