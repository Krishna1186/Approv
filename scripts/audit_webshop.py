"""Run the extractor over real human shopping instructions, for a founder audit pass.

    python scripts/audit_webshop.py --out output/webshop-audit-2026-09-10.json

This is not a scored gold set and does not produce an accuracy number. DR 0016 §4 asks
for a human *audit* of a generator's output (~50 cases, catching systematic error) rather
than hand-labelling hundreds of examples, and that is the pattern this follows — except
the thing being audited here is the extractor itself, run against text nobody generated
for it. The WebShop instructions (data/cache/webshop/items_human_ins.json, ~10k products,
one or more crowd-worker instructions each — "i'm looking for a blue wireless bluetooth
headphones") are real requests, unlike a keyword search query and unlike anything the
spec-first case-pack generators produce, because they were written before Approv's schema
existed and were never shaped to fit it.

There is no answer key. The dataset's own 'attributes'/'options' fields describe a
different labelling task (WebShop's own attribute taxonomy, not this schema) and are
carried into the output for a human's reference only, never compared against or scored
against. Read the output and look for a systematic pattern — a whole attribute the
extractor never recovers, a category of instruction it mishandles, an invented value —
the way DR 0016's audit already works for the gate's catalogue-derived keys.

The probe schema below is deliberately open-vocabulary (no closed list, unlike the
shopify packs) because there is no catalogue behind this text to define one; the
extractor is being read for how it behaves with nothing to constrain it, not scored
against a category it was tuned for.
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from approv.harness.adapters import AdapterError
from approv.harness.intent import RequestInterpreter
from approv.harness.shopping import ShoppingCase, canonical, digest
from approv.types.core import AttributeSpec, CategorySchema, Criticality, Dimension

# Groq default, overridable with --endpoint/--key-file for whichever OpenAI-compatible
# provider has budget left — RequestInterpreter only ever speaks this one wire format
# (approv/harness/intent.py), so any provider that speaks it works with no code change.
ENDPOINT = "https://api.groq.com/openai/v1"


def probe_schema() -> CategorySchema:
    """No catalogue stands behind this text, so no field profile does either.

    Criticality is set for completeness's sake (a future ComparisonRecord could use this
    schema) but nothing here runs the checker — only extraction is under audit.
    """
    return CategorySchema(
        category_id="webshop.audit", version="probe-v1",
        attributes=(
            AttributeSpec(name="color", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
            AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
            AttributeSpec(name="material", dimension=Dimension.NOMINAL, criticality=Criticality.SOFT),
            AttributeSpec(name="price", dimension=Dimension.MONEY, criticality=Criticality.BOUND),
            AttributeSpec(name="product_type", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        ),
        field_profiles=(),
    )


def load_instructions(path: Path, sample: int, seed: int) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    flat = [{"asin": asin, **record} for asin, records in data.items() for record in records]
    flat.sort(key=lambda r: (r["asin"], r.get("assignment_id", "")))
    rng = random.Random(seed)
    return rng.sample(flat, min(sample, len(flat)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default="data/cache/webshop/items_human_ins.json")
    parser.add_argument("--out", required=True)
    parser.add_argument("--sample", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--model", default="openai/gpt-oss-20b")
    parser.add_argument("--version", default="v4", choices=("v1", "v2", "v3", "v4", "v5"))
    parser.add_argument("--interval", type=float, default=6)
    parser.add_argument("--endpoint", default=ENDPOINT,
                        help="OpenAI-compatible /chat/completions base URL. Default is Groq's.")
    parser.add_argument("--key-file", default="",
                        help="Read the API key from this file instead of GROQ_API_KEY. "
                             "Use for a non-Groq provider; never pass a key on the command "
                             "line directly, since that lands in shell history.")
    args = parser.parse_args()

    if args.key_file:
        key = Path(args.key_file).read_text(encoding="utf-8").strip()
    else:
        from scripts.run_study import get_key
        key = get_key()
    schema = probe_schema()
    interpreter = RequestInterpreter(args.endpoint, args.model, key, args.version)

    rows = load_instructions(Path(args.source), args.sample, args.seed)
    out = Path(args.out)
    results = json.loads(out.read_text(encoding="utf-8-sig")) if out.exists() else {}

    for index, row in enumerate(rows):
        cid = "webshop-%s-%d" % (row["asin"], index)
        if cid in results:
            continue
        case = ShoppingCase(id=cid, request=row["instruction"],
                            author="WebShop crowd-worker instruction, real text, not generated",
                            cluster="webshop-%s" % row["asin"])
        delays = []
        for attempt in range(4):
            time.sleep(args.interval if not delays else delays[-1])
            try:
                interpreted, meta = interpreter(case, schema)
                break
            except AdapterError as error:
                wait = error.metadata.get("retry_after_seconds", 0)
                if error.code == "http_429" and 0 < wait <= 90 and attempt < 3:
                    delays.append(wait + 1)
                    continue
                out.write_text(canonical(results) + "\n", encoding="utf-8")
                print(json.dumps({"blocked": error.code, "case": cid, "done": len(results)}))
                return 2
        results[cid] = {
            "asin": row["asin"],
            "instruction": row["instruction"],
            # Reference only — a different labelling task, never scored against.
            "webshop_attributes": row.get("attributes", []),
            "webshop_options": row.get("options", []),
            "extractor_status": meta["status"],
            "extractor_version": meta.get("version"),
            "extractor_model": meta.get("model"),
            "constraints": [c for c in interpreted.constraints],
            "requested_units": interpreted.requested_units,
            "quantity_scope": interpreted.quantity_scope,
            "interpretation_notes": list(interpreted.interpretation_notes),
            "raw_output": meta.get("raw_output"),
        }
        # model_dump each constraint for JSON safety, matching the rest of the harness.
        results[cid]["constraints"] = [c.model_dump(mode="json") for c in interpreted.constraints]
        out.write_text(canonical(results) + "\n", encoding="utf-8")

    parsed = sum(1 for r in results.values() if r["extractor_status"] == "parsed")
    empty = sum(1 for r in results.values()
               if r["extractor_status"] == "parsed" and not r["constraints"])
    print(json.dumps({
        "out": str(out), "sampled": len(rows), "recorded": len(results),
        "parsed": parsed, "invalid_interpretation": len(results) - parsed,
        "parsed_with_no_constraints": empty,
        "note": "Not a scored result. Read the constraints and interpretation_notes "
                "columns against the instruction text and look for a systematic pattern.",
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
