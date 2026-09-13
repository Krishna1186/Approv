"""Two renderings of one document: plain text and a self-contained HTML page.

Both take the same `Document` and print the same sections in the same order, because a
returns desk and the counterparty they are arguing with must be able to refer to the same
numbered section. Neither renderer reads the record, decides anything, or adds a fact —
if a sentence is not in `document.py` or `language.py` it is not on the page.

The HTML carries the record's own JSON inside it, so the document and the evidence cannot
be separated in an email thread. That is also what makes the verification instructions
actionable: the file a reader is told to check is the file they are already looking at.
"""

from __future__ import annotations

import html as html_escape
import textwrap

from approv.artifact import language as lang, signature
from approv.artifact.document import (
    STOP, AttributeFinding, Document, Requirement, Row, build,
)
from approv.types.core import ComparisonRecord, Support

VERSION = "artifact-render-v1"

WIDTH = 88
_LABEL = 34

TITLE = "APPROV ORDER VERIFICATION RECORD"

# The sections, in the order both renderers print them. A dispute is argued by reference,
# so the numbering is part of the document rather than decoration.
HEADINGS = (
    "1. WHAT WAS ASKED FOR",
    "2. WHAT WAS DELIVERED",
    "3. ATTRIBUTE BY ATTRIBUTE",
    "4. WHAT THIS RECORD COVERS",
    "5. CHECKING THIS RECORD YOURSELF",
    "6. WHAT THIS DOCUMENT DOES NOT SAY",
)

DETAILS_HEADING = "RECORD DETAILS"

UNREAD_MEANS = (
    "Approv could not encode these parts of the request, so it never checked them. This "
    "is Approv's own failure, not the requester having stayed silent, and nothing below "
    "attributes it to them."
)

NEVER_ASKED_MEANS = (
    "The request said nothing about these, so nothing was checked and nobody is at "
    "fault. They are outside coverage for the same reason: a record cannot claim to have "
    "honoured a requirement nobody made."
)

NO_REQUIREMENTS = (
    "No requirement was recovered from this request. Approv read nothing it could check, "
    "so this record shows what was sold and not that it matched anything."
)

NO_FINDINGS = "No attribute was compared, so this record carries no findings at all."

CLOSING = (
    "This document says what was asked for, what was sold, and what Approv compared "
    "between them at the moment of decision.",
    "It does not say whether the catalogue was accurate, whether the item arrived, "
    "whether it was damaged, or whether the customer is satisfied. It does not say what "
    "the human behind the agent actually wanted. Approv never sees that, only what the "
    "agent stated on their behalf.",
    "A vague request satisfies almost anything. Where the request was thin this record "
    "proves correspondingly little, and the sections above say exactly where that is.",
)


# --------------------------------------------------------------------------------------
# Plain text
# --------------------------------------------------------------------------------------


def _wrap(text: str, indent: str = "", width: int = WIDTH) -> str:
    return textwrap.fill(text, width=width, initial_indent=indent,
                         subsequent_indent=indent) if text else ""


def _hang(text: str, first: str, rest: str) -> str:
    """A list item whose continuation lines sit under its text, not under its marker.

    Cosmetic everywhere except the numbered verification steps, where a continuation
    line flush with the next step's number turns a procedure into a paragraph and the
    procedure is the part a stranger has to follow exactly.
    """
    return textwrap.fill(text, width=WIDTH, initial_indent=first, subsequent_indent=rest)


def _row_lines(row: Row, indent: str = "  ") -> list[str]:
    """One `label ....... value` line, with prose values wrapped and tokens left whole.

    A digest or a signature must survive being copied out of this document, so a value
    with no spaces in it is never broken across lines however far it runs past the
    margin. A sentence is wrapped under the label instead.
    """
    value = "(not recorded)" if row.missing else row.value
    label = row.label + " " + "." * max(2, _LABEL - len(row.label))
    head = f"{indent}{label} {value}"
    if len(head) > WIDTH and " " in value.strip():
        lines = [f"{indent}{label}", _wrap(value, indent + " " * 4)]
    else:
        lines = [head]
    if row.note:
        lines.append(_wrap(row.note, indent + " " * 4))
    return lines


def _requirement_lines(req: Requirement) -> list[str]:
    lines = [f"  {req.attribute}: {req.value}"]
    if req.quote:
        lines.append(_wrap(f'read from the words "{req.quote}"', "      "))
    where = req.provenance
    if req.source:
        where += f" (field: {req.source})"
    lines.append(_wrap(where, "      "))
    return lines


def _finding_lines(item: AttributeFinding) -> list[str]:
    lines = [f"  [{item.verdict}] {item.attribute}"
             f"  |  {item.weight}  |  {item.coverage_label}"]
    indent, hang = "      ", "        "
    if item.asked_for is not None:
        lines.append(_hang(f"Asked for: {item.asked_for}", indent, hang))
    else:
        lines.append(_hang("Asked for: nothing. The request did not state this "
                           "attribute.", indent, hang))
    if item.agent_said is not None:
        lines.append(_hang(f"The agent said the product is: {item.agent_said}",
                           indent, hang))
    for line in item.catalogue:
        lines.append(_hang(f"Catalogue: {line}", indent, hang))
    for note in item.notes:
        lines.append(_hang(note, indent, hang))
    lines.append(_hang(f"How much it counted: {item.weight_means}", indent, hang))
    lines.append(_hang(f"Coverage: {item.coverage_means}", indent, hang))
    return lines


def to_text(document: Document, *, public_key: str | None = None,
            record_file: str = "record.json") -> str:
    """The whole document as plain text, for a printout, a ticket or an email body."""
    record = document.record
    out: list[str] = ["=" * WIDTH, TITLE]

    line = record.order
    if line is not None:
        out.append(f"Order {line.order_id}  |  SKU {line.sku}  |  "
                   f"{lang.value(line.unit_price)} x {line.quantity}")
    out.append(f"Decided {record.timestamp.isoformat()}")
    out += ["=" * WIDTH, "", document.headline.upper(), ""]
    out.append(_wrap(document.summary, "  "))
    out.append("")
    out.append(_wrap(document.means, "  "))
    out.append("")
    out.append(_wrap(f"What it does not mean: {document.does_not_mean}", "  "))

    if document.alerts:
        out += ["", "READ THIS FIRST"]
        for alert in document.alerts:
            marker = "STOP" if alert.severity == STOP else "NOTE"
            out.append(_hang(f"{marker}  {alert.text}", "  ", " " * 8))

    out += ["", "-" * WIDTH, HEADINGS[0], "-" * WIDTH, "",
            "In the requester's own words, as the channel recorded them:"]
    if document.request_text_missing:
        out.append("  (nothing was recorded)")
    else:
        out.append(_wrap(f'"{document.request_text}"', "  "))

    out += ["", "As Approv read it:"]
    if document.requirements:
        for req in document.requirements:
            out += _requirement_lines(req)
    else:
        out.append(_wrap(NO_REQUIREMENTS, "  "))

    out += ["", f"WHAT APPROV FAILED TO READ ({len(document.unread)})"]
    if document.unread:
        out.append(_wrap(UNREAD_MEANS, "  "))
        out += [_hang(f"- {note}", "  ", "    ") for note in document.unread]
    else:
        out.append("  Nothing. Approv encoded every part of the request it could check.")

    out += ["", f"WHAT NOBODY ASKED FOR ({len(document.never_asked)})"]
    if document.never_asked:
        out.append(_wrap(NEVER_ASKED_MEANS, "  "))
        out.append(_wrap(", ".join(document.never_asked), "  "))
    else:
        out.append("  Nothing. The request spoke to every attribute this category has.")

    out += ["", "-" * WIDTH, HEADINGS[1], "-" * WIDTH, ""]
    for row in document.order:
        out += _row_lines(row)
    out.append("")
    for row in document.product:
        out += _row_lines(row)

    out += ["", "-" * WIDTH, HEADINGS[2], "-" * WIDTH, ""]
    if document.findings:
        for item in document.findings:
            out += _finding_lines(item)
            out.append("")
    else:
        out.append(_wrap(NO_FINDINGS, "  "))

    out += ["-" * WIDTH, HEADINGS[3], "-" * WIDTH, ""]
    for key in (lang.GUARANTEED, lang.REFUSED, lang.OUT_OF_COVERAGE, lang.UNRECORDED):
        names = document.coverage_buckets.get(key, ())
        if not names:
            continue
        out.append(f"  {lang.COVERAGE_LABEL[key]} ({len(names)}): {', '.join(names)}")
        out.append(_wrap(lang.COVERAGE_MEANS[key], "      "))
        out.append("")
    if not any(document.coverage_buckets.values()):
        out += ["  Nothing on this record carries a coverage class.", ""]
    out.append(_wrap(lang.COVERAGE_CAVEAT, "  "))

    out += ["", "-" * WIDTH, HEADINGS[4], "-" * WIDTH, ""]
    for row in document.integrity:
        out += _row_lines(row)
    out.append("")
    for index, step in enumerate(signature.steps(signed=document.signed), start=1):
        out.append(_hang(f"{index}. {step}", "  ", "     "))
    if document.signed:
        out += ["", "  Python, standard library plus one signature library, none of "
                    "Approv's code:", ""]
        out += ["    " + snippet_line for snippet_line
                in signature.snippet(public_key, record_file).splitlines()]
        if public_key is None:
            out += ["", _wrap("The public key is not printed on this copy. Ask Approv "
                              "for the published key that was current on the date "
                              "above.", "  ")]
        out += ["", _wrap(signature.CANNOT_PROVE, "  ")]

    out += ["", "-" * WIDTH, HEADINGS[5], "-" * WIDTH, ""]
    for paragraph in CLOSING:
        out += [_wrap(paragraph, "  "), ""]

    out += ["-" * WIDTH, DETAILS_HEADING, "-" * WIDTH, ""]
    for row in document.identity:
        out += _row_lines(row)
    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------------------

_CSS = """
:root { color-scheme: light; }
body { margin: 0; background: #f4f4f2; color: #14161a;
       font: 15px/1.55 ui-sans-serif, system-ui, "Segoe UI", Helvetica, Arial, sans-serif; }
main { max-width: 60rem; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
header.doc { background: #14161a; color: #fff; padding: 1.25rem 1rem; }
header.doc .inner { max-width: 60rem; margin: 0 auto; }
header.doc h1 { font-size: 1rem; letter-spacing: .09em; text-transform: uppercase;
                margin: 0 0 .4rem; font-weight: 600; }
header.doc p { margin: .15rem 0; font-size: .9rem; color: #d6d8dc; }
.verdict { border-left: 6px solid #6b7280; background: #fff; padding: 1rem 1.1rem;
           margin: 1.25rem 0; }
.verdict.allow { border-color: #1d7a4c; }
.verdict.confirm { border-color: #b06a00; }
.verdict.refuse { border-color: #a31515; }
.verdict h2 { margin: 0 0 .5rem; font-size: 1.25rem; }
.verdict p { margin: .4rem 0; }
.verdict .caveat { color: #4a4f57; }
.verdict .tally { font-weight: 600; }
ul.alerts { list-style: none; padding: 0; margin: 1rem 0; }
ul.alerts li { background: #fff; border-left: 6px solid #b06a00; padding: .6rem .9rem;
               margin: .4rem 0; }
ul.alerts li.stop { border-color: #a31515; }
ul.alerts li .tag { font-weight: 700; letter-spacing: .06em; margin-right: .5rem;
                    font-size: .78rem; }
section { background: #fff; border: 1px solid #dcdcd8; padding: 1rem 1.1rem;
          margin: 1rem 0; }
section > h2 { font-size: .82rem; letter-spacing: .1em; text-transform: uppercase;
               margin: 0 0 .9rem; color: #4a4f57; border-bottom: 1px solid #e6e6e2;
               padding-bottom: .5rem; }
h3 { font-size: .95rem; margin: 1.2rem 0 .4rem; }
blockquote { margin: .4rem 0 1rem; padding: .6rem .9rem; background: #f7f7f5;
             border-left: 3px solid #c9c9c3; }
dl.rows { display: grid; grid-template-columns: minmax(9rem, 16rem) 1fr; gap: .3rem .9rem;
          margin: 0; }
dl.rows dt { color: #4a4f57; }
dl.rows dd { margin: 0; word-break: break-word; }
dl.rows dd .note { display: block; color: #6b7280; font-size: .86rem; }
.missing { color: #a31515; font-style: italic; }
table { border-collapse: collapse; width: 100%; font-size: .92rem; }
th, td { text-align: left; padding: .5rem .6rem; border-bottom: 1px solid #e6e6e2;
         vertical-align: top; }
th { font-size: .76rem; letter-spacing: .07em; text-transform: uppercase; color: #4a4f57; }
tr.met td:first-child { border-left: 4px solid #1d7a4c; }
tr.notmet td:first-child { border-left: 4px solid #a31515; }
tr.unchecked td:first-child { border-left: 4px solid #b06a00; }
td.verdict-cell { font-weight: 700; white-space: nowrap; }
td.notmet { color: #a31515; }
tr.detail td { border-bottom: 2px solid #dcdcd8; color: #4a4f57; font-size: .88rem;
               padding-top: 0; }
tr.detail ul { margin: .2rem 0; padding-left: 1.1rem; }
.cov { display: inline-block; padding: .05rem .45rem; border-radius: 2px;
       font-size: .78rem; font-weight: 700; white-space: nowrap; }
.cov-guaranteed { background: #e3f1e9; color: #14532d; }
.cov-refused { background: #efeff1; color: #33363c; }
.cov-out_of_coverage, .cov-unrecorded { background: #fbe3e3; color: #7a1010; }
.bucket { border: 1px solid #dcdcd8; padding: .7rem .9rem; margin: .5rem 0; }
.bucket.out_of_coverage, .bucket.unrecorded { border-color: #a31515; background: #fff6f6; }
.bucket h3 { margin: 0 0 .3rem; }
.bucket p { margin: .2rem 0; color: #4a4f57; }
.caveat-box { border: 2px solid #14161a; padding: .8rem .9rem; margin-top: 1rem; }
ol.steps li { margin: .35rem 0; }
pre { background: #14161a; color: #f2f2ef; padding: .9rem; overflow-x: auto;
      font-size: .82rem; line-height: 1.45; }
footer { color: #4a4f57; font-size: .9rem; margin-top: 1.5rem; }
@media print { body { background: #fff; } section { break-inside: avoid; } }
"""


def _e(text) -> str:
    """Escape for element content: `&`, `<` and `>` only.

    Quotes are left alone deliberately. Every sentence on this page is English prose full
    of apostrophes — "the merchant's own published data" — and rendering those as `&#x27;`
    makes the source unreadable for a merchant's engineer reviewing what we send their
    returns desk. Attribute values go through `_attr`, which does escape quotes, and no
    record field is interpolated into an attribute anywhere in this module.
    """
    return html_escape.escape(str(text), quote=False)


def _attr(text) -> str:
    return html_escape.escape(str(text), quote=True)


def _rows_html(rows: tuple[Row, ...]) -> str:
    out = ['<dl class="rows">']
    for row in rows:
        value = ('<span class="missing">not recorded</span>' if row.missing
                 else _e(row.value))
        note = f'<span class="note">{_e(row.note)}</span>' if row.note else ""
        out.append(f"<dt>{_e(row.label)}</dt><dd>{value}{note}</dd>")
    out.append("</dl>")
    return "\n".join(out)


_ROW_CLASS = {Support.SATISFIED: "met", Support.VIOLATED: "notmet",
              Support.UNSTATED: "unchecked"}


def _findings_html(findings: tuple[AttributeFinding, ...]) -> str:
    if not findings:
        return f"<p>{_e(NO_FINDINGS)}</p>"
    out = ["<table>", "<thead><tr><th>Attribute</th><th>Asked for</th>"
           "<th>Catalogue</th><th>Result</th><th>Counted as</th><th>Coverage</th>"
           "</tr></thead>", "<tbody>"]
    for item in findings:
        css = _ROW_CLASS[item.support]
        asked = (_e(item.asked_for) if item.asked_for is not None
                 else '<span class="missing">not stated</span>')
        catalogue = "<br>".join(_e(line) for line in item.catalogue)
        if item.catalogue_missing:
            catalogue = f'<span class="missing">{catalogue}</span>'
        notes = list(item.notes) + [f"How much it counted: {item.weight_means}",
                                    f"Coverage: {item.coverage_means}"]
        if item.agent_said is not None:
            notes.insert(0, f"The agent said the product is: {item.agent_said}")
        out.append(
            f'<tr class="{css}"><td>{_e(item.attribute)}</td><td>{asked}</td>'
            f"<td>{catalogue}</td>"
            f'<td class="verdict-cell {css}">{_e(item.verdict)}</td>'
            f"<td>{_e(item.weight)}</td>"
            f'<td><span class="cov cov-{_attr(item.coverage)}">{_e(item.coverage_label)}'
            "</span></td></tr>")
        bullets = "".join(f"<li>{_e(note)}</li>" for note in notes)
        out.append(f'<tr class="detail"><td colspan="6"><ul>{bullets}</ul></td></tr>')
    out += ["</tbody>", "</table>"]
    return "\n".join(out)


def _coverage_html(document: Document) -> str:
    out = []
    for key in (lang.GUARANTEED, lang.REFUSED, lang.OUT_OF_COVERAGE, lang.UNRECORDED):
        names = document.coverage_buckets.get(key, ())
        if not names:
            continue
        out.append(
            f'<div class="bucket {_attr(key)}"><h3>{_e(lang.COVERAGE_LABEL[key])} '
            f"({len(names)}): {_e(', '.join(names))}</h3>"
            f"<p>{_e(lang.COVERAGE_MEANS[key])}</p></div>")
    if not out:
        out.append("<p>Nothing on this record carries a coverage class.</p>")
    out.append(f'<div class="caveat-box">{_e(lang.COVERAGE_CAVEAT)}</div>')
    return "\n".join(out)


def _request_html(document: Document) -> str:
    out = ["<h3>In the requester's own words, as the channel recorded them</h3>"]
    if document.request_text_missing:
        out.append('<p class="missing">Nothing was recorded.</p>')
    else:
        out.append(f"<blockquote>{_e(document.request_text)}</blockquote>")

    out.append("<h3>As Approv read it</h3>")
    if document.requirements:
        out.append('<dl class="rows">')
        for req in document.requirements:
            detail = req.provenance
            if req.source:
                detail += f" (field: {req.source})"
            quote = (f'Read from the words "{req.quote}". ' if req.quote else "")
            out.append(f"<dt>{_e(req.attribute)}</dt><dd>{_e(req.value)}"
                       f'<span class="note">{_e(quote + detail)}</span></dd>')
        out.append("</dl>")
    else:
        out.append(f'<p class="missing">{_e(NO_REQUIREMENTS)}</p>')

    out.append(f"<h3>What Approv failed to read ({len(document.unread)})</h3>")
    if document.unread:
        out.append(f"<p>{_e(UNREAD_MEANS)}</p><ul>")
        out += [f"<li>{_e(note)}</li>" for note in document.unread]
        out.append("</ul>")
    else:
        out.append("<p>Nothing. Approv encoded every part of the request it could "
                   "check.</p>")

    out.append(f"<h3>What nobody asked for ({len(document.never_asked)})</h3>")
    if document.never_asked:
        out.append(f"<p>{_e(NEVER_ASKED_MEANS)}</p>"
                   f"<p>{_e(', '.join(document.never_asked))}</p>")
    else:
        out.append("<p>Nothing. The request spoke to every attribute this category "
                   "has.</p>")
    return "\n".join(out)


def _signature_html(document: Document, public_key: str | None, record_file: str) -> str:
    out = [_rows_html(document.integrity), "<ol class=\"steps\">"]
    out += [f"<li>{_e(step)}</li>" for step in signature.steps(signed=document.signed)]
    out.append("</ol>")
    if document.signed:
        out.append("<p>Python, standard library plus one signature library, and none of "
                   "Approv's code:</p>")
        out.append(f"<pre>{_e(signature.snippet(public_key, record_file))}</pre>")
        if public_key is None:
            out.append('<p class="missing">The public key is not printed on this copy. '
                       "Ask Approv for the published key that was current on the date "
                       "above.</p>")
        out.append(f"<p>{_e(signature.CANNOT_PROVE)}</p>")
    return "\n".join(out)


def _embedded_json(document: Document) -> str:
    """The record itself, inside the page, so document and evidence travel together.

    `<` is escaped to its JSON unicode form: it appears only inside string values, the
    escape is still valid JSON, and it is what stops merchant catalogue text from closing
    the script element. Catalogue text is untrusted, first-party included (invariant 5).
    """
    payload = document.record.model_dump_json().replace("<", "\\u003c")
    return ('<script type="application/json" id="approv-record">'
            f"{payload}</script>")


def to_html(document: Document, *, public_key: str | None = None,
            record_file: str = "record.json") -> str:
    """One self-contained page: no scripts to run, no fonts to fetch, prints cleanly."""
    record = document.record
    line = record.order
    subtitle = [f"Decided {_e(record.timestamp.isoformat())}"]
    if line is not None:
        subtitle.insert(0, f"Order {_e(line.order_id)} &middot; SKU {_e(line.sku)} "
                           f"&middot; {_e(lang.value(line.unit_price))} "
                           f"&times; {line.quantity}")
    alerts = ""
    if document.alerts:
        items = "".join(
            f'<li class="{"stop" if a.severity == STOP else "warn"}">'
            f'<span class="tag">{"STOP" if a.severity == STOP else "NOTE"}</span>'
            f"{_e(a.text)}</li>" for a in document.alerts)
        alerts = f'<ul class="alerts">{items}</ul>'

    sections = [
        (HEADINGS[0], _request_html(document)),
        (HEADINGS[1], _rows_html(document.order) + _rows_html(document.product)),
        (HEADINGS[2], _findings_html(document.findings)),
        (HEADINGS[3], _coverage_html(document)),
        (HEADINGS[4], _signature_html(document, public_key, record_file)),
        (HEADINGS[5], "".join(f"<p>{_e(p)}</p>" for p in CLOSING)),
        (DETAILS_HEADING, _rows_html(document.identity)),
    ]
    body = "\n".join(
        f"<section><h2>{_e(heading)}</h2>{content}</section>"
        for heading, content in sections)

    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_e(TITLE)} — {_e(record.correlation_id)}</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n"
        f'<header class="doc"><div class="inner"><h1>{_e(TITLE)}</h1>'
        + "".join(f"<p>{part}</p>" for part in subtitle)
        + "</div></header>\n<main>\n"
        f'<div class="verdict {_attr(record.decision.value)}">'
        f"<h2>{_e(document.headline)}</h2>"
        f'<p class="tally">{_e(document.summary)}</p>'
        f"<p>{_e(document.means)}</p>"
        f'<p class="caveat"><strong>What it does not mean:</strong> '
        f"{_e(document.does_not_mean)}</p></div>\n"
        f"{alerts}\n{body}\n"
        f"<footer>Record {_e(record.correlation_id)}. Approv holds the stated request "
        "and the chosen product together; it does not hold the customer's own words."
        "</footer>\n"
        f"{_embedded_json(document)}\n</main>\n</body>\n</html>\n"
    )


# --------------------------------------------------------------------------------------
# The two calls a caller actually makes
# --------------------------------------------------------------------------------------


def render_text(record: ComparisonRecord, *, public_key: str | None = None,
                record_file: str = "record.json") -> str:
    return to_text(build(record), public_key=public_key, record_file=record_file)


def render_html(record: ComparisonRecord, *, public_key: str | None = None,
                record_file: str = "record.json") -> str:
    return to_html(build(record), public_key=public_key, record_file=record_file)
