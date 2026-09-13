"""Optional printable companion; install reportlab only when exporting PDFs.

Usage: python -m approv.schema.report_pdf report.json report.pdf
The HTML/JSON writer and default tests require no PDF dependency.
"""
from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

from .report import format_share


def write_pdf(report: dict, output: Path) -> None:
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

    fonts = Path(reportlab.__file__).parent / "fonts"
    pdfmetrics.registerFont(TTFont("ReportVera", str(fonts / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("ReportVeraBold", str(fonts / "VeraBd.ttf")))
    pdfmetrics.registerFontFamily("ReportVera", normal="ReportVera", bold="ReportVeraBold")
    ink, green, pale = colors.HexColor("#14332f"), colors.HexColor("#287361"), colors.HexColor("#e6eee8")
    body = ParagraphStyle("body", fontName="ReportVera", fontSize=10, leading=15, textColor=ink, spaceAfter=10)
    title = ParagraphStyle("title", parent=body, fontName="ReportVeraBold", fontSize=25, leading=31, spaceAfter=18)
    heading = ParagraphStyle("heading", parent=body, fontName="ReportVeraBold", fontSize=15, leading=21, spaceBefore=16, spaceAfter=10, keepWithNext=True)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=11, spaceAfter=6)
    cell = ParagraphStyle("cell", parent=small, fontSize=7.5, leading=10, spaceAfter=0)
    metric = ParagraphStyle("metric", parent=body, fontName="ReportVeraBold", fontSize=13, leading=20)
    e = lambda text: escape(str(text))
    p = lambda text, style=body: Paragraph(text, style)
    m, context = report["measurement"], report["context"]
    floor = ", ".join(m["floor"]) or "none found"
    story = [p("APPROV / CATALOGUE READINESS", small), p(e(context["merchant"]), title),
             p("What your catalogue lets us verify,<br/>and what to publish next.", heading), p(e(context["scope"])),
             p("<b>Proposal for review.</b> No schema has been adopted. A merchant reviewer must confirm the category, source mappings and required attributes before verification uses it."),
             p("Below the proposed minimum: " + e(floor), heading), p(e(format_share(m["cannot_verify"])), metric),
             p("Conditional on this suggested minimum; this is not a complete purchase check.", small),
             p("No structured comparison evidence", heading), p(e(format_share(m["no_comparable_attributes"])), metric),
             p("No exact merchant-attributed, non-advice attribute usable as a comparison anchor.", small),
             p(f"<b>Audit denominator:</b> {m['listings']:,} / {m['listings']:,} expanded listings from {m['input_records']:,} / {m['input_records']:,} supplied product records."),
             p("Missing or unusable product evidence prevents verification of a request that depends on that attribute. The affected traffic share is unmeasured: listing frequency is not request frequency."),
             p(f"Category / cohort: {e(m['category_id'])}<br/>Audit date: {e(m['observed_at'])}<br/>Model: {e(m['model_version'])}; prompt: {e(m['prompt_version'])}<br/>Intervals: Wilson 95%, descriptive catalogue counts, not accuracy.", small),
             PageBreak(), p("Publication by attribute", heading),
             p("Usable publication is a consistent typed reading from a structured source or labelled prose. Missing means no nonempty source. Present but unusable means a value exists but cannot support a consistent typed reading."),
             p("Every cell reports listings / all expanded listings, followed by its rate and Wilson 95% interval. This is the supplied snapshot, not an estimate of the live store.", small)]
    data = [[p("<b>Attribute / dimension</b>", cell), p("<b>Usable publication</b>", cell), p("<b>Missing</b>", cell), p("<b>Present but unusable</b>", cell)]]
    for row in report["attributes"]:
        cells = [p(e(row["attribute"]) + "<br/>" + e(row["dimension"] or "unresolved"), cell)]
        for key in ("published", "missing", "present_but_unusable"):
            share = format_share(row[key]).replace(" listings (", "<br/>(").replace("; Wilson 95% interval ", ";<br/>95% interval ")
            cells.append(p(share, cell))
        data.append(cells)
    table = Table(data, colWidths=[126, 114, 114, 114], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), pale), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), .4, colors.HexColor("#ccd9d4")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([table, Spacer(1, 12),
                  p("Minimum-eligible evidence additionally requires exact merchant attribution and excludes advice. The companion HTML and JSON include those counts and parsed-only counts for every attribute.", small),
                  PageBreak(), p("What to publish next", heading),
                  p("Start with facts customers request and the minimum your reviewer selects. The counts below describe catalogue gaps; they do not promise increases in covered traffic.")])
    actions = sorted((row for row in report["attributes"] if row["actions"] and row["action_scope"] == "publication_repair"),
                     key=lambda row: (row["attribute"] not in m["floor"], -row["present_but_unusable"]["numerator"],
                                      -row["not_verifiable_for_attribute"]["numerator"], row["attribute"]))
    if not actions:
        story.append(p("No publication repairs identified for the proposed minimum, observed selection axes, monetary fields or parsed-only facts. Review the remaining source mappings and category requirements; discovery cannot name fields never supplied."))
    for row in actions:
        story.extend([p(e(row["attribute"]), heading),
                      p("Cannot verify this attribute on " + e(format_share(row["not_verifiable_for_attribute"])), small)])
        story.extend(p(e(action)) for action in row["actions"])
        if row["parsed_only"]["numerator"]:
            story.append(p("Parsed-only publication: " + e(format_share(row["parsed_only"])), small))
        scenario = row["minimum_repair_scenario"]
        if scenario:
            story.append(p("<b>Conditional scenario:</b> " + e(scenario["assumption"]) + " Additional listings meeting the proposed minimum: "
                           + e(format_share(scenario["additional_listings_meeting_proposed_minimum"])) + ". Remaining below it: "
                           + e(format_share(scenario["remaining_below_proposed_minimum"])) + ". This is not an observed improvement.", small))
    story.extend([p("Other fields in the publication table may be incidental catalogue metadata. Review their relevance before asking the merchant to publish more data. The HTML and JSON preserve every field's diagnostics and conditional remediation, including source mapping ambiguities."),
                  PageBreak() if actions else Spacer(1, 6), p("Method and provenance", heading),
                  p("Suggested minimum: " + e(floor) + ". " + e(m["floor_basis"])),
                  p("Review separate category cohorts before treating this minimum as necessary or sufficient. When no minimum is found, every supplied listing remains below it; an empty catalogue has no rate."),
                  p("Counts are exact for the supplied snapshot. Wilson intervals follow the existing catalogue coverage report; they do not establish confidence about unsupplied products, future traffic or accuracy."),
                  p("Parent facts are inherited into variants. Empty or ambiguous variant collections remain unresolved denominator rows. Duplicate rows remain counted. Structured merchant attribution is an onboarding assumption requiring review, not a contractual liability finding."),
                  p("Methodology: DR 0015 catalogue coverage report and DR 0007 verification floor. Counts reuse the schema proposal and Wilson implementation in harness/coverage.py. No model, receipt or authorisation is produced."),
                  p(f"Category / cohort: {e(m['category_id'])}<br/>Source: {e(context['source'])}<br/>Captured: {e(context['captured_at'] or 'not recorded in source')}<br/>Audited: {e(m['observed_at'])}<br/>Derivation: {e(m['derivation_version'])}<br/>Model: {e(m['model_version'])}<br/>Prompt: {e(m['prompt_version'])}", small),
                  p("Source SHA-256: " + e(context["source_sha256"] or "not supplied") + "<br/>Catalogue payload SHA-256: " + e(report["catalogue_digest"]) + "<br/>Proposal ID: " + e(report["proposal_id"]), small),
                  p("Review notes:<br/>" + "<br/>".join(e(warning) for warning in m["warnings"]), small),
                  p("The companion HTML contains the full source locators, minimum-eligible shares and per-attribute diagnostics; JSON also preserves the machine-readable report and schema proposal.", small)])

    def footer(canvas, doc):
        canvas.setStrokeColor(green)
        canvas.line(54, 40, A4[0] - 54, 40)
        canvas.setFont("ReportVera", 7)
        canvas.setFillColor(ink)
        canvas.drawString(54, 27, "APPROV / Catalogue readiness / Proposal for review")
        canvas.drawRightString(A4[0] - 54, 27, f"Page {doc.page}")

    output.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(output), pagesize=A4, rightMargin=54, leftMargin=54, topMargin=48, bottomMargin=58,
                      title="Catalogue readiness | " + context["merchant"], author="Approv", invariant=1).build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_pdf(json.loads(args.report.read_text(encoding="utf-8")), args.output)
