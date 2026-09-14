"""The catalogue-locator-v1 wire grammar; resolution belongs to surface.

None is an array step. Strings are literal object keys, including dots and '*'.
This codec does not read a product or turn a selector into evidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, unquote

VERSION = "catalogue-locator-v1"
LABEL_KEYS = ("name", "label", "attribute", "key", "option")
VALUE_KEYS = ("value", "selected_value", "selection", "choice")
_ESCAPES = {"0": "~", "1": "/", "2": "*", "3": "#"}


@dataclass(frozen=True)
class Locator:
    segments: tuple[str | None, ...]
    selector: str | None = None
    table: tuple[str | None, ...] | None = None


def format_locator(segments: tuple[str | None, ...], *, selector: str | None = None,
                   table: tuple[str | None, ...] | None = None) -> str:
    if not segments:
        raise ValueError("a source locator must name a field")
    encoded = []
    for part in segments:
        if part is None:
            encoded.append("*")
        elif not isinstance(part, str) or not part.strip() or any(ord(c) < 32 for c in part):
            raise ValueError("source keys must be nonempty strings without control characters")
        else:
            encoded.append(part.replace("~", "~0").replace("/", "~1").replace("*", "~2").replace("#", "~3"))
    path = "/" + "/".join(encoded)
    if selector is not None:
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError("a selector must contain an option name")
        path += "#name=" + quote(selector, safe="")
    if table is not None:
        if selector is None:
            raise ValueError("an option table requires a name guard")
        path += "&table=" + quote(format_locator(table), safe="")
    return path


def parse_locator(text: str) -> Locator:
    """Reject malformed/noncanonical syntax; never fall back to a dotted lookup."""
    if not isinstance(text, str) or not text.startswith("/"):
        raise ValueError("a source locator must start with /")
    path, separator, suffix = text.partition("#")
    selector = None
    table = None
    if separator:
        parameters = suffix.split("&")
        if len(parameters) > 2 or not parameters[0].startswith("name="):
            raise ValueError("unknown source selector")
        if len(parameters) == 2 and not parameters[1].startswith("table="):
            raise ValueError("unknown option-table parameter")
        try:
            selector = unquote(parameters[0][5:], encoding="utf-8", errors="strict")
            if len(parameters) == 2:
                table_text = unquote(parameters[1][6:], encoding="utf-8", errors="strict")
                # A table is a plain pointer, never another selector or a URL.
                if "#" in table_text:
                    raise ValueError("an option table must be a plain source pointer")
                table = parse_locator(table_text).segments
        except UnicodeError as error:
            raise ValueError("invalid UTF-8 selector") from error
    parts = []
    for part in path[1:].split("/"):
        if part == "*":
            parts.append(None)
        else:
            if re.search(r"~(?![0-3])", part):
                raise ValueError("invalid source-key escape")
            parts.append(re.sub(r"~([0-3])", lambda m: _ESCAPES[m[1]], part))
    locator = Locator(tuple(parts), selector, table)
    if format_locator(locator.segments, selector=locator.selector, table=locator.table) != text:
        raise ValueError("noncanonical source locator")
    return locator
