from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any


# OpenAI gpt-4o list prices (USD per 1K tokens). Azure pricing is typically
# the same or within ~10% by region. Treats every input token as uncached;
# real cost may be lower with prompt-caching on supported deployments.
GPT_4O_INPUT_PRICE_PER_1K = 0.0025   # $2.50 per 1M tokens
GPT_4O_OUTPUT_PRICE_PER_1K = 0.01    # $10.00 per 1M tokens


def estimate_cost_usd(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    if provider == "azure" and "gpt-4o" in (model or "").lower():
        return (
            prompt_tokens * GPT_4O_INPUT_PRICE_PER_1K / 1000.0
            + completion_tokens * GPT_4O_OUTPUT_PRICE_PER_1K / 1000.0
        )
    return 0.0


def _empty_totals() -> dict[str, Any]:
    return {
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "total_calls": 0,
    }


class LLMUsageTracker:
    def __init__(
        self,
        persist_path: Path,
        *,
        initial_totals: dict[str, Any] | None = None,
        on_save: Callable[[dict[str, Any]], None] | None = None,
    ):
        self._path = Path(persist_path)
        self._on_save = on_save
        self._lock = threading.Lock()
        self._totals = self._hydrate(initial_totals)
        self._last_call: dict[str, Any] | None = None

    def _hydrate(self, initial_totals: dict[str, Any] | None) -> dict[str, Any]:
        """Load from initial_totals (SQLite) if provided, else fall back to JSON file."""
        source = initial_totals if isinstance(initial_totals, dict) else self._load_json()
        out = _empty_totals()
        out["total_prompt_tokens"] = int(source.get("total_prompt_tokens", 0) or 0)
        out["total_completion_tokens"] = int(source.get("total_completion_tokens", 0) or 0)
        out["total_tokens"] = int(source.get("total_tokens", 0) or 0)
        out["total_cost_usd"] = float(source.get("total_cost_usd", 0.0) or 0.0)
        out["total_calls"] = int(source.get("total_calls", 0) or 0)
        return out

    def _load_json(self) -> dict[str, Any]:
        if not self._path.exists():
            return _empty_totals()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _empty_totals()
        return data if isinstance(data, dict) else _empty_totals()

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._totals, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def record_call(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> dict[str, Any]:
        cost = estimate_cost_usd(provider, model, prompt_tokens, completion_tokens)
        total_tokens = prompt_tokens + completion_tokens
        call_record = {
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost,
        }
        with self._lock:
            self._totals["total_prompt_tokens"] += prompt_tokens
            self._totals["total_completion_tokens"] += completion_tokens
            self._totals["total_tokens"] += total_tokens
            self._totals["total_cost_usd"] += cost
            self._totals["total_calls"] += 1
            self._last_call = call_record
            self._save_locked()
            if self._on_save is not None:
                try:
                    self._on_save(dict(self._totals))
                except Exception:
                    pass
        return call_record

    def get_totals(self) -> dict[str, Any]:
        with self._lock:
            result = dict(self._totals)
            if self._last_call is not None:
                result["last_call"] = dict(self._last_call)
            return result
