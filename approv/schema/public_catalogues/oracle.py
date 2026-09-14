"""Independent structural answer key for public Shopify feed probes.

Deliberately imports no Approv code. This audits attribution to published fields,
not physical product truth or the semantic sufficiency of a category minimum.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from urllib.parse import quote


def name_key(value):
    return re.sub(r"\s+", "_", value.strip().casefold())


# The key a Shopify feed publishes its option definitions under. Named here rather than
# discovered because the oracle's job is to state the answer from the feed's own
# conventions; a reader that binds `option1` to a name table somewhere else is exactly the
# confident-wrong-variant defect these probes exist to catch, and it should show up as a
# disagreement rather than be absorbed by searching for whatever table agrees.
OPTION_TABLE = "options"


def option_key(product, variant):
    definitions = {}
    ambiguous = set()
    for index, option in enumerate(product.get(OPTION_TABLE, []), 1):
        if not isinstance(option, dict):
            continue
        position = option.get("position", index)
        if type(position) is not int or not isinstance(option.get("name"), str):
            continue
        if position in definitions:
            ambiguous.add(position)
        definitions[position] = option["name"]
    # The locator syntax is spelled out rather than imported, like everything else here.
    # A numbered slot means nothing without the table that named it, so the guard carries
    # both: `#name=` is which option this is, `&table=` is which table said so.
    table = "&table=" + quote("/" + OPTION_TABLE, safe="")
    expected = []
    for position, label in definitions.items():
        slot = "option" + str(position)
        raw = variant.get(slot)
        if position in ambiguous or not label.strip() or raw is None or str(raw).strip() == "":
            continue
        expected.append({"attribute": name_key(label),
                         "field_name": f"/variants/*/{slot}#name=" + quote(label, safe="") + table,
                         "raw": str(raw).strip(), "position": position})
    return expected, sorted(ambiguous)


def probe_rows(records, limit=200):
    """Stable hash sample over variant rows, independent of proposed attributes."""
    rows = []
    for pi, product in enumerate(records):
        for vi, variant in enumerate(product.get("variants", [])):
            if isinstance(variant, dict):
                token = json.dumps([pi, vi, product.get("id"), variant.get("id")]).encode()
                rows.append((hashlib.sha256(token).digest(), pi, vi))
    return [(pi, vi) for _, pi, vi in sorted(rows)[:limit]]


def raw_inventory(records):
    counts = Counter()
    examples = {}
    for pi, product in enumerate(records):
        variants = product.get("variants", [])
        ids = Counter(str(v["id"]) for v in variants if isinstance(v, dict) and v.get("id") is not None)
        for vi, variant in enumerate(variants):
            if not isinstance(variant, dict):
                continue
            counts["variant_rows"] += 1
            flags = []
            if variant.get("id") is None and not str(variant.get("sku") or "").strip():
                flags.append("no_order_addressable_identifier")
            if not str(variant.get("sku") or "").strip():
                flags.append("blank_sku")
            if variant.get("id") is not None and ids[str(variant["id"])] > 1:
                flags.append("duplicate_variant_id_within_product")
            if isinstance(variant.get("featured_image"), dict):
                flags.append("featured_image_object")
            expected, ambiguous = option_key(product, variant)
            if expected:
                flags.append("option_table_selected_slot")
            if ambiguous:
                flags.append("ambiguous_option_positions")
            if any(re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", slot["raw"]) for slot in expected):
                flags.append("uuid_valued_selector_requires_review")
            counts["populated_selected_slots"] += len(expected)
            for flag in flags:
                counts[flag] += 1
                examples.setdefault(flag, {"product_index": pi, "variant_index": vi, "product_id": product.get("id"), "variant_id": variant.get("id")})
    return dict(counts), examples


def value_matches_raw(raw, value):
    """Check lossless source fidelity. None means the oracle does not cover a type.

    No entity linking, quantity algebra, category guesses or producer value parser.
    A faithfully read physical unit can still need semantic review (e.g. shoe '9 M').
    """
    if value["kind"] == "term":
        return value["surface"] == raw
    if value["kind"] == "count":
        match = re.fullmatch(r"(\d+)\s*(?:count|ct|pcs?|pieces?|units?)?", raw, re.I)
        return bool(match) and int(match[1]) == value["n"]
    if value["kind"] == "quantity":
        match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*([a-zA-Z_ ]+|")', raw)
        if not match:
            return False
        # Alias conversions are deliberately left outside this narrow oracle.
        unit = match[2].strip().lower()
        if unit != value["unit"]:
            return None
        return Decimal(match[1]) == Decimal(value["magnitude"])
    if value["kind"] == "money":
        tokens = raw.split()
        if len(tokens) != 2:
            return False
        try:
            amount = tokens[1] if tokens[0] == value["currency"] else tokens[0]
            return value["currency"] in tokens and Decimal(amount) == Decimal(value["amount"])
        except InvalidOperation:
            return False
    return None
