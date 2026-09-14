"""Conservative value reading for onboarding; no merchant or category vocabulary.

An occupied field is not necessarily a usable value. In particular, a currency-less
price and an unqualified decimal are not silently turned into nominal evidence.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from approv.types.core import Count, Dimension, Money, Quantity, Term

VERSION = "schema-onboarding-v2"
NUMBER = r"(?:0|[1-9]\d*)(?:\.\d+)?"
_NUMBER = re.compile(NUMBER)
_MONEY = re.compile(rf"(?:(?P<before>[A-Z]{{3}})\s+(?P<a>{NUMBER})|(?P<b>{NUMBER})\s+(?P<after>[A-Z]{{3}}))")
_QUANTITY = re.compile(rf"(?P<n>{NUMBER})\s*(?P<u>[a-zA-Z_ ]+|\")")
_COUNT = re.compile(rf"(?P<n>\d+)\s*(?:count|ct|pcs?|pieces?|units?)", re.I)
_UNITS = {
    **dict.fromkeys(("mg", "g", "kg", "oz", "lb"), Dimension.MASS),
    **dict.fromkeys(("ml", "cl", "l", "us_fl_oz", "imperial_fl_oz"), Dimension.VOLUME),
    **dict.fromkeys(("mm", "cm", "m", "in", "ft"), Dimension.LENGTH),
}
_ALIASES = {"grams": "g", "gram": "g", "kilograms": "kg", "kilogram": "kg",
            "lbs": "lb", "pounds": "lb", "pound": "lb", "ounces": "oz",
            "ounce": "oz", "litre": "l", "litres": "l", "liter": "l",
            "liters": "l", "milliliters": "ml", "millilitres": "ml",
            "inches": "in", "inch": "in", '"': "in", "feet": "ft",
            "meters": "m", "metres": "m", "us fl oz": "us_fl_oz",
            "imperial fl oz": "imperial_fl_oz"}
_EMPTY = {"", "n/a", "null", "none", "unknown", "not specified", "-"}
_PRICE = re.compile(r"(?:^|_)(?:price|cost|amount|msrp)(?:_|$)")


def key_name(key: str) -> str:
    return re.sub(r"\s+", "_", key.strip().casefold())


def semantic_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", re.sub(r"([a-z])([A-Z])", r"\1_\2", key).lower()).strip("_")


def occupied(value: object) -> bool:
    return value is not None and (not isinstance(value, str) or value.strip().casefold() not in _EMPTY)


def text_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def read_value(value: object, name: str, *, currency: str | None = None,
               option: bool = False) -> tuple[Dimension | None, object | None, str | None]:
    """Return a dimension, typed value and diagnostic; never infer a currency.

    Integers in option selectors are labels (shoe size 9 is not a count). A quantity
    object must carry both magnitude and unit; a money object both amount and currency.
    Unit spellings here are only those supported by the existing quantity comparator.
    """
    if not occupied(value):
        return None, None, None
    try:
        if isinstance(value, dict):
            if set(value) <= {"amount", "currency"} and "amount" in value:
                dimension, typed, issue = read_value(value["amount"], "price", currency=value.get("currency", currency))
                if dimension is not Dimension.MONEY:
                    return Dimension.MONEY, None, "invalid_money_amount"
                return dimension, typed, issue
            if set(value) <= {"value", "magnitude", "unit"} and "unit" in value:
                magnitude = value.get("magnitude", value.get("value"))
                return read_value(f"{magnitude} {value['unit']}", name)
            return None, None, "unsupported_object"
        if isinstance(value, list):
            return None, None, "multivalued_field_requires_mapping" if value else None
        raw = text_value(value)
        if len(raw) > 512:
            return None, None, "prose_requires_labelled_extraction"
        if isinstance(value, bool):
            return Dimension.NOMINAL, Term(surface=raw), None
        match = _MONEY.fullmatch(raw)
        if match:
            code = match["before"] or match["after"]
            if currency and currency != code:
                return Dimension.MONEY, None, "currency_conflict"
            return Dimension.MONEY, Money(amount=Decimal(match["a"] or match["b"]), currency=code), None
        if raw[:1] in {"$", "€", "£", "¥", "₹"}:
            # Even '$' is ambiguous between currencies. Configuration must supply it.
            symbols = {"€": {"EUR"}, "£": {"GBP"}, "₹": {"INR"},
                       "¥": {"JPY", "CNY"}, "$": {"USD", "CAD", "AUD", "NZD", "SGD", "HKD"}}
            if _NUMBER.fullmatch(raw[1:].strip()):
                if currency in symbols[raw[0]]:
                    return Dimension.MONEY, Money(amount=Decimal(raw[1:].strip()), currency=currency), None
                return Dimension.MONEY, None, "currency_missing_or_ambiguous"
        match = _COUNT.fullmatch(raw)
        if match:
            return Dimension.COUNT, Count(n=int(match["n"])), None
        match = _QUANTITY.fullmatch(raw)
        if match:
            unit = _ALIASES.get(match["u"].strip().lower(), match["u"].strip().lower())
            if unit in _UNITS:
                dim = _UNITS[unit]
                return dim, Quantity(magnitude=Decimal(match["n"]), unit=unit, dimension=dim), None
            return None, None, "unknown_or_ambiguous_unit"
        if _NUMBER.fullmatch(raw):
            unit_key = semantic_key(name).split("_")[-1]
            unit = _ALIASES.get(unit_key, unit_key)
            if unit in _UNITS and not option:
                return _UNITS[unit], Quantity(magnitude=Decimal(raw), unit=unit, dimension=_UNITS[unit]), None
            if _PRICE.search(semantic_key(name)):
                if currency:
                    return Dimension.MONEY, Money(amount=Decimal(raw), currency=currency), None
                return Dimension.MONEY, None, "currency_missing_or_ambiguous"
            if option:
                return Dimension.NOMINAL, Term(surface=raw), None
            if "." not in raw and not (len(raw) > 1 and raw.startswith("0")):
                return Dimension.COUNT, Count(n=int(raw)), None
            return None, None, "unitless_decimal"
        if isinstance(value, (int, float, Decimal)) or raw.casefold() in {"nan", "inf", "infinity"}:
            return None, None, "invalid_number"
        if re.match(r"^[+-]?\d", raw) and re.search(r"\d\s*(?:fl\s*oz|[kcm]?g|[mc]?l)\b", raw, re.I):
            return None, None, "ambiguous_quantity_expression"
        if isinstance(value, str):
            return Dimension.NOMINAL, Term(surface=raw), None
        return None, None, "unsupported_value"
    except (ValidationError, InvalidOperation, ValueError, OverflowError, TypeError):
        return None, None, "invalid_typed_value"
