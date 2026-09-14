"""Explicit offline cohort audit and standalone partner handoffs; no auto-adoption."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
import hashlib
from pathlib import Path
import subprocess

from approv.schema import propose_schema
from approv.schema.models import Share
from approv.schema.report import ReportContext, build_partner_report, render_html, format_share
from approv.surface.verification import evidence_from_snapshot, selected_listing
from approv.types.core import Money, OrderLine

from .fetch import save
from .oracle import option_key, probe_rows, raw_inventory, value_matches_raw


def share(n, d):
    return Share(numerator=n, denominator=d).model_dump(mode="json")


def rate(value, unit="listings"):
    return format_share(value).replace("listings", unit)


PREREQUISITES = [
    "Bind an order line to the same product and a uniquely identifiable selected variant. Supply a nonempty SKU and, where the catalogue uses numeric variant IDs, preserve that ID in the order mapping. Never invent a SKU from a display title. A feed ID alone does not prove your order integration can name it.",
    "Supply a trusted ISO currency and the charged unit price. A bare public-feed price does not establish currency, taxes, discounts or the final order amount.",
    "Keep option-name tables with their selected option slots. Keep the original snapshot and its catalogue version or capture time; a current public page cannot establish what was offered at order time.",
    "Split mixed product categories and have a human confirm source mappings, relevant attributes and the verification minimum. Remove incidental image metadata from product requirements before adopting any proposal.",
    "Capture the stated request and its provenance. A final cart without a usable request supports order evidence only; it cannot support an intent-verification label or price.",
]


def check_probes(records, proposal, limit=200):
    counts = Counter()
    examples = []
    packet = []
    zero_sources = {(row.attribute, source.field_name) for row in proposal.report.attributes
                    for source in row.sources if source.published.numerator == 0}
    for pi, vi in probe_rows(records, limit):
        product, variant = records[pi], records[pi]["variants"][vi]
        counts["probed_variants"] += 1
        expected, ambiguous = option_key(product, variant)
        counts["expected_selected_slots"] += len(expected)
        # A diagnostic order, never signed or sent to verification. XXX is ISO's
        # no-currency code; this fabricated zero price is not merchant evidence.
        order = OrderLine(order_id="offline-structural-probe", product_id=str(product.get("id", "absent")),
                          sku=str(variant.get("sku") or "probe-missing-sku"),
                          variant_id=str(variant["id"]) if variant.get("id") is not None else None,
                          quantity=1, unit_price=Money(amount=0, currency="XXX"))
        trace = {"product_index": pi, "variant_index": vi, "product_id": product.get("id"), "variant_id": variant.get("id"), "expected": expected}
        try:
            projection = selected_listing(product, order)
            actual = evidence_from_snapshot(projection, proposal.proposed_schema)
        except (ValueError, TypeError) as error:
            counts["reader_or_binding_errors"] += 1
            counts["unread_selected_slots"] += len(expected)
            trace.update(problem="reader_or_binding_error", detail=str(error))
            if len(examples) < 20:
                examples.append(trace)
            continue
        counts["nonzero_evidence_variants"] += bool(actual)
        disagreements = [e for e in actual if (e.attribute, e.field_name) in zero_sources]
        if disagreements:
            counts["variants_with_publication_reader_disagreement"] += 1
            if len(examples) < 20:
                examples.append({**trace, "problem": "reader_emits_source_reported_as_never_usable",
                                 "actual": [e.model_dump(mode="json") for e in disagreements]})
        wrong = missing = False
        for expected_slot in expected:
            found = [e for e in actual if e.field_name == expected_slot["field_name"]]
            matching = [e for e in found if e.attribute == expected_slot["attribute"]]
            if not matching:
                problem = "wrong_attribute" if found else "missing_evidence"
                if found:
                    counts["wrong_selected_slots"] += 1
                    wrong = True
                else:
                    counts["missing_selected_slots"] += 1
                    missing = True
            else:
                results = [value_matches_raw(expected_slot["raw"], e.value.model_dump(mode="json")) for e in matching]
                if any(result is False for result in results) or len(matching) != 1:
                    counts["wrong_selected_slots"] += 1
                    wrong = True
                    problem = "wrong_or_ambiguous_value"
                elif any(result is None for result in results):
                    counts["oracle_unassessed_selected_slots"] += 1
                    problem = "oracle_type_not_assessed"
                else:
                    counts["correct_selected_slots"] += 1
                    problem = None
            if problem and len(examples) < 20:
                examples.append({**trace, "problem": problem, "slot": expected_slot,
                                 "actual": [e.model_dump(mode="json") for e in found]})
        counts["variants_with_wrong_selected_evidence"] += wrong
        counts["variants_with_missing_selected_evidence"] += missing
        media = [e for e in actual if "/featured_image/" in e.field_name]
        if media:
            counts["variants_with_image_metadata_evidence"] += 1
            if len(examples) < 20:
                examples.append({**trace, "problem": "image_metadata_as_product_evidence", "actual": [e.model_dump(mode="json") for e in media]})
        # A human-review packet, not a claim that a human has reviewed it.
        if len(packet) < 10:
            packet.append({**trace, "raw_options": product.get("options"), "selected_variant": variant,
                           "actual": [e.model_dump(mode="json") for e in actual]})
    n, slots = counts["probed_variants"], counts["expected_selected_slots"]
    result = {key: share(counts[key], slots if key.endswith("selected_slots") else n) for key in (
        "correct_selected_slots", "missing_selected_slots", "wrong_selected_slots", "unread_selected_slots", "oracle_unassessed_selected_slots",
        "nonzero_evidence_variants", "reader_or_binding_errors", "variants_with_wrong_selected_evidence",
        "variants_with_missing_selected_evidence", "variants_with_image_metadata_evidence", "variants_with_publication_reader_disagreement")}
    return {"counts": dict(counts), "rates": result, "examples": examples, "human_review_packet": packet, "human_review_status": "pending"}


def locator_shape(field):
    if "#name=" in field and "/option" in field:
        return "option_table_selected_slot"
    if "#name=" in field and "/*/" in field:
        return "named_pair_selector"
    if "#name=" in field:
        return "labelled_prose_selector"
    if "/*/" in field:
        return "variant_or_array_field"
    return "object_pointer"


def decorate(report, audit):
    e = lambda text: escape(str(text), quote=True)
    parts = ['<h2>Before an order can be checked</h2><ul>' + ''.join('<li>'+e(p)+'</li>' for p in PREREQUISITES) + '</ul>']
    probes = audit["probes"]
    parts += ['<h2>Reader audit — Approv integration work</h2>',
              '<p>These checks compare selected option values directly with raw feed fields. They do not establish physical truth or replace human source review.</p>']
    for key, label in [("variants_with_wrong_selected_evidence", "Incorrect selected option evidence"),
                       ("variants_with_missing_selected_evidence", "Missing selected option evidence"),
                       ("variants_with_image_metadata_evidence", "Image metadata emitted as product evidence"),
                       ("variants_with_publication_reader_disagreement", "Reader emits a source the publication report calls wholly unusable"),
                       ("reader_or_binding_errors", "Reader or order-binding failure")]:
        parts.append('<p><strong>'+e(label)+':</strong> '+e(rate(probes["rates"][key], "probed variants"))+'</p>')
    if audit["media_profiles"]:
        parts += ['<p class="notice"><strong>Source mapping correction required.</strong> Approv proposed image metadata as product attributes. '
                  'This is an Approv derivation issue, not a request for you to publish image dimensions as product facts. The proposal must not be adopted unchanged.</p>']
    parts.append('<p>Probe selection: lowest SHA-256 ranks of raw product/variant row identifiers. Human spot-check status: pending. Full diagnostics and capture provenance accompany this report.</p>')
    parts.append('<p>Order mapping: '+e(rate(audit["identifiers"]["no_order_addressable_identifier"]))+' have neither a published variant ID nor SKU. '+e(rate(audit["identifiers"]["blank_sku"]))+' have no nonempty SKU. A merchant may have an order-side SKU absent from this public export; confirm it rather than manufacturing one.</p>')
    parts.append('<p>Opaque identifier selections: '+e(rate(audit["identifiers"]["uuid_valued_selector_requires_review"]))+' publish UUID-shaped option values. Confirm whether these are operational listing IDs before treating them as customer choices.</p>')
    html = render_html(report)
    html = html.replace('<div class="metrics">', '<p class="notice"><strong>Review source scope before using these numbers.</strong> '
                        'A label such as size is counted as that exact derived attribute. Bundle-component sizes, other option names, and category-specific alternatives require mapping review; a gap is not proof the merchant omitted all sizing information.</p><div class="metrics">', 1)
    return html.replace('<h2>Publication by attribute</h2>', '\n'.join(parts) + '<h2>Publication by attribute</h2>')


def audit_store(manifest, cache, output, revision):
    host = manifest["host"]
    folder = cache / host
    raw = (folder / "products.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["products_sha256"]:
        raise ValueError("aggregate catalogue hash differs from capture manifest")
    records = json.loads(raw)
    captured = next(r["started_at"] for r in manifest["responses"] if "/products.json?" in r["requested_url"])
    proposal = propose_schema(records, category_id="public." + manifest["sector"] + "." + host,
                              observed_at=datetime.now(timezone.utc))
    inventory, inventory_examples = raw_inventory(records)
    n = inventory.get("variant_rows", 0)
    shape_counts = Counter(locator_shape(p.field_name) for p in proposal.proposed_schema.field_profiles)
    profile_n = len(proposal.proposed_schema.field_profiles)
    media_profiles = [p.field_name for p in proposal.proposed_schema.field_profiles if "/featured_image/" in p.field_name]
    audit = {"revision": revision, "host": host, "merchant": manifest["merchant"], "sector": manifest["sector"],
             "capture": manifest, "raw_counts": inventory, "raw_examples": inventory_examples,
             "identifiers": {key: share(inventory.get(key, 0), n) for key in ("no_order_addressable_identifier", "blank_sku", "duplicate_variant_id_within_product", "uuid_valued_selector_requires_review")},
             "locator_shapes": {key: share(value, profile_n) for key, value in sorted(shape_counts.items())},
             "media_profiles": media_profiles, "probes": check_probes(records, proposal),
             "proposal_has_usable_minimum": bool(proposal.proposed_schema.attributes and proposal.report.floor and proposal.report.cannot_verify.numerator < proposal.report.listings),
             "adopted": False}
    save(folder / "human-review-packet.json", audit["probes"].pop("human_review_packet"))
    audit["probes"]["human_review_packet_local"] = host + "/human-review-packet.json"
    scope = ("Public " + manifest["sector"] + " store feed; mixed product categories require review. " +
             ("Pagination reached a short or empty page." if manifest["pagination_complete"] else "Partial capture: " + manifest["status"] + ".") +
             " This snapshot does not establish live-store or order-traffic completeness.")
    report = build_partner_report(proposal, ReportContext(merchant=manifest["merchant"], scope=scope,
                                  source="https://"+host+"/products.json", captured_at=captured,
                                  source_sha256=manifest["products_sha256"]))
    prefix = output / host
    save(prefix.with_suffix(prefix.suffix + ".json"), report)
    save(output / (host + ".audit.json"), audit)
    save(output / (host + ".proposal.json"), proposal.model_dump(mode="json"))
    (output / (host + ".html")).write_text(decorate(report, audit), encoding="utf-8")
    print(f"audited {host}: {proposal.report.listings} listings, media profiles {len(media_profiles)}", flush=True)
    return {"host": host, "merchant": manifest["merchant"], "sector": manifest["sector"], "status": "audited", "listings": proposal.report.listings,
            "proposal_has_usable_minimum": audit["proposal_has_usable_minimum"], "below_minimum": report["measurement"]["cannot_verify"],
            "no_evidence": report["measurement"]["no_comparable_attributes"], "floor": report["measurement"]["floor"],
            "locator_shapes": audit["locator_shapes"], "probes": audit["probes"]["rates"], "media_profiles": media_profiles,
            "pagination_complete": manifest["pagination_complete"]}


def write_index(rows, output, revision):
    audited = [r for r in rows if r["status"] == "audited"]
    retrieved = [r for r in rows if r["status"] in {"audited", "derivation_failure"}]
    usable = sum(r["proposal_has_usable_minimum"] for r in audited)
    metrics = {"retrieved_nonempty_catalogues": share(len(retrieved), len(rows)), "usable_proposals_all_attempted": share(usable, len(rows)),
               "usable_proposals_retrieved": share(usable, len(retrieved)), "stores_with_media_profiles": share(sum(bool(r["media_profiles"]) for r in audited), len(audited))}
    shapes = ["object_pointer", "variant_or_array_field", "option_table_selected_slot", "named_pair_selector", "labelled_prose_selector"]
    shape_stores = {key: share(sum(key in row["locator_shapes"] for row in audited), len(audited)) for key in shapes}
    sectors = {}
    for sector in sorted({row["sector"] for row in rows}):
        cohort = [row for row in rows if row["sector"] == sector]
        observed = [row for row in cohort if row["status"] in {"audited", "derivation_failure"}]
        sectors[sector] = {"retrieved": share(len(observed), len(cohort)),
                           "usable_proposals": share(sum(row.get("proposal_has_usable_minimum", False) for row in observed), len(observed))}
    summary = {"revision": revision, "observed_at": datetime.now(timezone.utc).isoformat(), "model": "none-deterministic", "prompt": "none",
               "metrics": metrics, "locator_shape_stores": shape_stores, "sectors": sectors, "stores": rows}
    save(output / "index.json", summary)
    e = lambda text: escape(str(text), quote=True)
    body = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Approv | Public catalogue readiness</title>',
            '<style>body{font:16px/1.6 Georgia,serif;color:#163a32;background:#f6f4ed;margin:40px auto;padding:0 24px;max-width:1200px}h1{font-size:44px}table{width:100%;border-collapse:collapse;font:14px/1.5 Arial,sans-serif}td,th{padding:14px 8px;border-bottom:1px solid #ccd4cc;text-align:left}a{color:#13624d}.note{padding:20px;background:#e5ebe2}small{display:block}</style>',
            '<h1>What public catalogues let us verify</h1><p>A fresh merchant cohort across apparel, footwear, grocery, homeware and cosmetics. Open a merchant name for its standalone handoff.</p>',
            '<p class="note">Unconfirmed proposals. Public feed availability is not an order integration. Counts describe captured listings; they do not estimate traffic, accuracy or financial coverage. This purposive cohort is not a representative sample of commerce.</p>',
            '<p>Audit: '+e(summary["observed_at"])+'. Base revision: '+e(revision)+'. Model: none-deterministic. Prompt: none. Wilson 95% intervals are descriptive; a store-access failure is not a schema failure.</p>']
    for key, value in metrics.items():
        body.append('<p><strong>'+e(key.replace('_', ' '))+':</strong> '+e(rate(value, "stores"))+'</p>')
    if len(audited) < 30:
        body.append('<p class="note"><strong>Incomplete study.</strong> The requested cohort of at least thirty fetched catalogues has not been reached. Access and terms exclusions remain in the table; these results cannot support a cross-sector readiness claim.</p>')
    body.append('<h2>Sector denominators</h2>')
    for sector, values in sectors.items():
        body.append('<p>'+e(sector)+': retrieved '+e(rate(values["retrieved"], "selected stores"))+'; usable proposals '+e(rate(values["usable_proposals"], "retrieved stores"))+'.</p>')
    body.append('<h2>Locator shapes</h2>')
    for key, value in shape_stores.items():
        body.append('<p>'+e(key)+': '+e(rate(value, "retrieved stores"))+'</p>')
    body.append('<h2>Merchant handoffs</h2><table><thead><tr><th>Merchant / sector</th><th>Captured scope</th><th>Below proposed minimum</th><th>No comparison evidence</th></tr></thead><tbody>')
    for row in rows:
        label = e(row["merchant"])
        if row["status"] == "audited":
            label = '<a href="'+e(row["host"])+'.html">'+label+'</a>'
            cells = [str(row["listings"])+" / "+str(row["listings"])+" captured listings; "+("pagination complete" if row["pagination_complete"] else "partial capture"),
                     ", ".join(row["floor"])+": "+rate(row["below_minimum"]), rate(row["no_evidence"])]
        else:
            cells = [row["status"], "Unmeasured", "Unmeasured"]
        body.append('<tr><td>'+label+'<small>'+e(row["sector"])+'</small></td>'+''.join('<td>'+e(cell)+'</td>' for cell in cells)+'</tr>')
    body.append('</tbody></table><p>Raw public responses remain in the local cache. JSON companions retain provenance, errors, counts, intervals, and unconfirmed proposals. Human source-key spot-checks remain pending.</p></html>')
    (output / "index.html").write_text('\n'.join(body), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((args.cache / "manifest.json").read_text(encoding="utf-8"))
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    rows = []
    for store in manifest["stores"]:
        if not store["products"]:
            rows.append({key: store[key] for key in ("host", "merchant", "sector", "status")})
        else:
            try:
                rows.append(audit_store(store, args.cache, args.output, revision))
            except (ValueError, TypeError, KeyError) as error:
                rows.append({**{key: store[key] for key in ("host", "merchant", "sector")}, "status": "derivation_failure", "error": str(error)})
        write_index(rows, args.output, revision)


if __name__ == "__main__":
    main()
