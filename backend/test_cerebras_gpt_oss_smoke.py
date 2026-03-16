"""Quick smoke test for Groq GPT-OSS connectivity.

Run:
  python test_cerebras_gpt_oss_smoke.py
    python test_cerebras_gpt_oss_smoke.py --model openai/gpt-oss-20b --prompt "Say hello"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import httpx

from config import settings
from services.ai_service import cerebras_chat


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke test Groq GPT-OSS model")
    parser.add_argument("--model", default="openai/gpt-oss-20b", help="Model name to test")
    parser.add_argument("--prompt", default="Reply with exactly: GROQ_GPT_OSS_OK", help="Prompt for the model")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--max-tokens", type=int, default=80, dest="max_tokens", help="Max completion tokens")
    parser.add_argument("--list-models", action="store_true", help="List models available to the configured key")
    parser.add_argument("--auto-model", action="store_true", help="Auto-pick a GPT-OSS model from available models")
    return parser


async def _run(model: str, prompt: str, temperature: float, max_tokens: int) -> int:
    print("=== Groq GPT-OSS Smoke Test ===")
    print(f"API URL: {settings.GROQ_API_URL}")
    print(f"Configured keys: {len(settings.GROQ_API_KEYS)}")
    print(f"Model: {model}")

    if not settings.GROQ_API_KEYS:
        print("FAIL: No Groq API key configured in environment.")
        return 2

    messages = [
        {"role": "system", "content": "You are a strict API connectivity test assistant."},
        {"role": "user", "content": prompt},
    ]

    started = time.perf_counter()
    try:
        resp = await cerebras_chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        print(f"FAIL: Request error: {exc}")
        return 1

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    content = (
        resp.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )

    print(f"Latency: {elapsed_ms} ms")
    print(f"Response id: {resp.get('id', 'n/a')}")
    print(f"Output: {content or '<empty>'}")

    usage = resp.get("usage")
    if usage:
        print("Usage:")
        print(json.dumps(usage, indent=2))

    if not content:
        print("FAIL: Empty model output")
        return 1

    print("PASS: Groq GPT-OSS call succeeded.")
    return 0


async def _list_models() -> tuple[int, list[str]]:
    if not settings.GROQ_API_KEYS:
        print("FAIL: No Groq API key configured in environment.")
        return 2, []

    key = settings.GROQ_API_KEYS[0]
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )

    if resp.status_code >= 400:
        print(f"FAIL: models endpoint returned {resp.status_code}: {resp.text}")
        return 1, []

    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    rows = data.get("data", []) if isinstance(data, dict) else []
    model_ids = [r.get("id") for r in rows if isinstance(r, dict) and r.get("id")]

    print(f"Available models: {len(model_ids)}")
    for m in model_ids:
        print(f"- {m}")
    return 0, model_ids


def main() -> int:
    args = _build_parser().parse_args()

    async def _main() -> int:
        models: list[str] = []
        if args.list_models or args.auto_model:
            code, models = await _list_models()
            if code != 0:
                return code
            if args.list_models and not args.auto_model:
                return 0

        model = args.model
        if args.auto_model:
            gpt_oss_candidates = [m for m in models if "gpt-oss" in m.lower()]
            if not gpt_oss_candidates:
                print("FAIL: No GPT-OSS model found in available model list.")
                return 1
            model = gpt_oss_candidates[0]
            print(f"Auto-selected model: {model}")

        return await _run(model, args.prompt, args.temperature, args.max_tokens)

    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
