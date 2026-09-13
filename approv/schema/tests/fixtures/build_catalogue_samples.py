"""Regenerate the checked-in merchant samples; never called by the default suite.

Usage: python approv/schema/tests/fixtures/build_catalogue_samples.py <data/cache>
Preserve sibling context from each available host, plus explicit colour
variation and numeric/slash size labels. Keep at most six actual SKU rows per family.
Stable content hashes choose rows, not the schema derivation being tested.
"""
import copy
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def siblings(rows):
    return sorted(rows, key=digest)[:6]


def build(cache):
    cached_path = cache / "shopping-study" / "shopper-v3.json"
    raw_path = cache / "shopify-raw.json"
    pack = json.loads(cached_path.read_text(encoding="utf-8"))
    groups = defaultdict(list)
    for row in pack["inventory"]["products"]:
        groups[row["source_url"]].append({k: row[k] for k in ("id", "source_url", "details")})
    selected = {}
    hosts = sorted({urlsplit(url).netloc for url in groups})
    for host in hosts:
        candidates = [url for url, rows in groups.items() if urlsplit(url).netloc == host and len(rows) > 1]
        if candidates:
            url = min(candidates, key=digest)
            selected[url] = siblings(groups[url])
    for predicate in (
        lambda rows: len({r["details"].get("color") for r in rows}) > 1,
        lambda rows: any(re.fullmatch(r"\d+(?:\.\d+)?", r["details"].get("size", "")) for r in rows),
        lambda rows: any("/" in r["details"].get("size", "") for r in rows),
    ):
        candidates = [url for url, rows in groups.items() if len(rows) > 1 and predicate(rows)]
        url = min(candidates, key=digest)
        selected[url] = siblings(groups[url])
    cached_sample = [row for url in sorted(selected) for row in selected[url]]

    raw_sample = []
    hosts_raw = json.loads(raw_path.read_text(encoding="utf-8"))
    for host, products in hosts_raw:
        candidates = [p for p in products if len(p.get("variants", [])) > 1]
        if candidates:
            product = copy.deepcopy(min(candidates, key=digest))
            product["variants"] = siblings(product["variants"])
            product["merchant_id"] = host
            raw_sample.append(product)

    target = Path(__file__).parent
    for name, content in (("shopify_cached_sample.json", cached_sample), ("shopify_raw_sample.json", raw_sample)):
        (target / name).write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    provenance = {
        "selection_version": "host-and-sibling-sample-v1",
        "source_sha256": {str(p.relative_to(cache)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (cached_path, raw_path)},
        "samples": {
            "cached": {"selected_listings": len(cached_sample), "source_listings": len(pack["inventory"]["products"])},
            "raw": {"selected_listings": sum(len(p["variants"]) for p in raw_sample),
                    "source_listings": sum(len(p.get("variants", [])) for _, products in hosts_raw for p in products)},
        },
        "model_version": "none-deterministic", "prompt_version": "none",
        "purpose": "regression fixtures; not a statistical sample or published performance estimate",
    }
    (target / "catalogue_samples_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build(Path(sys.argv[1]))
