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


def format_locator(segments: tuple[str | None, ...], *, selector: str | None = None) -> str:
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
    return path


def parse_locator(text: str) -> Locator:
    """Reject malformed/noncanonical syntax; never fall back to a dotted lookup."""
    if not isinstance(text, str) or not text.startswith("/"):
        raise ValueError("a source locator must start with /")
    path, separator, suffix = text.partition("#")
    selector = None
    if separator:
        if not suffix.startswith("name="):
            raise ValueError("unknown source selector")
        try:
            selector = unquote(suffix[5:], encoding="utf-8", errors="strict")
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
    locator = Locator(tuple(parts), selector)
    if format_locator(locator.segments, selector=locator.selector) != text:
        raise ValueError("noncanonical source locator")
    return locator
