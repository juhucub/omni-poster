from __future__ import annotations


class OllamaInfraError(RuntimeError):
    """Base error for low-level Ollama HTTP failures."""

    def __init__(self, message: str, *, elapsed_ms: int | None = None) -> None:
        super().__init__(message)
        self.elapsed_ms = elapsed_ms


class OllamaTimeoutError(OllamaInfraError):
    """Raised when an Ollama HTTP request times out."""


class OllamaNetworkError(OllamaInfraError):
    """Raised when an Ollama HTTP request fails before a response is usable."""


class OllamaHTTPStatusError(OllamaInfraError):
    """Raised when Ollama returns a non-2xx HTTP status."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_text: str = "",
        elapsed_ms: int | None = None,
    ) -> None:
        super().__init__(message, elapsed_ms=elapsed_ms)
        self.status_code = status_code
        self.response_text = response_text
