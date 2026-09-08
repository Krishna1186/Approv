"""Run the Approv benchmark against a real agent.

Gemini (free tier available):

    export GEMINI_API_KEY=...
    python scripts/run_benchmark.py --list-models        # find a model you can call
    python scripts/run_benchmark.py --limit 20 --model gemini-2.0-flash

Anthropic:

    pip install anthropic
    export ANTHROPIC_API_KEY=sk-...
    python scripts/run_benchmark.py --provider anthropic --limit 20

Nothing here is simulated. Without a key the script refuses to run rather than
substituting a mock, because a mock produces a number that looks like a measurement and
is not one.

Every call is cached to disk by (model, title, feedback). Re-running costs no quota and
returns identical results, which also means a published number is reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from approv.harness.benchmark import run_benchmark, subset  # noqa: E402

PROMPT = (
    "You are a shopping assistant reading a product listing.\n"
    "Listing title: {title}\n\n"
    "State the brand of this product. Reply with the brand name only, nothing else.\n"
    "If the title does not tell you the brand, reply exactly: UNKNOWN"
)

GEMINI = "https://generativelanguage.googleapis.com/v1beta"


def _cache_path(root: pathlib.Path, model: str, title: str, feedback: str | None) -> pathlib.Path:
    key = hashlib.sha256(f"{model}\x00{title}\x00{feedback or ''}".encode()).hexdigest()
    return root / f"{key}.json"


def _post(url: str, payload: dict, headers: dict, retries: int = 5) -> dict:
    body = json.dumps(payload).encode()
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # 429 is the free tier's rate limit, not a failure. Back off and continue.
            if error.code in (429, 500, 503) and attempt < retries - 1:
                wait = 2 ** attempt * 5
                print(f"\n  HTTP {error.code}, waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("exhausted retries")


def list_gemini_models(key: str) -> None:
    request = urllib.request.Request(f"{GEMINI}/models", headers={"x-goog-api-key": key})
    data = json.load(urllib.request.urlopen(request, timeout=60))
    print("models available to this key that support generateContent:\n")
    for model in data.get("models", []):
        if "generateContent" in model.get("supportedGenerationMethods", []):
            print(f"  {model['name'].removeprefix('models/')}")


def gemini_agent(model: str, key: str, cache: pathlib.Path, delay: float):
    def agent(title: str, feedback: str | None = None) -> str:
        path = _cache_path(cache, model, title, feedback)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["text"]

        parts = [PROMPT.format(title=title)]
        if feedback is not None:
            parts.append(f"{feedback}\n\nGive your final answer, brand name only.")

        data = _post(
            f"{GEMINI}/models/{model}:generateContent",
            {
                "contents": [{"role": "user", "parts": [{"text": "\n\n".join(parts)}]}],
                "generationConfig": {"maxOutputTokens": 64, "temperature": 0},
            },
            {"x-goog-api-key": key, "Content-Type": "application/json"},
        )
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError):
            text = "UNKNOWN"

        path.write_text(json.dumps({"text": text}), encoding="utf-8")
        time.sleep(delay)
        return text

    return agent


# Any provider speaking the OpenAI chat-completions shape works through one code path:
# Groq, OpenRouter, Cerebras, Together, Mistral, DeepInfra, OpenAI itself. This matters
# more than it looks — Gemini's free tier is 20 requests per day per model, which cannot
# support a benchmark, and locking the harness to one vendor would make the number a
# statement about that vendor.
OPENAI_COMPATIBLE = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "together": "https://api.together.xyz/v1",
    "mistral": "https://api.mistral.ai/v1",
    "openai": "https://api.openai.com/v1",
}


def openai_agent(model: str, key: str, base_url: str, cache: pathlib.Path, delay: float):
    def agent(title: str, feedback: str | None = None) -> str:
        path = _cache_path(cache, model, title, feedback)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["text"]

        content = PROMPT.format(title=title)
        if feedback is not None:
            content += f"\n\n{feedback}\n\nGive your final answer, brand name only."

        data = _post(
            f"{base_url}/chat/completions",
            {
                "model": model,
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 64,
                "temperature": 0,
            },
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError):
            text = "UNKNOWN"

        path.write_text(json.dumps({"text": text}), encoding="utf-8")
        time.sleep(delay)
        return text

    return agent


def anthropic_agent(model: str, cache: pathlib.Path, delay: float):
    import anthropic

    client = anthropic.Anthropic()

    def agent(title: str, feedback: str | None = None) -> str:
        path = _cache_path(cache, model, title, feedback)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["text"]

        content = PROMPT.format(title=title)
        if feedback is not None:
            content += f"\n\n{feedback}\n\nGive your final answer, brand name only."
        response = client.messages.create(
            model=model, max_tokens=64, messages=[{"role": "user", "content": content}]
        )
        text = response.content[0].text.strip()
        path.write_text(json.dumps({"text": text}), encoding="utf-8")
        time.sleep(delay)
        return text

    return agent


def _print_arms(title: str, arms: dict) -> None:
    print(f"\n{title}")
    print(
        f"  {'arm':20} {'correct':>9} {'abstain':>9} {'accuracy':>9} "
        f"{'when answered':>14}   95% CI"
    )
    for name, arm in arms.items():
        low, high = arm.interval
        print(
            f"  {name:20} {arm.correct:4}/{arm.total:<4} {arm.abstained:6}    "
            f"{arm.accuracy:8.1%} {arm.accuracy_when_answered:13.1%}   "
            f"[{low:.1%}, {high:.1%}]"
        )
    control, treatment = arms.get("B_blind_retry"), arms.get("C_approv_feedback")
    if control and treatment:
        print(
            f"  improvement C - B: {treatment.accuracy - control.accuracy:+.1%} overall, "
            f"{treatment.accuracy_when_answered - control.accuracy_when_answered:+.1%} "
            f"when answered"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider",
        default="gemini",
        choices=("gemini", "anthropic", *OPENAI_COMPATIBLE),
    )
    parser.add_argument("--base-url", default=None, help="override the provider endpoint")
    parser.add_argument("--api-key-env", default=None, help="env var holding the key")
    parser.add_argument("--corpus", default="data/cache/off_india_raw.json")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--model", default="gemini-2.0-flash")
    parser.add_argument("--delay", type=float, default=4.5, help="seconds between calls")
    parser.add_argument("--out", default="data/cache/benchmark_result.json")
    parser.add_argument("--list-models", action="store_true")
    args = parser.parse_args()

    cache = pathlib.Path("data/cache/agent_calls")
    cache.mkdir(parents=True, exist_ok=True)

    if args.provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            print("GEMINI_API_KEY is not set. Refusing to run with a simulated agent.")
            return 1
        if args.list_models:
            list_gemini_models(key)
            return 0
        agent = gemini_agent(args.model, key, cache, args.delay)
    elif args.provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY is not set. Refusing to run with a simulated agent.")
            return 1
        agent = anthropic_agent(args.model, cache, args.delay)
    else:
        env = args.api_key_env or f"{args.provider.upper()}_API_KEY"
        key = os.environ.get(env)
        if not key:
            print(f"{env} is not set. Refusing to run with a simulated agent.")
            return 1
        base = args.base_url or OPENAI_COMPATIBLE[args.provider]
        agent = openai_agent(args.model, key, base, cache, args.delay)

    # Spend one call proving the model answers before committing the whole run.
    # Gemini's --list-models advertised gemini-2.5-flash, which returns 404 with "no
    # longer available to new users" — so a listing is not proof a model is callable,
    # and finding that out 40 calls into a quota-limited run wastes the quota.
    try:
        probe = agent("Preflight check: Amul Butter 500g")
        print(f"preflight: model answered {probe[:40]!r}\n")
    except Exception as error:  # noqa: BLE001 - surfacing the provider's own message
        print(f"preflight FAILED: {type(error).__name__}: {error}")
        print("The model is not callable with this key. Nothing was spent on the run.")
        return 1

    records = json.load(open(args.corpus, encoding="utf-8"))[: args.limit]
    print(f"corpus: {len(records)} records from {args.corpus}")
    print(f"model:  {args.model} via {args.provider}")
    print(f"calls:  up to {3 * len(records)} (3 per record), {args.delay}s apart, cached")
    print("arms:   A baseline | B blind retry (control) | C Approv feedback\n")

    result = run_benchmark(
        records, agent, on_progress=lambda i, n: print(f"\r  {i}/{n}", end="", flush=True)
    )
    print()

    _print_arms("ALL RECORDS", result.arms)
    _print_arms(
        "HARD SUBSET - brand is NOT in the title (the cases that matter)",
        subset(result, brand_in_title_value=False),
    )
    _print_arms(
        "TRIVIAL SUBSET - brand is already in the title (a copy job)",
        subset(result, brand_in_title_value=True),
    )

    print("\nRead the transcript before believing any of this.")
    print("C - B is the number. C - A would also count the effect of simply retrying.")

    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(
        {
            "model": args.model,
            "provider": args.provider,
            "n_records": len(records),
            "arms": {
                name: {
                    "correct": arm.correct,
                    "abstained": arm.abstained,
                    "total": arm.total,
                    "accuracy": arm.accuracy,
                    "accuracy_when_answered": arm.accuracy_when_answered,
                    "interval": arm.interval,
                }
                for name, arm in result.arms.items()
            },
            "transcript": result.transcript,
        },
        open(args.out, "w", encoding="utf-8"),
        indent=2,
        ensure_ascii=False,
    )
    print(f"transcript: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
