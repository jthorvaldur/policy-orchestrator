"""llm_router — single-file LLM provider router.

Copy or symlink into any repo. Reads env vars at import time.
No config files needed, no external deps beyond httpx + anthropic.

Usage:
    from llm_router import ask, ask_json, available_providers

    # Task-based routing (picks provider automatically)
    answer = ask("summarize this contract", task="summarize")

    # Explicit model
    answer = ask("analyze contradictions", model="claude-sonnet-4-6")

    # Get structured output
    data = ask_json("extract dates and amounts", task="extract")

    # Check what's available
    print(available_providers())

Environment variables:
    OLLAMA_BASE_URL       Local ollama (default: http://localhost:11434)
    ANTHROPIC_API_KEY     Anthropic Claude API
    OPENROUTER_API_KEY    OpenRouter multi-model gateway
    VAST_API_KEY          Vast.ai GPU instances
    VAST_ENDPOINT         Vast.ai instance URL (e.g. http://x.x.x.x:8000/v1)
    LEGAL_LOCAL_ONLY      Set to "1" to block all cloud providers
    LLM_ROUTER_VERBOSE    Set to "1" for debug logging to stderr
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Environment detection (at import time — no network calls)
# ---------------------------------------------------------------------------

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
VAST_KEY = os.environ.get("VAST_API_KEY", "")
VAST_ENDPOINT = os.environ.get("VAST_ENDPOINT", "")
LEGAL_LOCAL_ONLY = os.environ.get("LEGAL_LOCAL_ONLY", "") == "1"
VERBOSE = os.environ.get("LLM_ROUTER_VERBOSE", "") == "1"

# Lazy-loaded anthropic client
_anthropic_mod = None
_anthropic_client = None

# Ollama reachability cache
_ollama_ok: bool | None = None

# ---------------------------------------------------------------------------
# Task → complexity mapping
# ---------------------------------------------------------------------------

TASK_TIER: dict[str, str] = {
    "classify": "low", "extract": "low", "summarize": "low", "tag": "low",
    "analyze": "mid", "compare": "mid", "draft": "mid",
    "reason": "high", "plan": "high", "code": "high",
    "legal_analysis": "high", "contradict": "high",
}

TIER_DEFAULTS: dict[str, list[tuple[str, str]]] = {
    # (provider, model) pairs in priority order
    "low": [
        ("ollama", "llama3.1:8b"),
        ("openrouter", "meta-llama/llama-3.2-3b-instruct"),
    ],
    "mid": [
        ("anthropic", "claude-haiku-4-5"),
        ("openrouter", "mistralai/mistral-7b-instruct"),
        ("ollama", "llama3.1:8b"),
    ],
    "high": [
        ("anthropic", "claude-sonnet-4-6"),
        ("openrouter", "anthropic/claude-sonnet-4-6"),
        ("ollama", "llama3.1:8b"),
    ],
}

# Model name → provider inference
MODEL_PROVIDERS: dict[str, str] = {
    "claude-": "anthropic",
    "gpt-": "openai_compat",
    "meta-llama/": "openrouter",
    "mistralai/": "openrouter",
    "anthropic/": "openrouter",
    "google/": "openrouter",
}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    if VERBOSE:
        print(f"[llm_router] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Provider backends
# ---------------------------------------------------------------------------

def _check_ollama() -> bool:
    """Check if ollama is reachable (cached after first call)."""
    global _ollama_ok
    if _ollama_ok is not None:
        return _ollama_ok
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3.0)
        _ollama_ok = r.status_code == 200
    except Exception:
        _ollama_ok = False
    _log(f"ollama reachable: {_ollama_ok}")
    return _ollama_ok


def _ask_ollama(
    prompt: str,
    system: str = "",
    model: str = "llama3.1:8b",
    temperature: float = 0.1,
    max_tokens: int = 4000,
    timeout: float = 120.0,
) -> str:
    """Call local ollama via httpx."""
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if system:
        payload["system"] = system

    _log(f"ollama -> {model}")
    r = httpx.post(
        f"{OLLAMA_URL}/api/generate",
        json=payload,
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json().get("response", "").strip()


def _get_anthropic_client():
    """Lazy-load anthropic SDK and create client."""
    global _anthropic_mod, _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client
    import anthropic
    _anthropic_mod = anthropic
    _anthropic_client = anthropic.Anthropic()
    return _anthropic_client


def _ask_anthropic(
    prompt: str,
    system: str = "",
    model: str = "claude-sonnet-4-6",
    temperature: float = 0.1,
    max_tokens: int = 4000,
    timeout: float = 120.0,
) -> str:
    """Call Anthropic via the official SDK."""
    client = _get_anthropic_client()
    _log(f"anthropic -> {model}")
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    if temperature > 0:
        kwargs["temperature"] = temperature
    resp = client.messages.create(**kwargs, timeout=timeout)
    return resp.content[0].text


def _ask_openai_compat(
    prompt: str,
    system: str = "",
    model: str = "",
    api_key: str = "",
    base_url: str = "",
    temperature: float = 0.1,
    max_tokens: int = 4000,
    timeout: float = 120.0,
) -> str:
    """Call any OpenAI-compatible endpoint (OpenRouter, Vast, etc.)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    _log(f"openai-compat -> {model} @ {base_url}")
    r = httpx.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Provider availability
# ---------------------------------------------------------------------------

def _provider_available(provider: str) -> bool:
    """Check if a provider can be used right now."""
    if provider == "ollama":
        return _check_ollama()
    if provider == "anthropic":
        return bool(ANTHROPIC_KEY)
    if provider == "openrouter":
        return bool(OPENROUTER_KEY)
    if provider == "vast":
        return bool(VAST_KEY and VAST_ENDPOINT)
    return False


def available_providers() -> dict[str, bool]:
    """Return which providers are configured and reachable."""
    return {
        "ollama": _check_ollama(),
        "anthropic": bool(ANTHROPIC_KEY),
        "openrouter": bool(OPENROUTER_KEY),
        "vast": bool(VAST_KEY and VAST_ENDPOINT),
    }


# ---------------------------------------------------------------------------
# Model → provider resolution
# ---------------------------------------------------------------------------

def _infer_provider(model: str) -> str | None:
    """Infer provider from model name prefix."""
    for prefix, provider in MODEL_PROVIDERS.items():
        if model.startswith(prefix):
            return provider
    # Bare model names like "llama3.1:8b" are ollama
    if ":" in model or "/" not in model:
        return "ollama"
    return None


def _call_provider(
    provider: str,
    prompt: str,
    system: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> str:
    """Dispatch to the right backend."""
    if provider == "ollama":
        return _ask_ollama(prompt, system, model, temperature, max_tokens, timeout)
    if provider == "anthropic":
        return _ask_anthropic(prompt, system, model, temperature, max_tokens, timeout)
    if provider == "openrouter":
        return _ask_openai_compat(
            prompt, system, model, OPENROUTER_KEY,
            "https://openrouter.ai/api/v1", temperature, max_tokens, timeout,
        )
    if provider == "vast":
        return _ask_openai_compat(
            prompt, system, model, VAST_KEY,
            VAST_ENDPOINT, temperature, max_tokens, timeout,
        )
    raise ValueError(f"Unknown provider: {provider}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ask(
    prompt: str,
    system: str = "",
    task: str = "",
    model: str = "",
    temperature: float = 0.1,
    max_tokens: int = 4000,
    timeout: float = 120.0,
) -> str:
    """Route a prompt to the best available provider.

    Args:
        prompt: The user message.
        system: Optional system prompt.
        task: Task type for automatic routing (classify, extract, analyze, etc.).
        model: Explicit model name — overrides task-based routing.
        temperature: Sampling temperature (default 0.1 for determinism).
        max_tokens: Max response tokens.
        timeout: Request timeout in seconds.

    Returns:
        The model's text response.

    Raises:
        RuntimeError: If no provider is available for the request.
    """
    if LEGAL_LOCAL_ONLY and model:
        provider = _infer_provider(model)
        if provider and provider != "ollama":
            raise RuntimeError(
                f"LEGAL_LOCAL_ONLY=1 — cannot use cloud provider '{provider}'. "
                "Use a local ollama model or unset LEGAL_LOCAL_ONLY."
            )

    # Explicit model → infer provider
    if model:
        provider = _infer_provider(model)
        if provider and _provider_available(provider):
            return _call_provider(provider, prompt, system, model, temperature, max_tokens, timeout)
        if provider and not _provider_available(provider):
            _log(f"requested provider {provider} unavailable, falling back")

    # Task-based routing
    tier = TASK_TIER.get(task, "mid")
    candidates = TIER_DEFAULTS.get(tier, TIER_DEFAULTS["mid"])

    if LEGAL_LOCAL_ONLY:
        candidates = [(p, m) for p, m in candidates if p == "ollama"]

    errors = []
    for prov, default_model in candidates:
        if not _provider_available(prov):
            continue
        use_model = model or default_model
        try:
            return _call_provider(prov, prompt, system, use_model, temperature, max_tokens, timeout)
        except Exception as e:
            _log(f"{prov} failed: {e}")
            errors.append(f"{prov}: {e}")

    avail = available_providers()
    raise RuntimeError(
        f"No provider available for task={task!r} tier={tier!r}. "
        f"Providers: {avail}. Errors: {errors}"
    )


def ask_json(
    prompt: str,
    system: str = "",
    task: str = "",
    model: str = "",
    temperature: float = 0.1,
    max_tokens: int = 4000,
    timeout: float = 120.0,
) -> dict | list:
    """Like ask(), but extracts and parses JSON from the response.

    Handles models that wrap JSON in markdown code fences or extra text.
    """
    raw = ask(prompt, system, task, model, temperature, max_tokens, timeout)

    # Strip markdown code fences
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    raw = re.sub(r"\n?```\s*$", "", raw)

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Extract first JSON object or array
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = raw.find(start_char)
        end = raw.rfind(end_char)
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                continue

    raise ValueError(f"Could not extract JSON from response: {raw[:200]}...")


# ---------------------------------------------------------------------------
# Async variants
# ---------------------------------------------------------------------------

async def async_ask(
    prompt: str,
    system: str = "",
    task: str = "",
    model: str = "",
    temperature: float = 0.1,
    max_tokens: int = 4000,
    timeout: float = 120.0,
) -> str:
    """Async version of ask(). Uses httpx.AsyncClient for non-blocking calls."""
    if LEGAL_LOCAL_ONLY and model:
        provider = _infer_provider(model)
        if provider and provider != "ollama":
            raise RuntimeError(
                f"LEGAL_LOCAL_ONLY=1 — cannot use cloud provider '{provider}'."
            )

    # Explicit model
    if model:
        provider = _infer_provider(model)
        if provider and _provider_available(provider):
            return await _async_call(provider, prompt, system, model, temperature, max_tokens, timeout)

    # Task-based routing
    tier = TASK_TIER.get(task, "mid")
    candidates = TIER_DEFAULTS.get(tier, TIER_DEFAULTS["mid"])
    if LEGAL_LOCAL_ONLY:
        candidates = [(p, m) for p, m in candidates if p == "ollama"]

    errors = []
    for prov, default_model in candidates:
        if not _provider_available(prov):
            continue
        use_model = model or default_model
        try:
            return await _async_call(prov, prompt, system, use_model, temperature, max_tokens, timeout)
        except Exception as e:
            _log(f"async {prov} failed: {e}")
            errors.append(f"{prov}: {e}")

    raise RuntimeError(f"No provider available. Errors: {errors}")


async def async_ask_json(
    prompt: str,
    system: str = "",
    task: str = "",
    model: str = "",
    temperature: float = 0.1,
    max_tokens: int = 4000,
    timeout: float = 120.0,
) -> dict | list:
    """Async version of ask_json()."""
    raw = await async_ask(prompt, system, task, model, temperature, max_tokens, timeout)
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    raw = re.sub(r"\n?```\s*$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = raw.find(start_char)
        end = raw.rfind(end_char)
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"Could not extract JSON from response: {raw[:200]}...")


async def _async_call(
    provider: str,
    prompt: str,
    system: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> str:
    """Async dispatch to provider backends."""
    if provider == "anthropic":
        # anthropic SDK doesn't have native async — run sync in thread
        import asyncio
        return await asyncio.to_thread(
            _ask_anthropic, prompt, system, model, temperature, max_tokens, timeout
        )

    # For httpx-based providers, use AsyncClient
    async with httpx.AsyncClient(timeout=timeout) as client:
        if provider == "ollama":
            payload: dict[str, Any] = {
                "model": model, "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            }
            if system:
                payload["system"] = system
            r = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            r.raise_for_status()
            return r.json().get("response", "").strip()

        # openrouter / vast — OpenAI-compatible
        api_key = OPENROUTER_KEY if provider == "openrouter" else VAST_KEY
        base_url = "https://openrouter.ai/api/v1" if provider == "openrouter" else VAST_ENDPOINT
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        r = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
