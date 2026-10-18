from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

from openai import APIConnectionError, APIError, OpenAI, RateLimitError


def normalize_base_url(base_url: str) -> str:
    u = (base_url or "").strip().rstrip("/")
    if u.endswith("/chat/completions"):
        u = u[: -len("/chat/completions")]
    return u


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str = field(repr=False)
    model: str
    extra_body: dict = field(default_factory=dict)
    timeout_sec: float = 600.0
    max_attempts: int = 3



_CLIENTS: dict[tuple[str, str, float], OpenAI] = {}


def _client(cfg: LLMConfig) -> OpenAI:
    key = (normalize_base_url(cfg.base_url), cfg.api_key, cfg.timeout_sec)
    if key not in _CLIENTS:
        if not key[0]:
            raise ValueError(f"missing base_url for model {cfg.model!r}")
        _CLIENTS[key] = OpenAI(base_url=key[0], api_key=cfg.api_key or "EMPTY", timeout=cfg.timeout_sec, max_retries=1)
    return _CLIENTS[key]


def _backoff(attempt: int, base: float = 1.5, cap: float = 30.0) -> None:
    delay = min(cap, base * (2 ** attempt))
    time.sleep(delay * (0.7 + 0.6 * random.random()))


def _retryable(e: Exception) -> bool:
    if isinstance(e, (RateLimitError, APIConnectionError)):
        return True
    if isinstance(e, APIError):
        status = getattr(e, "status_code", None)
        return status is None or status == 429 or status >= 500
    msg = str(e).lower()
    return "429" in msg or "rate limit" in msg or "empty_response" in msg or "timed out" in msg


def _extract_text(resp: Any) -> str:
    try:
        msg = resp.choices[0].message
    except Exception:
        return ""
    c = getattr(msg, "content", None)
    if isinstance(c, str):
        return c.strip()
    if isinstance(c, list):
        parts = []
        for p in c:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                for k in ("text", "content"):
                    if isinstance(p.get(k), str):
                        parts.append(p[k])
        return "\n".join(parts).strip()
    return ""


def _drop_empty_text(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            kept = [p for p in c if not (isinstance(p, dict) and p.get("type") == "text" and not str(p.get("text") or "").strip())]
            m = {**m, "content": kept}
        elif isinstance(c, str) and not c.strip():
            m = {**m, "content": "(no answer)" if m.get("role") == "assistant" else "(empty)"}
        out.append(m)
    return out


def chat(
    cfg: LLMConfig,
    messages: list[dict],
    *,
    system: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    json_mode: bool = False,
) -> str:
    full = ([{"role": "system", "content": system}] if system else []) + list(messages)
    full = _drop_empty_text(full)
    kwargs: dict[str, Any] = dict(model=cfg.model, messages=full, temperature=temperature, max_tokens=max_tokens)
    if cfg.extra_body:
        kwargs["extra_body"] = cfg.extra_body
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    last: Exception | None = None
    for attempt in range(max(1, cfg.max_attempts)):
        try:
            resp = _client(cfg).chat.completions.create(**kwargs)
            text = _extract_text(resp)
            if not text:
                raise RuntimeError("empty_response")
            return text
        except Exception as e:
            msg = str(e).lower()
            if json_mode and "response_format" in msg:
                kwargs.pop("response_format", None)
                json_mode = False
                continue
            if not _retryable(e) or attempt == cfg.max_attempts - 1:
                last = e
                break
            last = e
            _backoff(attempt)
    raise last if last else RuntimeError("chat failed")

