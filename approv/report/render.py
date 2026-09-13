"""The report, as plain text and as a self-contained page.

The same two renderings as the dispute artifact, for the same reason: one to paste into
an email or a ticket, one to send. They print the same sections in the same order.

The layout helpers are a deliberate copy of the artifact's rather than an import of them.
The two documents have different widths, different audiences and different lifetimes, and
sharing the private helpers would mean a change to how a returns desk reads a refusal
silently reflows a partner's weekly numbers.

**No number reaches the page without its denominator.** `_measure` is the only function
that prints a rate, and it cannot print one without the population, the counts and the
interval, because `Measure` cannot hold one without the other.
"""

from __future__ import annotations

import html as html_escape
import textwrap

from approv.report import metrics as m
from approv.report.document import PopulationBlock, ReportDocument, Row, build
from approv.report.outcomes import OutcomeFeed
from approv.types.core import ComparisonRecord, Decision

VERSION = "report-render-v1"

WIDTH = 88
_LABEL = 46

TITLE = "APPROV SHADOW REPORT"

HEADINGS = (
    "1. THE HEADLINE: OF WHAT WE WOULD HAVE REFUSED, WHAT CAME BACK",
    "2. WHAT WAS OBSERVED",
    "3. WHAT APPROV WOULD HAVE DONE",
    "4. WHAT CAME BACK THAT WE HAD SAID SOMETHING ABOUT",
    "5. WHY IT CAME BACK",
    "6. HOW MUCH OF YOUR TRAFFIC CARRIES A STATED REQUEST",
    "7. THE PAYOUT PROXY",
    "8. THE DATA THIS WAS BUILT FROM",
    "9. WHAT THIS REPORT DOES NOT SAY",
)

HEADLINE_MEANS = (
    "Of the orders Approv would have refused, the share your customers sent back coded "
    "not-as-described or wrong-item. This is the number that decides whether the check "
    "is worth having: a refusal that nobody returns is a sale we would have cost you."
)

NEVER_POOLED = (
    "These populations are never combined into a single rate. Agent-stated traffic and "
    "on-site-search traffic carry different amounts of the customer's actual request, so "
    "one blended number would describe neither."
)

RECALL_MEANS = (
    "Of the wrong-item returns matched to a receipt, the share Approv had said something "
    "about. Reported twice because \"flagged\" is ambiguous: the strict number counts only "
    "refusals, the broad one also counts escalations, which in shadow mode nobody acted "
    "on."
)

ATTRIBUTION_MEANS = (
    "Every wrong-item return matched to a receipt, attributed from what the record "
    "actually shows. Where your desk coded which attribute the customer complained "
    "about, that coding decides it; where it did not, the record as a whole does, and "
    "that is the weaker instrument."
)

PAYOUT_MEANS = (
    "Orders carrying a finding Approv would have stood behind, that came back as the "
    "wrong item anyway. A proxy and not a payout: no coverage contract exists, every "
    "term of one is still open, and nothing here is a promise to pay. What it is: the "
    "count of orders where a guarantee, had one been in force, would have been tested."
)


def _wrap(text: str, indent: str = "", width: int = WIDTH) -> str:
    return textwrap.fill(text, width=width, initial_indent=indent,
                         subsequent_indent=indent) if text else ""


def _hang(text: str, first: str, rest: str) -> str:
    return textwrap.fill(text, width=WIDTH, initial_indent=first, subsequent_indent=rest)


def _pct(value: float) -> str:
    return "%.1f%%" % (100 * value)


def _row_lines(row: Row, indent: str = "  ") -> list[str]:
    value = "(not recorded)" if row.missing and not row.value else row.value
    label = row.label + " " + "." * max(2, _LABEL - len(row.label))
    head = f"{indent}{label} {value}"
    lines = [head] if len(head) <= WIDTH or " " not in value.strip() else [
        f"{indent}{label}", _wrap(value, indent + "    ")]
    if row.note:
        lines.append(_wrap(row.note, indent + "    "))
    return lines


def _measure_lines(measure: m.Measure, indent: str = "    ") -> list[str]:
    """One number, or one honest account of why there is not one.

    The only place a rate is rendered. It prints the counts, the rate, the interval and
    the denominator in words every time, because invariant 6 is not satisfied by a
    percentage with a footnote somewhere else on the page.
    """
    tag = "  [FIXTURE]" if measure.fixture else ""
    if measure.unavailable is not None:
        return [_hang("%s: NOT COMPUTED%s" % (measure.name, tag), indent, indent + "  "),
                _wrap("Why: " + measure.unavailable, indent + "  ")]
    if measure.denominator == 0:
        return [_hang("%s: no orders in this population%s" % (measure.name, tag),
                      indent, indent + "  "),
                _wrap("Of: " + measure.denominator_note, indent + "  ")]
    low, high = measure.interval
    lines = [_hang("%s%s" % (measure.name, tag), indent, indent + "  "),
             "%s  %d of %d   %s   95%% CI [%s, %s]"
             % (indent + "  ", measure.numerator, measure.denominator,
                _pct(measure.rate), _pct(low), _pct(high))]
    lines.append(_wrap("Of: " + measure.denominator_note, indent + "  "))
    if measure.thin:
        lines.append(_wrap(
            "Fewer than %d observations. Read the interval, not the rate: this is a "
            "description of a handful of orders, not a measurement." % m.THIN,
            indent + "  "))
    return lines


def _attribution_lines(block: PopulationBlock, indent: str = "    ") -> list[str]:
    table = block.attribution
    tag = "  [FIXTURE]" if table.fixture else ""
    if table.blocked:
        return [_hang("NOT COMPUTED%s" % tag, indent, indent + "  "),
                _wrap("Why: " + table.blocked, indent + "  ")]
    if not table.total:
        return [indent + "No wrong-item returns matched a receipt in this population."
                + tag]
    lines = ["%s%d wrong-item return(s), %d attributed from your desk's own attribute "
             "coding%s" % (indent, table.total, table.coded, tag)]
    for member, count in table.counts.items():
        if not count:
            continue
        lines.append("%s  %d of %d  %s" % (indent, count, table.total,
                                           member.value.replace("_", " ")))
        lines.append(_wrap(m.ATTRIBUTION_MEANS[member], indent + "    "))
    return lines


def to_text(document: ReportDocument) -> str:
    out: list[str] = ["=" * WIDTH, TITLE,
                      "%s  |  %s" % (document.partner, document.period),
                      "Generated %s" % document.generated_at.isoformat(), "=" * WIDTH, ""]
    out += ["SHADOW MODE", _wrap(document.shadow_note, "  "), ""]
    if document.feed_note:
        out += ["!" * WIDTH, _wrap(document.feed_note, "  "), "!" * WIDTH, ""]

    out += ["-" * WIDTH, HEADINGS[0], "-" * WIDTH, "", _wrap(HEADLINE_MEANS, "  "), ""]
    for block in document.populations:
        out.append("  %s (%d observed)" % (block.label, block.observed))
        out += _measure_lines(block.precision)
        out += _measure_lines(block.open_window)
        out.append("")
    out.append(_wrap(NEVER_POOLED, "  "))

    out += ["", "-" * WIDTH, HEADINGS[1], "-" * WIDTH, ""]
    for row in document.volume:
        out += _row_lines(row)

    out += ["", "-" * WIDTH, HEADINGS[2], "-" * WIDTH, ""]
    for block in document.populations:
        out.append("  %s" % block.label)
        for decision in (Decision.REFUSE, Decision.CONFIRM, Decision.ALLOW):
            out += _measure_lines(block.decisions[decision])
        out += _measure_lines(block.aborted)
        out += _measure_lines(block.coverage_eligible)
        out.append("")

    out += ["-" * WIDTH, HEADINGS[3], "-" * WIDTH, "", _wrap(RECALL_MEANS, "  "), ""]
    for block in document.populations:
        out.append("  %s" % block.label)
        out += _measure_lines(block.recall_strict)
        out += _measure_lines(block.recall_flagged)
        out.append("")

    out += ["-" * WIDTH, HEADINGS[4], "-" * WIDTH, "",
            _wrap(ATTRIBUTION_MEANS, "  "), ""]
    for block in document.populations:
        out.append("  %s" % block.label)
        out += _attribution_lines(block)
        out.append("")

    out += ["-" * WIDTH, HEADINGS[5], "-" * WIDTH, ""]
    out += _measure_lines(document.provenance, "  ")

    out += ["", "-" * WIDTH, HEADINGS[6], "-" * WIDTH, "", _wrap(PAYOUT_MEANS, "  "), ""]
    for block in document.populations:
        out.append("  %s" % block.label)
        out += _measure_lines(block.payout_proxy)
        out.append("")

    out += ["-" * WIDTH, HEADINGS[7], "-" * WIDTH, ""]
    for row in document.sources:
        out += _row_lines(row)
    out.append("")
    for row in document.join_quality:
        out += _row_lines(row)

    out += ["", "-" * WIDTH, HEADINGS[8], "-" * WIDTH, ""]
    for caveat in document.caveats:
        out.append(_hang("- " + caveat, "  ", "    "))
        out.append("")
    page = "\n".join(out).rstrip() + "\n"
    return "\n".join(line.rstrip() for line in page.split("\n"))


# --------------------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------------------

_CSS = """
:root { color-scheme: light; }
body { margin: 0; background: #f4f4f2; color: #14161a;
       font: 15px/1.55 ui-sans-serif, system-ui, "Segoe UI", Helvetica, Arial, sans-serif; }
main { max-width: 62rem; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
header.doc { background: #14161a; color: #fff; padding: 1.25rem 1rem; }
header.doc .inner { max-width: 62rem; margin: 0 auto; }
header.doc h1 { font-size: 1rem; letter-spacing: .09em; text-transform: uppercase;
                margin: 0 0 .4rem; font-weight: 600; }
header.doc p { margin: .15rem 0; font-size: .9rem; color: #d6d8dc; }
.shadow { border-left: 6px solid #14161a; background: #fff; padding: 1rem 1.1rem;
          margin: 1.25rem 0; }
.fixture { border: 2px solid #a31515; background: #fff6f6; padding: .9rem 1.1rem;
           margin: 1.25rem 0; color: #7a1010; font-weight: 600; }
section { background: #fff; border: 1px solid #dcdcd8; padding: 1rem 1.1rem;
          margin: 1rem 0; }
section > h2 { font-size: .82rem; letter-spacing: .1em; text-transform: uppercase;
               margin: 0 0 .9rem; color: #4a4f57; border-bottom: 1px solid #e6e6e2;
               padding-bottom: .5rem; }
h3 { font-size: .95rem; margin: 1.1rem 0 .4rem; }
p.means { color: #4a4f57; margin: .2rem 0 1rem; }
.measure { border-left: 4px solid #c9c9c3; padding: .5rem .8rem; margin: .6rem 0;
           background: #fafaf8; }
.measure.nocompute { border-color: #a31515; }
.measure .name { font-weight: 600; }
.measure .figure { font-size: 1.35rem; margin: .2rem 0; }
.measure .figure .counts { font-size: .95rem; color: #4a4f57; }
.measure .of { color: #4a4f57; font-size: .88rem; }
.measure .thin { color: #7a1010; font-size: .88rem; }
.tag { display: inline-block; background: #fbe3e3; color: #7a1010; font-size: .7rem;
       font-weight: 700; letter-spacing: .06em; padding: .05rem .4rem; margin-left: .4rem;
       vertical-align: middle; }
dl.rows { display: grid; grid-template-columns: minmax(10rem, 22rem) 1fr; gap: .3rem .9rem;
          margin: 0; }
dl.rows dt { color: #4a4f57; }
dl.rows dd { margin: 0; word-break: break-word; }
dl.rows dd .note { display: block; color: #6b7280; font-size: .86rem; }
.missing { color: #a31515; font-style: italic; }
ul.attr { list-style: none; padding: 0; margin: .4rem 0; }
ul.attr li { margin: .5rem 0; }
ul.attr .count { font-weight: 700; }
ul.attr .means { color: #4a4f57; font-size: .9rem; display: block; }
footer ul { color: #4a4f57; font-size: .92rem; }
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
        note = f'<span class="note">{_e(row.note)}</span>' if row.note else ""
        out.append(f"<dt>{_e(row.label)}</dt><dd>{value}{note}</dd>")
    out.append("</dl>")
    return "\n".join(out)


def _measure_html(measure: m.Measure) -> str:
    tag = '<span class="tag">FIXTURE</span>' if measure.fixture else ""
    if measure.unavailable is not None:
        return (f'<div class="measure nocompute"><span class="name">{_e(measure.name)}'
                f'</span>{tag}<div class="figure">NOT COMPUTED</div>'
                f'<span class="of">Why: {_e(measure.unavailable)}</span></div>')
    if measure.denominator == 0:
        return (f'<div class="measure"><span class="name">{_e(measure.name)}</span>{tag}'
                f'<div class="figure">no orders in this population</div>'
                f'<span class="of">Of: {_e(measure.denominator_note)}</span></div>')
    low, high = measure.interval
    thin = ('<span class="thin">Fewer than %d observations. Read the interval, not the '
            "rate.</span>" % m.THIN) if measure.thin else ""
    return (f'<div class="measure"><span class="name">{_e(measure.name)}</span>{tag}'
            f'<div class="figure">{_e(_pct(measure.rate))} '
            f'<span class="counts">{measure.numerator} of {measure.denominator}, '
            f"95% CI [{_e(_pct(low))}, {_e(_pct(high))}]</span></div>"
            f'<span class="of">Of: {_e(measure.denominator_note)}</span>{thin}</div>')


def _attribution_html(block: PopulationBlock) -> str:
    table = block.attribution
    tag = '<span class="tag">FIXTURE</span>' if table.fixture else ""
    if table.blocked:
        return ('<div class="measure nocompute"><div class="figure">NOT COMPUTED</div>'
                '<span class="of">Why: %s</span>%s</div>' % (_e(table.blocked), tag))
    if not table.total:
        return ("<p>No wrong-item returns matched a receipt in this population.%s</p>"
                % tag)
    items = []
    for member, count in table.counts.items():
        if not count:
            continue
        items.append(f'<li><span class="count">{count} of {table.total}</span> '
                     f'{_e(member.value.replace("_", " "))}'
                     f'<span class="means">{_e(m.ATTRIBUTION_MEANS[member])}</span></li>')
    return ("<p>%d wrong-item return(s), %d attributed from your desk's own attribute "
            "coding.%s</p><ul class=\"attr\">%s</ul>"
            % (table.total, table.coded, tag, "".join(items)))


def to_html(document: ReportDocument) -> str:
    blocks = document.populations

    def per_population(render) -> str:
        return "".join("<h3>%s</h3>%s" % (_e(b.label), render(b)) for b in blocks)

    sections = [
        (HEADINGS[0],
         f'<p class="means">{_e(HEADLINE_MEANS)}</p>'
         + per_population(lambda b: _measure_html(b.precision)
                          + _measure_html(b.open_window))
         + f'<p class="means">{_e(NEVER_POOLED)}</p>'),
        (HEADINGS[1], _rows_html(document.volume)),
        (HEADINGS[2], per_population(
            lambda b: "".join(_measure_html(b.decisions[d]) for d in
                              (Decision.REFUSE, Decision.CONFIRM, Decision.ALLOW))
            + _measure_html(b.aborted) + _measure_html(b.coverage_eligible))),
        (HEADINGS[3], f'<p class="means">{_e(RECALL_MEANS)}</p>'
         + per_population(lambda b: _measure_html(b.recall_strict)
                          + _measure_html(b.recall_flagged))),
        (HEADINGS[4], f'<p class="means">{_e(ATTRIBUTION_MEANS)}</p>'
         + per_population(_attribution_html)),
        (HEADINGS[5], _measure_html(document.provenance)),
        (HEADINGS[6], f'<p class="means">{_e(PAYOUT_MEANS)}</p>'
         + per_population(lambda b: _measure_html(b.payout_proxy))),
        (HEADINGS[7], _rows_html(document.sources) + _rows_html(document.join_quality)),
        (HEADINGS[8], "<ul>" + "".join("<li>%s</li>" % _e(c)
                                       for c in document.caveats) + "</ul>"),
    ]
    body = "\n".join("<section><h2>%s</h2>%s</section>" % (_e(heading), content)
                     for heading, content in sections)
    warning = (f'<div class="fixture">{_e(document.feed_note)}</div>'
               if document.feed_note else "")
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_e(TITLE)} - {_e(document.partner)}</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n"
        f'<header class="doc"><div class="inner"><h1>{_e(TITLE)}</h1>'
        f"<p>{_e(document.partner)} &middot; {_e(document.period)}</p>"
        f"<p>Generated {_e(document.generated_at.isoformat())}</p>"
        "</div></header>\n<main>\n"
        f'<div class="shadow">{_e(document.shadow_note)}</div>\n{warning}\n{body}\n'
        "</main>\n</body>\n</html>\n")


def render_text(records: list[ComparisonRecord], feed: OutcomeFeed | None = None,
                **kw) -> str:
    return to_text(build(records, feed, **kw))


def render_html(records: list[ComparisonRecord], feed: OutcomeFeed | None = None,
                **kw) -> str:
    return to_html(build(records, feed, **kw))
