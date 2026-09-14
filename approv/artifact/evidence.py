"""The cart-only receipt, rendered as the lesser thing it is.

`OrderEvidenceRecord` exists because cart contents cannot supply the request half: an
adapter that receives only a final cart knows what was bought and nothing about what was
asked for. The type is chosen before the comparison rather than described after one, and
**this module is the same decision on the reading surface**.

So it is a separate document and a separate page, not the dispute artifact with sections
left out. A degraded version of the stronger page is exactly the failure the type was
created to end: a returns desk reads the heading, and a heading that says what the
dispute artifact's says, over a page that happens to be shorter, is read as a
verification that went quietly.

**What the page must never let a reader come away with.** That anything was authorised.
That any attribute was checked. That anything is covered. Each of those is stated in the
negative, near the top, before the order details a reader is looking for - because a
reader who finds what they came for stops reading, and the limits have to be above that
point rather than below it.

What it *does* carry is a real evidence product and is worth stating plainly: which line
of which order, at what price, in what availability state, against the catalogue as it
stood, at a recorded time, signed and chained like any other receipt.
"""

from __future__ import annotations

import html as html_escape
import textwrap
from dataclasses import dataclass

from approv.artifact import signature
from approv.artifact.document import Row, order_rows, product_rows

VERSION = "artifact-evidence-v1"

WIDTH = 80

TITLE = "ORDER EVIDENCE"

SUBTITLE = "NOT A VERIFICATION. No stated request reached Approv for this order."

WHAT_IT_IS = (
    "This is a signed record of what was sold: which line of which order, at what price, "
    "in what availability state, against the merchant's catalogue as it stood, at a "
    "recorded time. It is the strongest thing an order with no stated request can "
    "honestly produce, and it is weaker than a verification."
)

# Said in the negative, above the details, because a reader who finds what they came for
# stops reading. Each line is a thing somebody could otherwise assume from the fact that a
# signed Approv document exists at all.
DOES_NOT_ESTABLISH = (
    "Nothing was authorised, refused or asked about. There is no decision on this record "
    "because no request arrived to decide anything about.",
    "No attribute was checked. Approv compares a stated request against published "
    "catalogue data, and with no stated request there is nothing to compare - not a "
    "comparison that came back clean.",
    "Nothing here is covered. Coverage attaches to a channel that carries a stated "
    "request; this order arrived through one that did not, and there is no guarantee to "
    "withdraw because none ever attached.",
    "This says nothing about whether the customer got what they wanted. It says what the "
    "merchant sold and what their catalogue said about it.",
)

WHY_NO_REQUEST = (
    "Recorded in the words of whoever knew, and not rewritten. A record that said only "
    "\"no request\" would invite a reader to supply their own reason for it."
)

NO_REASONS = (
    "The record carries no account of why no stated request was available. That is a gap "
    "in what was recorded, not evidence that the order was ordinary."
)


@dataclass(frozen=True)
class EvidenceDocument:
    """Everything the renderers print for a cart-only receipt."""

    record: object
    identity: tuple[Row, ...] = ()
    reasons: tuple[str, ...] = ()
    order: tuple[Row, ...] = ()
    product: tuple[Row, ...] = ()
    integrity: tuple[Row, ...] = ()
    signed: bool = False
    # Read off the record rather than assumed. `eligible` is hard-wired false on the type
    # and is printed anyway: a reader should not have to know that the absence of a
    # coverage block means what it means.
    eligible: bool = False
    aborted: str | None = None


def _identity(record) -> tuple[Row, ...]:
    return (
        Row("Recorded at", record.timestamp.isoformat()),
        Row("Merchant", record.merchant_id or "", missing=record.merchant_id is None),
        Row("Reference", record.correlation_id),
        Row("How the order reached us", record.shape.value.replace("_", " "),
            note="no stated request accompanied it, which is what makes this document "
                 "the product it is."),
        Row("Agent involvement", record.agent.value.replace("_", " "),
            missing=record.agent.value == "unknown",
            note="recorded rather than inferred. A merchant whose checkout detects "
                 "agents knows; Approv does not guess on their behalf."),
        Row("Category", "%s (schema %s)" % (record.category_id, record.category_version)),
    )


def _integrity(record) -> tuple[Row, ...]:
    sealed = bool(getattr(record, "hash", None) and getattr(record, "signature", None))
    rows = [
        Row("Record digest", record.hash or "", missing=not record.hash,
            note="the digest this record was signed over."),
        Row("Previous record", record.prev_hash or "",
            missing=record.prev_hash is None,
            note="the receipt before this one in the merchant's chain. The first record "
                 "in a chain has none."),
        Row("Signature", record.signature or "", missing=not record.signature),
        Row("Signing key", record.key_id or "", missing=record.key_id is None),
        Row("Signature scheme", record.signature_version),
        Row("Verification", "signed and chained" if sealed else "",
            missing=not sealed,
            note=None if sealed else
            "This record carries no signature, so nothing below can be checked and "
            "nothing about it should be relied on in a dispute."),
    ]
    completion = getattr(record, "completion", None)
    if completion is not None and getattr(completion, "value", "") != "completed":
        rows.append(Row("Recording did NOT complete",
                        getattr(record, "completion_detail", None) or completion.value,
                        missing=True,
                        note="Approv's own failure, not the merchant's and not the "
                             "customer's."))
    return tuple(rows)


def build_evidence(record) -> EvidenceDocument:
    """Arrange one cart-only receipt as a document. Reads the record and adds no facts."""
    completion = getattr(record, "completion", None)
    aborted = (getattr(record, "completion_detail", None) or completion.value
               if completion is not None and getattr(completion, "value", "") != "completed"
               else None)
    return EvidenceDocument(
        record=record,
        identity=_identity(record),
        reasons=tuple(record.reasons),
        order=order_rows(record),
        product=product_rows(record),
        integrity=_integrity(record),
        signed=bool(record.hash and record.signature),
        eligible=bool(getattr(record, "eligible", False)),
        aborted=aborted,
    )


# --------------------------------------------------------------------------------------
# Plain text
# --------------------------------------------------------------------------------------


def _wrap(text: str, indent: str = "  ") -> str:
    return textwrap.fill(text, width=WIDTH, initial_indent=indent,
                         subsequent_indent=indent)


def _bullet(text: str, indent: str = "  ") -> str:
    """A bullet whose wrapped lines sit under its text rather than under its dash.

    Small, and it is the difference between a list of limits that reads as a list and one
    that reads as a paragraph somebody forgot to format. These are the four sentences a
    reader most needs to take in.
    """
    return textwrap.fill(text, width=WIDTH, initial_indent=indent + "- ",
                         subsequent_indent=indent + "  ")


def _rows(rows: tuple[Row, ...], indent: str = "  ") -> list[str]:
    out = []
    for row in rows:
        value = row.value or ("(not recorded)" if row.missing else "")
        label = row.label + " " + "." * max(2, 40 - len(row.label))
        head = "%s%s %s" % (indent, label, value)
        if len(head) <= WIDTH or " " not in value.strip():
            out.append(head)
        else:
            out.append("%s%s" % (indent, label))
            out.append(_wrap(value, indent + "    "))
        if row.note:
            out.append(_wrap(row.note, indent + "    "))
    return out


def to_text(document: EvidenceDocument, *, public_key: str | None = None,
            record_file: str = "record.json") -> str:
    """The page as plain text. Banded differently from the dispute artifact on purpose.

    The two documents are told apart at a glance and before a word is read: this one opens
    with a line of `~` and the words NOT A VERIFICATION, and it never prints a verdict
    headline, an attribute table or a coverage line, because it has none of those things
    to print.
    """
    out = ["~" * WIDTH, TITLE, SUBTITLE, "~" * WIDTH, "",
           "WHAT THIS IS", _wrap(WHAT_IT_IS), "",
           "WHAT THIS DOES NOT ESTABLISH"]
    for item in DOES_NOT_ESTABLISH:
        out.append(_bullet(item))
    out.append("")
    if document.aborted:
        out += ["!" * WIDTH,
                _wrap("Recording this order did not run to a conclusion: %s. That is "
                      "Approv's failure. Treat what follows as incomplete."
                      % document.aborted),
                "!" * WIDTH, ""]

    out += ["WHY THERE WAS NO STATED REQUEST", _wrap(WHY_NO_REQUEST), ""]
    if document.reasons:
        for reason in document.reasons:
            out.append(_bullet(reason))
    else:
        out.append(_wrap(NO_REASONS))
    out.append("")

    out += ["THE ORDER"] + _rows(document.order) + [""]
    out += ["THE PRODUCT, AS THE MERCHANT'S CATALOGUE DESCRIBED IT"]
    out += _rows(document.product) + [""]
    out += ["THIS RECORD"] + _rows(document.identity) + _rows(document.integrity) + [""]
    out += ["HOW TO CHECK THIS RECORD YOURSELF"]
    steps = signature.STEPS if document.signed else signature.UNSIGNED_STEPS
    for step in steps:
        out.append(_bullet(step))
    out.append("")
    out.append(signature.snippet(public_key, record_file))
    out.append("")
    for line in signature.CANNOT_PROVE:
        out.append(_bullet(line))
    page = "\n".join(out).rstrip() + "\n"
    return "\n".join(line.rstrip() for line in page.split("\n"))


# --------------------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------------------

_CSS = """
:root { color-scheme: light; }
body { margin: 0; background: #f3f2ef; color: #1a1a1a;
       font: 15px/1.6 ui-sans-serif, system-ui, "Segoe UI", Helvetica, Arial, sans-serif; }
main { max-width: 50rem; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
/* Deliberately not the dispute artifact's header. A reader who has seen both must be
   able to tell them apart across a desk, before reading a word. */
header.doc { background: #5c5a54; color: #fff; padding: 1.1rem 1rem;
             border-bottom: 6px solid #b8860b; }
header.doc .inner { max-width: 50rem; margin: 0 auto; }
header.doc h1 { margin: 0 0 .25rem; font-size: 1.05rem; letter-spacing: .12em;
                text-transform: uppercase; font-weight: 600; }
header.doc p { margin: 0; font-size: .95rem; font-weight: 700; color: #ffe7a8;
               letter-spacing: .02em; }
section { background: #fff; border: 1px solid #dedcd6; padding: .9rem 1.1rem;
          margin: 1rem 0; }
section > h2 { font-size: .78rem; letter-spacing: .11em; text-transform: uppercase;
               margin: 0 0 .8rem; color: #55534d; border-bottom: 1px solid #eae8e2;
               padding-bottom: .45rem; }
.lesser { background: #fff8e6; border: 2px solid #b8860b; padding: .9rem 1.1rem;
          margin: 1.1rem 0; }
.lesser ul { margin: .5rem 0 0; padding-left: 1.1rem; }
.lesser li { margin: .35rem 0; }
.aborted { border: 2px solid #a31515; background: #fff6f6; color: #7a1010;
           padding: .9rem 1.1rem; margin: 1.1rem 0; font-weight: 600; }
dl.rows { display: grid; grid-template-columns: minmax(9rem, 18rem) 1fr; gap: .3rem .9rem;
          margin: 0; }
dl.rows dt { color: #55534d; }
dl.rows dd { margin: 0; word-break: break-word; }
dl.rows dd .note { display: block; color: #6b7280; font-size: .86rem; }
.missing { color: #a31515; font-style: italic; }
pre { background: #1d1c1a; color: #eee; padding: .9rem; overflow-x: auto;
      font-size: .82rem; line-height: 1.45; }
ul.reasons { padding-left: 1.1rem; }
footer { color: #55534d; font-size: .9rem; }
@media print { body { background: #fff; } section { break-inside: avoid; } }
"""


def _e(text) -> str:
    return html_escape.escape(str(text), quote=False)


def _rows_html(rows: tuple[Row, ...]) -> str:
    out = ['<dl class="rows">']
    for row in rows:
        value = ('<span class="missing">not recorded</span>'
                 if row.missing and not row.value else _e(row.value))
        if row.missing and row.value:
            value = '<span class="missing">%s</span>' % value
        note = '<span class="note">%s</span>' % _e(row.note) if row.note else ""
        out.append("<dt>%s</dt><dd>%s%s</dd>" % (_e(row.label), value, note))
    out.append("</dl>")
    return "\n".join(out)


def to_html(document: EvidenceDocument, *, public_key: str | None = None,
            record_file: str = "record.json") -> str:
    reasons = ("<ul class=\"reasons\">%s</ul>"
               % "".join("<li>%s</li>" % _e(r) for r in document.reasons)
               if document.reasons else "<p class=\"missing\">%s</p>" % _e(NO_REASONS))
    aborted = ('<div class="aborted">Recording this order did not run to a conclusion: '
               "%s. That is Approv's failure. Treat what follows as incomplete.</div>"
               % _e(document.aborted)) if document.aborted else ""
    steps = signature.STEPS if document.signed else signature.UNSIGNED_STEPS
    sections = [
        ("What this is", "<p>%s</p>" % _e(WHAT_IT_IS)),
        ("Why there was no stated request",
         "<p>%s</p>%s" % (_e(WHY_NO_REQUEST), reasons)),
        ("The order", _rows_html(document.order)),
        ("The product, as the merchant's catalogue described it",
         _rows_html(document.product)),
        ("This record", _rows_html(document.identity + document.integrity)),
        ("How to check this record yourself",
         "<ul>%s</ul><pre>%s</pre><footer><ul>%s</ul></footer>"
         % ("".join("<li>%s</li>" % _e(s) for s in steps),
            _e(signature.snippet(public_key, record_file)),
            "".join("<li>%s</li>" % _e(c) for c in signature.CANNOT_PROVE))),
    ]
    body = "\n".join("<section><h2>%s</h2>%s</section>" % (_e(heading), content)
                     for heading, content in sections)
    limits = ('<div class="lesser"><strong>What this does not establish</strong><ul>%s'
              "</ul></div>"
              % "".join("<li>%s</li>" % _e(item) for item in DOES_NOT_ESTABLISH))
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>%s - %s</title>\n<style>%s</style>\n</head>\n<body>\n"
        '<header class="doc"><div class="inner"><h1>%s</h1><p>%s</p></div></header>\n'
        "<main>\n%s\n%s\n%s\n</main>\n</body>\n</html>\n"
        % (_e(TITLE), _e(document.record.correlation_id), _CSS, _e(TITLE), _e(SUBTITLE),
           limits, aborted, body))


def render_text(record, *, public_key: str | None = None,
                record_file: str = "record.json") -> str:
    return to_text(build_evidence(record), public_key=public_key,
                   record_file=record_file)


def render_html(record, *, public_key: str | None = None,
                record_file: str = "record.json") -> str:
    return to_html(build_evidence(record), public_key=public_key,
                   record_file=record_file)
