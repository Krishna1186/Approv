"""Open Food Facts records into typed Evidence.

OFF is ODbL: commercial use is permitted with attribution, and share-alike binds only if
a *derived database* is republished. §5's "publish the number, never the corpus" keeps us
clear of that, but the position should be confirmed by a lawyer before any public claim
rests on it.

Two things learned from 599 real Indian-market records on 2026-09-07, both of which
shaped this module:

**`product_quantity` is not independent of `quantity`.** 93.4% of the time it is exactly
what you get by parsing the `quantity` string. They are one fact, so this loader emits
`quantity` and ignores `product_quantity`. Emitting both would manufacture a corroboration
that does not exist — two fields agreeing means nothing if one was computed from the other.

**17% of quantity strings carry no usable unit.** Real values include `'1'`, `'75'`,
`'1.73 - 3.00'`, `','` and `'2pcs'`. Every one of those returns None here. A bare number is
the "1x1x1 box" case in the wild, and guessing its unit is the exact failure the
architecture exists to prevent: extraction either produces a typed value or it produces
nothing.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from approv.types.core import (
    Certainty,
    Dimension,
    Evidence,
    Liability,
    Quantity,
    Term,
)

# Unit spellings seen in the wild, mapped to canonical units. This is an alias table, not
# fuzzy matching: every entry is an explicit decision that one spelling means another, and
# the table can be read and disputed. "litter" is a real typo in the data.
_UNIT_ALIASES = {
    "g": "g", "gm": "g", "gms": "g", "gr": "g", "gram": "g", "grams": "g", "grm": "g",
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilogram": "kg", "kilograms": "kg",
    "mg": "mg",
    "ml": "ml", "millilitre": "ml", "milliliter": "ml", "mls": "ml",
    "cl": "cl",
    "l": "l", "lt": "l", "ltr": "l", "litre": "l", "liter": "l", "litres": "l",
    "liters": "l", "litter": "l",
}

_DIMENSION_OF = {
    "mg": Dimension.MASS, "g": Dimension.MASS, "kg": Dimension.MASS,
    "ml": Dimension.VOLUME, "cl": Dimension.VOLUME, "l": Dimension.VOLUME,
}

_QUANTITY = re.compile(
    r"^\s*(?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>[a-zA-Z]+)\s*$", re.UNICODE
)
_RANGE = re.compile(r"\d\s*[-–—]\s*\d")
_MULTIPACK = re.compile(
    r"^\s*(?P<count>\d+)\s*[x×*]\s*(?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>[a-zA-Z]+)\s*$",
    re.UNICODE | re.IGNORECASE,
)


def _to_decimal(raw: str) -> Decimal | None:
    # A comma is a decimal point in "1,5 L" but a thousands separator in "1,500 g".
    # Treat it as a decimal point only when one or two digits follow, and refuse
    # otherwise rather than picking a reading.
    if "," in raw:
        head, _, tail = raw.partition(",")
        if len(tail) in (1, 2) and tail.isdigit():
            raw = f"{head}.{tail}"
        else:
            return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def parse_quantity(text: str | None) -> tuple[Quantity | None, int | None]:
    """Parse a raw quantity string into a typed Quantity and an optional pack count.

    Returns `(None, None)` for anything that is not unambiguously a quantity. That
    includes bare numbers, ranges, and counts like "2pcs" — refusing is the point.
    """
    if not text:
        return None, None

    cleaned = unicodedata.normalize("NFKC", str(text)).strip()
    if not cleaned or _RANGE.search(cleaned):
        return None, None

    count = None
    match = _MULTIPACK.match(cleaned)
    if match:
        count = int(match.group("count"))
    else:
        match = _QUANTITY.match(cleaned)
    if not match:
        return None, None

    unit = _UNIT_ALIASES.get(match.group("unit").lower())
    if unit is None:
        return None, count

    number = _to_decimal(match.group("number"))
    if number is None:
        return None, count

    if count is not None:
        number = number * count

    return Quantity(magnitude=number, unit=unit, dimension=_DIMENSION_OF[unit]), count


def evidence_from(record: dict) -> tuple[Evidence, ...]:
    """Build typed Evidence from one OFF product record.

    Field profiles reflect the two axes from DR 0016. OFF is contributor-authored rather
    than merchant-authored, so nothing here is `MERCHANT_GUARANTEED` — nobody owes a
    remedy for a wrong OFF field. That is a real limitation of this corpus and it is
    recorded in the data rather than hidden.
    """
    out: list[Evidence] = []

    brands = (record.get("brands") or "").strip()
    if brands:
        out.append(
            Evidence(
                attribute="brand",
                value=Term(surface=brands.split(",")[0].strip()),
                field_name="brands",
                liability=Liability.PLATFORM_DERIVED,
                certainty=Certainty.EXACT,
                raw_text=brands,
            )
        )

    name = (record.get("product_name") or "").strip()
    if name:
        out.append(
            Evidence(
                attribute="brand",
                value=Term(surface=name),
                field_name="product_name",
                liability=Liability.PLATFORM_DERIVED,
                certainty=Certainty.PARSED,
                raw_text=name,
            )
        )

    quantity, count = parse_quantity(record.get("quantity"))
    if quantity is not None:
        attribute = "net_weight" if quantity.dimension is Dimension.MASS else "net_volume"
        out.append(
            Evidence(
                attribute=attribute,
                value=quantity,
                field_name="quantity",
                liability=Liability.PLATFORM_DERIVED,
                certainty=Certainty.EXACT,
                raw_text=str(record.get("quantity")),
            )
        )

    return tuple(out)
