"""Offline report writer. Explicit envelopes unwrap data, never embedded schemas."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .derive import propose_schema
from .report import ReportContext, build_partner_report, format_share, render_html


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalogue", type=Path)
    parser.add_argument("--shape", choices=("records", "shopping-study", "shopify-export"), default="records")
    parser.add_argument("--host", help="one host from a Shopify export; never merges merchant identities")
    parser.add_argument("--merchant", required=True, help="display name, or an explicit multi-merchant cohort label")
    parser.add_argument("--scope", required=True, help="what this supplied snapshot includes and excludes")
    parser.add_argument("--category", required=True)
    parser.add_argument("--captured-at", help="only when established by the source")
    parser.add_argument("--observed-at", help="timezone-aware audit date; default now UTC")
    parser.add_argument("--currency", help="explicitly established catalogue currency; never inferred from a host")
    parser.add_argument("--output", type=Path, required=True, help="output prefix for .html, .json and .proposal.json")
    args = parser.parse_args(argv)
    if args.host and args.shape != "shopify-export":
        parser.error("--host requires --shape shopify-export")
    raw = args.catalogue.read_bytes()
    payload = json.loads(raw)
    captured_at = args.captured_at
    if args.shape == "shopping-study":
        inventory = payload["inventory"]
        records = [{"id": p["id"], "source_url": p["source_url"], "details": p["details"]}
                   for p in inventory["products"]]
        captured_at = captured_at or inventory.get("captured_at")
    elif args.shape == "shopify-export":
        if args.host and args.host not in {host for host, _ in payload}:
            parser.error("host absent from supplied export")
        records = [dict(product, merchant_id=host) for host, products in payload
                   if not args.host or host == args.host for product in products]
    else:
        records = payload
    observed_at = datetime.fromisoformat(args.observed_at) if args.observed_at else datetime.now(timezone.utc)
    proposal = propose_schema(records, category_id=args.category, observed_at=observed_at, currency=args.currency)
    context = ReportContext(merchant=args.merchant, scope=args.scope, source=args.catalogue.name,
                            captured_at=captured_at, source_sha256=hashlib.sha256(raw).hexdigest())
    report = build_partner_report(proposal, context)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    Path(str(args.output) + ".html").write_text(render_html(report), encoding="utf-8")
    Path(str(args.output) + ".json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(str(args.output) + ".proposal.json").write_text(proposal.model_dump_json(round_trip=True, indent=2) + "\n", encoding="utf-8")
    print(args.merchant)
    print("Below proposed minimum (" + ", ".join(proposal.report.floor) + "): " + format_share(report["measurement"]["cannot_verify"]))
    print("No structured comparison evidence: " + format_share(report["measurement"]["no_comparable_attributes"]))
    print("Report: " + str(args.output) + ".html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
