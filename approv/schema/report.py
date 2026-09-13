"""Partner-facing presentation of the existing onboarding counts (DR 0015 / 0007).

No new catalogue reader, coverage decision, traffic estimate or schema adoption.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from html import escape

from .models import AttributeReport, SchemaProposal, Share


@dataclass(frozen=True)
class ReportContext:
    merchant: str
    scope: str
    source: str
    captured_at: str | None = None
    source_sha256: str | None = None


_REPAIRS = {
    "currency_missing_or_ambiguous": "Publish an explicit ISO currency with each amount, or establish a trusted catalogue currency during onboarding.",
    "currency_conflict": "Reconcile contradictory currency declarations before comparing prices.",
    "invalid_money_amount": "Publish a nonnegative numeric amount and its currency in separate structured fields.",
    "unknown_or_ambiguous_unit": "Publish a supported, unambiguous unit with the value; distinguish US from imperial fluid ounces.",
    "unitless_decimal": "Publish the measurement unit or currency alongside the decimal value.",
    "ambiguous_quantity_expression": "Publish a single selected quantity and its unit in structured fields.",
    "multivalued_field_requires_mapping": "Identify the selected value separately from the list of possible values.",
    "unsupported_object": "Expose a scalar or an explicit amount/currency or value/unit object.",
    "prose_requires_labelled_extraction": "Move the product fact into a dedicated structured field.",
    "invalid_number": "Replace invalid or non-finite numbers with valid product values.",
    "invalid_typed_value": "Correct the value to match its declared type and unit.",
    "unsupported_value": "Expose the product fact in a supported structured value.",
    "no_unambiguous_dimension": "Review mixed types and units; split different meanings into distinct attributes.",
    "conflicting_values_excluded_from_publication": "Reconcile conflicting sources for the same listing and attribute.",
}


def _share(numerator: int, denominator: int) -> dict:
    return Share(numerator=numerator, denominator=denominator).model_dump(mode="json")


def format_share(share: dict) -> str:
    n, d = share["numerator"], share["denominator"]
    if not d:
        return f"{n:,} / {d:,} listings (rate unavailable; interval unavailable)"
    lo, hi = share["interval"]
    def percent(value, digits=1):
        # Keep small nonzero rates and narrow end-point intervals visible.
        precision = 4 if 0 < value < .001 or .999 < value < 1 else digits
        return f"{100 * value:.{precision}f}%"
    return (f"{n:,} / {d:,} listings ({percent(n / d)}; "
            f"Wilson 95% interval {percent(lo, 2)}-{percent(hi, 2)})")


def _actions(attribute: AttributeReport) -> list[str]:
    actions = []
    if attribute.occupied.numerator < attribute.occupied.denominator:
        actions.append("Publish this fact for each affected sellable SKU, including explicit variant selections where applicable.")
    if attribute.parsed_only.numerator:
        actions.append("Move the labelled fact from description text into a structured field; parsed prose cannot satisfy the minimum.")
    if attribute.dimension is None and "no_unambiguous_dimension" in attribute.issues:
        actions.append("Review the source mapping and mixed meanings before requesting new product data; no unambiguous attribute type was established.")
    elif attribute.occupied.numerator > attribute.published.numerator:
        # Diagnostics can survive a successful whole-label nominal interpretation.
        # Do not ask a merchant to turn a valid shoe-size label into a measurement.
        actions.extend(_REPAIRS[issue] for issue in attribute.issues if issue in _REPAIRS)
    if attribute.published.numerator > attribute.floor_eligible.numerator and not attribute.parsed_only.numerator:
        actions.append("Review source attribution, certainty and advice status; a populated value alone is not minimum-eligible evidence.")
    if attribute.occupied.numerator > attribute.published.numerator and not actions:
        actions.append("Review the excluded values and source diagnostics, then publish a consistent typed value.")
    return list(dict.fromkeys(actions))


def build_partner_report(proposal: SchemaProposal, context: ReportContext) -> dict:
    """Render a proposal honestly as a proposal, using its measured denominators.

    A repair scenario counts publication patterns; it never reruns discovery and
    never asserts that the proposed floor is the category's sufficient minimum.
    """
    if not isinstance(proposal, SchemaProposal):
        raise TypeError("partner report requires a SchemaProposal")
    measured = proposal.report
    total = measured.listings
    attributes = []
    for attribute in measured.attributes:
        row = attribute.model_dump(mode="json")
        row["missing"] = _share(total - attribute.occupied.numerator, total)
        row["present_but_unusable"] = _share(attribute.occupied.numerator - attribute.published.numerator, total)
        row["not_verifiable_for_attribute"] = _share(total - attribute.published.numerator, total)
        row["actions"] = _actions(attribute)
        row["action_scope"] = ("publication_repair" if attribute.attribute in measured.floor
                               or attribute.variant_groups.numerator or attribute.parsed_only.numerator
                               or attribute.dimension is not None and attribute.dimension.value == "money"
                               else "category_review")
        if row["actions"] and row["action_scope"] == "category_review":
            row["actions"].insert(0, "First confirm that this source describes a requested product fact; incidental catalogue metadata need not become a verification requirement.")
        row["minimum_repair_scenario"] = None
        if attribute.attribute in measured.floor:
            other_required = set(measured.floor) - {attribute.attribute}
            gain = sum(pattern.count for pattern in proposal.publication_patterns
                       if other_required <= set(pattern.attributes) and attribute.attribute not in pattern.attributes)
            row["minimum_repair_scenario"] = {
                "assumption": "If every gap for this attribute becomes consistent, exact merchant evidence; other attributes remain unchanged.",
                "additional_listings_meeting_proposed_minimum": _share(gain, total),
                "remaining_below_proposed_minimum": _share(measured.cannot_verify.numerator - gain, total),
            }
        attributes.append(row)
    return {
        "report_version": "catalogue-partner-report-v1",
        "status": "proposal_requires_human_review",
        "context": asdict(context),
        "measurement": measured.model_dump(mode="json", exclude={"attributes"}),
        "catalogue_digest": proposal.catalogue_digest,
        "proposal_id": proposal.proposal_id,
        "attributes": attributes,
    }


_CSS = """
:root { color-scheme: light; --ink:#14332f; --muted:#526762; --line:#ccd9d4; --paper:#fffdf7; }
* { box-sizing:border-box } body { margin:0; background:#e9eeea; color:var(--ink); font:16px/1.55 Georgia,serif }
main { max-width:1120px; margin:32px auto; padding:56px; background:var(--paper) }
.eyebrow, h2, h3, th, .label { font-family:Arial,sans-serif } .eyebrow { text-transform:uppercase; letter-spacing:.15em; font-size:12px }
h1 { font-size:42px; line-height:1.12; margin:18px 0 } h2 { font-size:23px; margin-top:40px } h3 { font-size:17px }
.deck { font-size:20px; max-width:850px } .muted, small { color:var(--muted) }
.notice { border-left:4px solid #bc7a27; padding:12px 18px; background:#f7efd9 }
.metrics { border-block:1px solid var(--line); margin:28px 0; padding:8px 0 }
.metric { padding:14px 0 } .metric + .metric { border-top:1px solid var(--line) }
.metric strong { display:block; font:600 22px/1.4 Arial,sans-serif }
.metric small { display:block } table { width:100%; border-collapse:collapse; table-layout:fixed; font:13px/1.45 Arial,sans-serif }
th,td { text-align:left; vertical-align:top; padding:12px 8px; border-bottom:1px solid var(--line); overflow-wrap:anywhere }
th { background:#e6eee8 } th:first-child { width:19% } .source { font:12px/1.5 monospace; overflow-wrap:anywhere }
.action { padding:14px 0; border-bottom:1px solid var(--line); break-inside:avoid }
.action h3 { margin:0 0 8px } ul { padding-left:22px } .metadata { font:13px/1.6 Arial,sans-serif; overflow-wrap:anywhere }
@media(max-width:720px) { main { margin:0; padding:24px 16px } h1 { font-size:32px } .table-scroll { overflow-x:auto } table { min-width:760px } }
@media print { @page { size:A4 landscape; margin:16mm } body { background:white } main { padding:0; margin:0; max-width:none } h1 { font-size:30px } h2,h3 { break-after:avoid } tr { break-inside:avoid } thead { display:table-header-group } .table-scroll { overflow:visible } }
"""


def render_html(report: dict) -> str:
    """Standalone, printable HTML; all catalogue and caller text is escaped."""
    m, context = report["measurement"], report["context"]
    e = lambda value: escape(str(value), quote=True)
    share = lambda value: e(format_share(value))
    floor = ", ".join(m["floor"]) or "none found"
    parts = [f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>Catalogue readiness | {e(context["merchant"])}</title><style>{_CSS}</style><main>',
             '<div class="eyebrow">Approv / Catalogue readiness</div>',
             f'<h1>{e(context["merchant"])}</h1><p class="deck">What your catalogue lets us verify, and what to publish next.</p>',
             f'<p>{e(context["scope"])}</p>',
             '<p class="notice"><strong>Proposal for review.</strong> This audit has not adopted a schema. '
             'A merchant reviewer must confirm the category, source mappings and required attributes before verification uses it.</p>',
             '<div class="metrics">',
             f'<div class="metric"><span class="label">Below the proposed minimum: {e(floor)}</span>'
             f'<strong>{share(m["cannot_verify"])}</strong><small>Conditional on this suggested minimum; it is not a complete purchase check.</small></div>',
             '<div class="metric"><span class="label">No structured comparison evidence</span>'
             f'<strong>{share(m["no_comparable_attributes"])}</strong><small>No exact, merchant-attributed, non-advice attribute usable as a comparison anchor.</small></div>',
             f'<div class="metric"><span class="label">Audit denominator</span><strong>{m["listings"]:,} / {m["listings"]:,} expanded listings examined</strong>'
             f'<small>From {m["input_records"]:,} / {m["input_records"]:,} supplied product records. {e(m["denominator_unit"])}. Duplicate rows remain counted.</small></div></div>',
             '<h2>What these findings mean</h2>',
             '<p>When a request depends on an attribute, missing or unusable product evidence prevents verification of that attribute. '
             'The share of traffic affected is unmeasured: listing frequency is not request frequency. '
             'This audit measures published evidence, not product truth, request interpretation accuracy, or financial coverage.</p>',
             f'<p><strong>Suggested minimum:</strong> {e(floor)}. {e(m["floor_basis"])} '
             'Review separate category cohorts before treating this minimum as necessary or sufficient. '
             'If no minimum is found, every listing remains below it; an empty catalogue has no rate.</p>',
             '<h2>Publication by attribute</h2>',
             '<p>Usable publication includes consistent typed readings from structured fields or labelled prose. '
             'Minimum-eligible evidence additionally requires an exact merchant source and excludes advice. '
             'Missing means no nonempty source; present but unusable means a source exists but cannot support a consistent typed reading.</p>',
             '<div class="table-scroll"><table><thead><tr><th>Attribute / dimension</th><th>Usable publication</th><th>Missing</th>'
             '<th>Present but unusable</th><th>Minimum-eligible</th></tr></thead><tbody>']
    for row in report["attributes"]:
        parts.append(f'<tr><td><strong>{e(row["attribute"])}</strong><br>{e(row["dimension"] or "unresolved")}</td>'
                     + ''.join(f'<td>{share(row[key])}</td>' for key in ("published", "missing", "present_but_unusable", "floor_eligible")) + '</tr>')
    parts.extend(['</tbody></table></div>', '<h2>What to publish next</h2>',
                  '<p>Start with attributes customers request and the minimum your reviewer selects. '
                  'The counts below identify affected listings, not promised increases in covered traffic.</p>'])
    actionable = sorted((row for row in report["attributes"] if row["actions"]),
                        key=lambda row: (row["action_scope"] != "publication_repair", row["attribute"] not in m["floor"],
                                         -row["present_but_unusable"]["numerator"], -row["not_verifiable_for_attribute"]["numerator"], row["attribute"]))
    if not actionable:
        parts.append('<p>No publication repairs identified in the observed fields. Review the proposed minimum and any category requirements absent from the entire export; discovery cannot name fields never supplied.</p>')
    for row in actionable:
        parts.extend([f'<section class="action"><h3>{e(row["attribute"])}</h3>',
                      '<p class="muted">' + ('Category relevance and source mapping require review.' if row["action_scope"] == "category_review" else 'Publication repair candidate; confirm relevance to customer requests.') + '</p>',
                      f'<p>Attribute cannot be verified on {share(row["not_verifiable_for_attribute"])}. '
                      f'Parsed-only publication: {share(row["parsed_only"])}.</p>',
                      '<ul>' + ''.join(f'<li>{e(action)}</li>' for action in row["actions"]) + '</ul>'])
        scenario = row["minimum_repair_scenario"]
        if scenario:
            parts.append(f'<p><strong>Conditional repair scenario:</strong> {e(scenario["assumption"])} '
                         f'Additional listings meeting the proposed minimum: {share(scenario["additional_listings_meeting_proposed_minimum"])}. '
                         f'Remaining below it: {share(scenario["remaining_below_proposed_minimum"])}. This is a scenario, not an observed improvement.</p>')
        parts.append('<p class="source">Observed source locators: ' + '<br>'.join(e(source["field_name"]) for source in row["sources"]) + '</p></section>')
    parts.extend(['<h2>Method and provenance</h2>', '<div class="metadata">',
                  f'<p>Category / cohort: {e(m["category_id"])}<br>Source: {e(context["source"])}<br>'
                  f'Catalogue captured: {e(context["captured_at"] or "not recorded in the source")}'
                  f'<br>Audit date: {e(m["observed_at"])}<br>Derivation: {e(m["derivation_version"])}'
                  f'<br>Model: {e(m["model_version"])}<br>Prompt: {e(m["prompt_version"])}<br>Interval method: {e(m["interval_method"])}</p>',
                  '<p>Counts are exact for the supplied snapshot. Wilson intervals accompany each rate for consistency with the existing catalogue coverage report; '
                  'they do not establish confidence about unsupplied products, live stock, future traffic or accuracy. '
                  'Parent facts are inherited into selected variants; ambiguous or empty variant collections remain unresolved denominator rows. '
                  'Structured merchant source attribution is an onboarding assumption requiring review, not a contractual liability finding.</p>',
                  '<p>Methodology: DR 0015 catalogue coverage report and DR 0007 verification floor. '
                  'Counts reuse the schema proposal and the Wilson implementation in harness/coverage.py. '
                  'No model, receipt or authorisation is produced by this report.</p>',
                  f'<p>Source SHA-256: {e(context["source_sha256"] or "not supplied")}<br>'
                  f'Catalogue payload SHA-256: {e(report["catalogue_digest"])}<br>Proposal ID: {e(report["proposal_id"])}</p>',
                  '<p>Review notes:</p><ul>' + ''.join(f'<li>{e(warning)}</li>' for warning in m["warnings"]) + '</ul>',
                  '</div></main></html>'])
    return '\n'.join(parts)
