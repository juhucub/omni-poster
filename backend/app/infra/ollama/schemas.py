from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OllamaGenerateResponse:
    payload: dict[str, Any]
    status_code: int
    elapsed_ms: int
    response_text: str
