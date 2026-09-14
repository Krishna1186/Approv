"""Structural discovery. Paths and option names come from the input, never a schema."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from html import unescape
from urllib.parse import urlsplit

from approv.types.core import Certainty, Dimension, Liability

from .values import key_name, occupied, read_value, semantic_key, text_value
from .locators import LABEL_KEYS, VALUE_KEYS, format_locator

_META = {"evidence", "schema", "category_schema", "field_profiles", "liability",
         "certainty", "is_variant_axis", "floor", "decision", "signature", "hash",
         "images", "image", "media", "reviews", "ratings", "recommendations",
         "tags", "created_at", "updated_at", "published_at", "position", "handle"}
# DR 0027. The exact names above miss the one real feeds actually publish: `featured_image`
# is a nested object of `width`, `height`, `alt` and `src`, and walking it proposed a
# product attribute called `width` whose value was a photograph's pixel count -- exact
# certainty, merchant-guaranteed, and satisfiable by a request that meant centimetres.
# Matched on any token so `featured_image`, `hero_image` and `product_photos` all land
# here, because an object describing a *rendering* of the product is not a source of
# product attributes however the merchant named it.
_RENDERING = {"image", "images", "photo", "photos", "thumbnail", "thumbnails",
              "gallery", "media", "video", "videos", "swatch", "swatches"}


def is_rendering(key: str) -> bool:
    return bool(_RENDERING.intersection(semantic_key(key).split("_")))
_PROSE = {"description", "body_html", "body", "prose", "copy", "description_html",
          "long_description", "short_description", "notes", "narrative"}
_OPERATIONAL = {"price", "cost", "amount", "msrp", "available", "availability",
                "stock", "inventory", "inventory_quantity", "taxable", "requires_shipping",
                "position", "title", "name", "variant", "currency", "currency_code"}
_GROUP = {"product_id", "parent_id", "family_id", "group_id", "item_group_id", "style_id"}
_NAMESPACE = {"merchant_id", "store_id", "merchant", "store", "host"}
_URL = {"source_url", "product_url", "canonical_url"}
_LABEL = LABEL_KEYS
_VALUE = VALUE_KEYS


def path_text(path: tuple[str, ...]) -> str:
    return format_locator(tuple(None if p == "\0" else p for p in path))


def selector_path(path: tuple[str, ...], label: str, *, table: tuple[str, ...] | None = None) -> str:
    return format_locator(tuple(None if p == "\0" else p for p in path), selector=label,
                          table=tuple(None if p == "\0" else p for p in table) if table is not None else None)


def is_identifier(key: str) -> bool:
    name = semantic_key(key)
    return bool(re.search(r"(?:^|_)(?:id|sku|code|ref|identifier)$", name)) and name not in {"currency_code"}


def identity(obj: dict) -> str | None:
    keys = sorted((k for k in obj if is_identifier(k) and semantic_key(k) not in _GROUP | _NAMESPACE),
                  key=lambda k: (semantic_key(k) != "id", semantic_key(k) != "sku", k))
    for key in keys:
        value = obj[key]
        if isinstance(value, (str, int)) and not isinstance(value, bool) and occupied(value):
            return f"{key}:{value}"
    return None


def pair(obj: dict) -> tuple[str, str] | None:
    label = next((k for k in _LABEL if isinstance(obj.get(k), str) and obj[k].strip()), None)
    val = next((k for k in _VALUE if k in obj), None)
    return (label, val) if label and val else None


@dataclass(frozen=True)
class OptionDefinition:
    name: str
    table: tuple[str, ...]


def option_definitions(obj: dict, path: tuple[str, ...] = ()) -> dict[int, OptionDefinition] | None:
    """Keep the table that established each slot; never last-write ambiguous names.

    None means no local definitions. A local definition set replaces inherited
    definitions as a whole, matching the documented nearest-object rule.
    """
    result = {}
    found = False
    for key, value in obj.items():
        if semantic_key(key) in _META or is_rendering(key):
            continue
        if isinstance(value, list) and value and all(isinstance(v, dict) and "name" in v and "values" in v for v in value):
            found = True
            for i, option in enumerate(value, 1):
                position = option.get("position", i)
                if (not isinstance(position, int) or isinstance(position, bool) or position < 1
                        or not isinstance(option["name"], str) or not option["name"].strip()
                        or not isinstance(option["values"], list)):
                    raise ValueError(f"invalid option definition in {path_text(path + (key,))}")
                if position in result:
                    raise ValueError(f"ambiguous option position {position} in {path_text(path + (key,))}")
                result[position] = OptionDefinition(option["name"], path + (key,))
    return result if found else None


def variant_collections(obj: dict, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], list]]:
    if len(path) > 32:
        raise ValueError("catalogue nesting exceeds 32 levels")
    result = []
    for key, value in obj.items():
        if not isinstance(key, str) or not key.strip() or any(ord(c) < 32 for c in key):
            raise ValueError("catalogue field names must be nonempty strings without control characters")
        if semantic_key(key) in _META or is_rendering(key):
            continue
        current = path + (key,)
        if value == [] and semantic_key(key) in {"variants", "skus", "editions"}:
            result.append((current, value))
        if isinstance(value, dict):
            result.extend(variant_collections(value, current))
        elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            if all(pair(v) or ("name" in v and "values" in v) for v in value):
                continue
            if any(identity(v) for v in value) or semantic_key(key) in {"variants", "skus", "editions"}:
                result.append((current, value))
    return result


@dataclass(frozen=True)
class Cell:
    name: str
    field: str
    raw: str
    dimension: Dimension | None
    value: object | None
    issue: str | None
    certainty: Certainty
    liability: Liability
    option: bool = False
    selectable: bool = True
    is_advice: bool = False
    present: bool = True


# The readings that may still be compared as a label even though typing them failed.
# `3XL` is not a unit and `13.5` has none; the whole surface text is what the merchant
# published either way.
_LABEL_SAFE = frozenset({"unitless_decimal", "unknown_or_ambiguous_unit"})
# And the ones where there is no honest surface text at all: stringifying a money object,
# copying six hundred characters of description into a label, or keeping a string that
# holds two quantity readings -- `1 fl oz | 30 ml`, out of a description -- would each
# manufacture the comparison that having no value correctly refuses.
_NOT_TEXT = frozenset({"unsupported_object", "invalid_money_amount", "invalid_number",
                       "multivalued_field_requires_mapping", "invalid_typed_value",
                       "prose_requires_labelled_extraction", "ambiguous_quantity_expression"})


def nominal_label(cell: "Cell") -> str | None:
    """The text this cell may be compared as when its attribute is NOMINAL, or None.

    DR 0029. One function because there were two: `derive._usable` decided what counted as
    published and `surface.verification._settled_value` decided what the reader emitted,
    they were written months apart, and on real feeds they disagreed 29 times out of 7,179
    probed variants -- derivation calling a source never usable while the reader emitted
    guaranteed evidence from it. Agreement between two rules is a thing that has to be
    maintained; one rule is a thing that cannot drift.

    Three ways to be a label, and the third is DR 0028: the merchant *enumerated* this
    value, so the whole string is one of the choices on offer whatever we failed to make of
    it. A gift card sold as `$35` is a selector label, not a money amount we may guess a
    currency for. Prose gets no such licence, which is the whole of the distinction.
    """
    # An absent cell has nothing to compare. It has to be refused here rather than by each
    # caller, because the selector branch below would otherwise read an empty option slot
    # as the label `None` -- which is what the two-rule version quietly did on one side.
    if not cell.present or cell.issue in _NOT_TEXT:
        return None
    if cell.value is not None or cell.issue in _LABEL_SAFE or cell.option:
        return cell.raw
    return None


@dataclass(frozen=True)
class Listing:
    group: str | None
    identity: str | None
    cells: tuple[Cell, ...]


def _prose_pairs(raw: str):
    # Only explicit, bounded label:value clauses. No execution, model, instructions,
    # free-text entity linking, or guessing what an unlabelled number refers to.
    text = unescape(re.sub(r"<[^>]*>", "\n", raw))
    for line in re.split(r"[\n;]", text):
        match = re.fullmatch(r"\s*([^:\n]{1,60}):\s*([^:\n]{1,160})\s*", line)
        if match:
            yield match[1].strip(), match[2].strip()


def flatten(obj: dict, *, path: tuple[str, ...] = (), skip: frozenset[tuple[str, ...]] = frozenset(),
            options: dict[int, OptionDefinition] | None = None, currency: str | None = None,
            policies: dict | None = None, depth: int = 0) -> list[Cell]:
    if depth > 32:
        raise ValueError("catalogue nesting exceeds 32 levels")
    cells: list[Cell] = []
    policies = policies or {}
    local_options = option_definitions(obj, path)
    options = local_options if local_options is not None else options or {}
    local_currencies = {str(v).strip() for k, v in obj.items()
                        if semantic_key(k) in {"currency", "currency_code"} and occupied(v)}
    # A contradictory local declaration must not fall back to deployment currency.
    if local_currencies:
        currency = next(iter(local_currencies)) if len(local_currencies) == 1 else "CONFLICT"

    def add(name, raw, field, *, prose=False, option=False, enumerated=False):
        policy = policies.get(field)
        certainty = Certainty.PARSED if prose else Certainty.EXACT
        liability = policy.liability if policy else Liability.MERCHANT_GUARANTEED
        advice = policy.is_advice if policy else False
        dim, value, issue = read_value(raw, name, currency=currency, option=option,
                                       enumerated=enumerated)
        if policy and policy.certainty is not Certainty.EXACT:
            certainty = policy.certainty if certainty is Certainty.EXACT else Certainty.INFERRED if policy.certainty is Certainty.INFERRED else certainty
        operational = bool(set(semantic_key(name).split("_")) & _OPERATIONAL)
        cells.append(Cell(key_name(name), field,
                          json.dumps(raw, sort_keys=True, ensure_ascii=False) if isinstance(raw, dict) else text_value(raw),
                          dim, value, issue, certainty, liability, option,
                          not (operational or dim is Dimension.MONEY or is_identifier(name) or prose or advice),
                          advice, occupied(raw) and raw != []))

    for key, value in obj.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("catalogue field names must be nonempty strings")
        current = path + (key,)
        source = path_text(current)
        name = semantic_key(key)
        if (current in skip or name in _META or is_rendering(key) or is_identifier(key)
                or name in _NAMESPACE | _URL):
            continue
        if name in _PROSE and isinstance(value, str):
            for label, reading in _prose_pairs(value):
                # Text cannot manufacture control fields or grant itself source trust.
                if semantic_key(label) not in _META and not is_rendering(label) and not is_identifier(label):
                    add(label, reading, source, prose=True)
            continue
        match = re.fullmatch(r"option_?(\d+)", name)
        if match:
            definition = options.get(int(match[1]))
            if definition:
                if selector_path(current, definition.name) in policies:
                    raise ValueError("source policy uses a legacy numbered-option locator; review and add its &table= binding")
                # DR 0028: the table that named this slot also enumerated its values.
                add(definition.name, value, selector_path(current, definition.name, table=definition.table),
                    option=True, enumerated=True)
            # Unnamed numbered selectors have no recoverable attribute name.
            continue
        if isinstance(value, dict):
            if ("amount" in value and set(value) <= {"amount", "currency"}) or ("unit" in value and set(value) <= {"unit", "value", "magnitude"}):
                add(key, value, source)
            elif pair(value):
                label_key, value_key = pair(value)
                add(value[label_key], value[value_key], selector_path(current + (value_key,), value[label_key]), option=True)
            else:
                cells.extend(flatten(value, path=current, skip=skip, options=options,
                                     currency=currency, policies=policies, depth=depth + 1))
        elif isinstance(value, list):
            paired = False
            for item in value:
                if isinstance(item, dict) and pair(item):
                    paired = True
                    label_key, value_key = pair(item)
                    add(item[label_key], item[value_key], selector_path(current + ("\0", value_key), item[label_key]), option=True)
            # Arrays of possible values are not the selected value. No cartesian products.
            if not paired and not any(isinstance(item, dict) and "name" in item and "values" in item for item in value):
                add(key, value, source)
        elif isinstance(value, (str, bool, int, float)) or value is None:
            add(key, value, source)
    return cells


def _flat_group(record: dict) -> str | None:
    namespace = tuple(sorted((k, str(v)) for k, v in record.items() if semantic_key(k) in _NAMESPACE))
    for key, value in sorted(record.items()):
        if semantic_key(key) in _GROUP and occupied(value):
            return json.dumps((namespace, key, value), sort_keys=True)
        if semantic_key(key) in _URL and isinstance(value, str):
            url = urlsplit(value)
            if url.scheme in {"http", "https"} and url.netloc and url.path.strip("/"):
                return json.dumps((namespace, key, value))
    return None


def discover(records: list[dict], *, currency: str | None = None, policies: dict | None = None):
    listings: list[Listing] = []
    warnings: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict) or any(not isinstance(k, str) for k in record):
            raise ValueError(f"record {index} must be an object with string keys")
        collections = variant_collections(record)
        if len(collections) > 1:
            warnings.add("ambiguous_variant_collections: supply one sellable collection per record")
            listings.append(Listing(None, None, ()))
            continue
        if not collections:
            cells = flatten(record, currency=currency, policies=policies)
            listings.append(Listing(_flat_group(record), identity(record), tuple(cells)))
            continue
        path, variants = collections[0]
        if not variants:
            warnings.add("empty_variant_collection: no sellable listing established")
            listings.append(Listing(None, None, ()))
            continue
        parent = [replace(c, option=False) for c in flatten(record, skip=frozenset({path}), currency=currency, policies=policies)]
        definitions = {}
        parent_currency = currency
        ancestor = record
        ancestor_path = ()
        for segment in (*path[:-1], None):
            local_definitions = option_definitions(ancestor, ancestor_path)
            if local_definitions is not None:
                definitions = local_definitions
            codes = {v for k, v in ancestor.items() if semantic_key(k) in {"currency", "currency_code"} and isinstance(v, str)}
            if codes:
                parent_currency = next(iter(codes)) if len(codes) == 1 else "CONFLICT"
            if segment is not None:
                ancestor = ancestor[segment]
                ancestor_path += (segment,)
        for variant in variants:
            if not identity(variant):
                warnings.add("variant_identity_missing: axis evidence requires distinct identifiers")
            children = flatten(variant, path=path + ("\0",), options=definitions,
                               currency=parent_currency, policies=policies)
            # Selected child values take precedence over inherited values of the same
            # attribute, including explicit nulls: never fill a missing SKU value from
            # an unrelated parent's similarly named field.
            child_names = {c.name for c in children} | {key_name(k) for k in variant}
            cells = [c for c in parent if c.name not in child_names] + children
            listings.append(Listing(f"record:{index}", identity(variant), tuple(cells)))
    return listings, warnings
