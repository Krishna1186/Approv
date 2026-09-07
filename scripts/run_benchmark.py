"""Run the Approv benchmark against a real agent.

    pip install anthropic
    export ANTHROPIC_API_KEY=sk-...
    python scripts/run_benchmark.py --limit 100

Nothing here is simulated. If no API key is present the script refuses to run rather
than substituting a mock, because a mock would produce a number that looks like a
measurement and is not one.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from approv.harness.benchmark import run_benchmark  # noqa: E402

PROMPT = (
    "You are a shopping assistant reading a product listing.\n"
    "Listing title: {title}\n\n"
    "State the brand of this product. Reply with the brand name only, nothing else.\n"
    "If the title does not tell you the brand, say exactly: UNKNOWN"
)


def anthropic_agent(model: str):
    import anthropic

    client = anthropic.Anthropic()

    def agent(title: str, feedback: str | None = None) -> str:
        messages = [{"role": "user", "content": PROMPT.format(title=title)}]
        if feedback is not None:
            messages.append({"role": "assistant", "content": "(previous answer)"})
            messages.append(
                {
                    "role": "user",
                    "content": f"{feedback}\n\nGive your final answer, brand name only.",
                }
            )
        response = client.messages.create(
            model=model, max_tokens=32, messages=messages
        )
        return response.content[0].text.strip()

    return agent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default="data/cache/off_india_raw.json")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--out", default="data/cache/benchmark_result.json")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Refusing to run with a simulated agent.")
        return 1

    records = json.load(open(args.corpus, encoding="utf-8"))[: args.limit]
    print(f"corpus: {len(records)} records from {args.corpus}")
    print(f"model:  {args.model}")
    print("arms:   A baseline · B blind retry (control) · C Approv feedback\n")

    result = run_benchmark(
        records,
        anthropic_agent(args.model),
        on_progress=lambda i, n: print(f"\r  {i}/{n}", end="", flush=True),
    )
    print("\n")

    for name, arm in result.arms.items():
        low, high = arm.interval
        print(
            f"{name:20} {arm.correct:4}/{arm.total:<4} {arm.accuracy:6.1%}   "
            f"95% CI [{low:.1%}, {high:.1%}]"
        )

    delta, description = result.improvement()
    print(f"\nimprovement attributable to Approv: {description}")
    print("  (C minus B. C minus A would also count the effect of simply retrying.)")

    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(
        {
            "model": args.model,
            "n": len(records),
            "arms": {
                name: {
                    "correct": arm.correct,
                    "total": arm.total,
                    "accuracy": arm.accuracy,
                    "interval": arm.interval,
                }
                for name, arm in result.arms.items()
            },
            "improvement_c_minus_b": delta,
            "transcript": result.transcript,
        },
        open(args.out, "w", encoding="utf-8"),
        indent=2,
        ensure_ascii=False,
    )
    print(f"\nfull transcript written to {args.out}")
    print("Read it. Spot-check twenty rows by hand before believing any of this.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
