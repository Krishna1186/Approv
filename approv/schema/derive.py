"""Catalogue -> proposal -> explicit human confirmation. No automatic adoption."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timezone

from approv.types.core import (
    AttributeSpec, CategorySchema, Certainty, Criticality, Dimension, FieldProfile,
    Liability, Term,
)

from .catalogue import Cell, discover
from .models import (
    AttributeReport, ConfirmedSchema, PublicationPattern, SchemaProposal, Share,
    SourcePolicy, SourceReport, VerifiabilityReport,
)
from .values import VERSION


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return value.astimezone(timezone.utc)


def _share(count: int, total: int) -> Share:
    return Share(numerator=count, denominator=total)


def _exact(cell: Cell) -> bool:
    return cell.certainty is Certainty.EXACT and not cell.is_advice and cell.liability is Liability.MERCHANT_GUARANTEED


def _dimension(cells: list[Cell], axis: bool):
    dimensions = {c.dimension for c in cells if c.dimension is not None}
    # Option labels may mix '9', 'XL', and 'Full/Queen'. Preserve the whole label;
    # never interpret the numeric subset as counts and discard the other sizes.
    if (axis or any(c.option for c in cells)) and (
        Dimension.NOMINAL in dimensions or dimensions <= {Dimension.COUNT}
    ):
        return Dimension.NOMINAL
    return next(iter(dimensions)) if len(dimensions) == 1 else None


def _usable(cell: Cell, dimension: Dimension | None) -> bool:
    if dimension is None:
        return False
    if dimension is Dimension.NOMINAL:
        # Full selector labels can remain labels, but an invalid price cannot.
        return cell.value is not None or (cell.option and cell.issue in {"unitless_decimal", "unknown_or_ambiguous_unit"})
    return cell.value is not None and cell.dimension is dimension


def _token(cell: Cell, dimension: Dimension) -> str:
    if dimension is Dimension.NOMINAL:
        return Term(surface=cell.raw).model_dump_json()
    return cell.value.model_dump_json()


def _floor_counts(patterns, floor):
    total = sum(p.count for p in patterns)
    no_values = sum(p.count for p in patterns if not p.attributes)
    missing = sum(p.count for p in patterns if not floor or not set(floor) <= set(p.attributes))
    return _share(no_values, total), _share(missing, total)


def propose_schema(records: list[dict], *, category_id: str,
                   observed_at: datetime | None = None, currency: str | None = None,
                   source_policies: dict[str, SourcePolicy] | None = None) -> SchemaProposal:
    """Derive from JSON product records without a merchant-specific Python adapter.

    Pass a category or catalogue cohort identifier, not a claimed universal category.
    `currency` and `source_policies` are trusted onboarding configuration. Missing
    currency is reported; '$' never defaults to USD. Metadata, identifiers, arrays of
    possible values and opaque prose are not comparison evidence.

    The floor is a *suggestion*: one most-published selection axis, or one most-published
    structured product attribute if no axis is proven. Catalogue frequency cannot prove
    semantic necessity. The reviewer must explicitly select the floor at confirmation.
    """
    if not isinstance(records, list):
        raise TypeError("catalogue must be a list of product records")
    if not isinstance(category_id, str) or not category_id.strip():
        raise ValueError("category_id must be nonempty")
    if currency is not None and (not isinstance(currency, str) or len(currency) != 3 or not currency.isascii() or not currency.isupper() or not currency.isalpha()):
        raise ValueError("currency must be an explicit three-letter uppercase code")
    policies = source_policies or {}
    if any(not isinstance(k, str) or not isinstance(v, SourcePolicy) for k, v in policies.items()):
        raise TypeError("source_policies maps exact source paths to SourcePolicy objects")
    observed_at = _aware(observed_at or datetime.now(timezone.utc))
    # Also validates serializability and rejects NaN rather than hashing non-JSON data.
    catalogue_digest = hashlib.sha256(json.dumps(records, sort_keys=True, ensure_ascii=False,
                                                allow_nan=False, separators=(",", ":")).encode()).hexdigest()
    listings, warnings = discover(records, currency=currency, policies=policies)
    total = len(listings)

    # Same leaf key in distinct nested roles (shipping.length and item.length) must
    # not be conflated. Dynamic option sources and labelled prose can support one
    # attribute; ordinary overlapping structured fields receive their full paths.
    collisions = set()
    for listing in listings:
        fields = defaultdict(set)
        for cell in listing.cells:
            if cell.certainty is Certainty.EXACT and not cell.option:
                fields[cell.name].add(cell.field)
        collisions.update(name for name, paths in fields.items() if len(paths) > 1)
    if collisions:
        warnings.add("overlapping_leaf_names_qualified_by_source_path")
        listings = [replace(row, cells=tuple(replace(c, name=c.field) if c.name in collisions else c for c in row.cells)) for row in listings]

    by_attribute = defaultdict(list)
    rows = defaultdict(lambda: defaultdict(list))
    by_group = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    group_ids = defaultdict(set)
    for index, listing in enumerate(listings):
        if listing.group and listing.identity:
            group_ids[listing.group].add(listing.identity)
        for cell in listing.cells:
            by_attribute[cell.name].append(cell)
            rows[cell.name][index].append(cell)
            if listing.group and listing.identity and _exact(cell) and cell.selectable:
                by_group[cell.name][listing.group][listing.identity].add(cell.raw)
    eligible_groups = {group for group, ids in group_ids.items() if len(ids) > 1}
    axis_groups = defaultdict(set)
    for attribute, groups in by_group.items():
        for group, identities in groups.items():
            # One SKU with contradictory values is not two stock choices.
            if group in eligible_groups and len(identities) > 1 and all(len(v) == 1 for v in identities.values()) and len(set.union(*identities.values())) > 1:
                axis_groups[attribute].add(group)

    profiles: dict[str, dict] = {}
    specs = []
    reports = []
    exact_by_listing = [set() for _ in listings]
    floor_candidates = []
    for attribute, cells in sorted(by_attribute.items()):
        if axis_groups[attribute]:
            cells = [replace(c, option=True) if c.selectable else c for c in cells]
            rows[attribute] = {index: [replace(c, option=True) if c.selectable else c for c in observed]
                               for index, observed in rows[attribute].items()}
        dimension = _dimension(cells, bool(axis_groups[attribute]))
        issues = {c.issue for c in cells if c.issue}
        if dimension is None:
            issues.add("no_unambiguous_dimension")
        dims = tuple(sorted({c.dimension for c in cells if c.dimension is not None}, key=lambda d: d.value))
        if dimension is Dimension.NOMINAL and any(d is not Dimension.NOMINAL for d in dims):
            issues.add("heterogeneous_selector_values_preserved_as_labels")
        published = exact = eligible = parsed_only = conflicts = 0
        source_rows = defaultdict(set)
        source_published = defaultdict(set)
        source_cells = defaultdict(list)
        for index, observed in rows[attribute].items():
            usable = [c for c in observed if _usable(c, dimension) and not c.is_advice]
            for cell in observed:
                source_rows[cell.field].add(index)
                source_cells[cell.field].append(cell)
                if _usable(cell, dimension):
                    source_published[cell.field].add(index)
            # Count listings once, and do not hide contradictory readings behind an
            # arbitrary first/last source preference.
            conflict = len({_token(c, dimension) for c in usable}) > 1
            conflicts += conflict
            if conflict:
                continue
            if usable:
                published += 1
                if any(c.certainty is Certainty.EXACT for c in usable):
                    exact += 1
                elif any(c.certainty is Certainty.PARSED for c in usable):
                    parsed_only += 1
                if any(_exact(c) for c in usable):
                    eligible += 1
                    exact_by_listing[index].add(attribute)
        if conflicts:
            issues.add("conflicting_values_excluded_from_publication")
        if dimension is not None:
            sources = tuple(sorted(source_rows))
            specs.append(AttributeSpec(name=attribute, dimension=dimension,
                                       criticality=Criticality.SOFT, feed_aliases=sources))
            for source, observed in source_cells.items():
                entry = profiles.setdefault(source, {"attributes": set(), "cells": [], "axis": False})
                entry["attributes"].add(attribute)
                entry["cells"].extend(observed)
                entry["axis"] |= bool(axis_groups[attribute]) and any(c.selectable and _exact(c) for c in observed)
            if eligible and any(c.selectable for c in cells):
                floor_candidates.append((bool(axis_groups[attribute]), eligible, attribute))
        reports.append(AttributeReport(
            attribute=attribute, dimension=dimension, observed_dimensions=dims,
            occupied=Share.publication(attribute, len(rows[attribute]), total),
            published=Share.publication(attribute, published, total), exact=_share(exact, total),
            floor_eligible=_share(eligible, total),
            parsed_only=_share(parsed_only, total), conflicted=_share(conflicts, total),
            variant_groups=_share(len(axis_groups[attribute]), len(eligible_groups)),
            sources=tuple(SourceReport(field_name=source, liability=observed[0].liability,
                                      certainty=max((c.certainty for c in observed), key=lambda c: {Certainty.EXACT: 0, Certainty.PARSED: 1, Certainty.INFERRED: 2}[c]),
                                      is_variant_axis=bool(axis_groups[attribute]) and any(c.selectable and _exact(c) for c in observed),
                                      occupied=_share(len(source_rows[source]), total),
                                      published=_share(len(source_published[source]), total))
                          for source, observed in sorted(source_cells.items())),
            issues=tuple(sorted(issues))))

    field_profiles = tuple(FieldProfile(field_name=source, attributes=tuple(sorted(entry["attributes"])),
                                        liability=entry["cells"][0].liability,
                                        certainty=max((c.certainty for c in entry["cells"]), key=lambda c: {Certainty.EXACT: 0, Certainty.PARSED: 1, Certainty.INFERRED: 2}[c]),
                                        is_variant_axis=entry["axis"], is_advice=any(c.is_advice for c in entry["cells"]))
                           for source, entry in sorted(profiles.items()))
    floor = frozenset()
    if floor_candidates:
        chosen = sorted(floor_candidates, key=lambda item: (-item[0], -item[1], item[2]))[0]
        floor = frozenset({chosen[2]})
    patterns = tuple(PublicationPattern(attributes=attrs, count=count)
                     for attrs, count in sorted(Counter(tuple(sorted(attrs)) for attrs in exact_by_listing).items()))
    no_values, cannot_verify = _floor_counts(patterns, floor)
    warnings.add("human_review_required: catalogue frequency cannot establish the category's necessary attributes")
    if not eligible_groups:
        warnings.add("no_distinct_sibling_identifiers: variant axes cannot be established")
    if not floor:
        warnings.add("no_structured_product_attribute_for_floor")
    if any(r.issues for r in reports):
        warnings.add("attribute_diagnostics_require_review")
    schema = CategorySchema(category_id=category_id, version=f"{VERSION}:{catalogue_digest[:16]}",
                            attributes=tuple(specs), field_profiles=field_profiles, floor=floor)
    report = VerifiabilityReport(category_id=category_id, observed_at=observed_at,
                                derivation_version=VERSION, input_records=len(records), listings=total,
                                attributes=tuple(reports), floor=tuple(sorted(floor)),
                                floor_basis="Most-published observed selection axis; otherwise most-published structured product attribute. Suggestion only; reviewer must select the floor.",
                                no_comparable_attributes=no_values, cannot_verify=cannot_verify,
                                warnings=tuple(sorted(warnings)))
    return SchemaProposal(proposed_schema=schema, report=report,
                          publication_patterns=patterns, catalogue_digest=catalogue_digest)


def confirm_schema(proposal: SchemaProposal, *, reviewer: str, expected_proposal_id: str,
                   floor: frozenset[str], confirmed_at: datetime | None = None) -> ConfirmedSchema:
    """Record human review of this exact proposal and the explicitly selected floor.

    Call only after the authenticated human reviews source policies, dimensions,
    diagnostics and the floor. Authentication and persistence belong to the hosting
    application. This function neither authenticates a person nor registers a schema.
    """
    if not isinstance(proposal, SchemaProposal):
        raise TypeError("confirmation requires a SchemaProposal")
    if expected_proposal_id != proposal.proposal_id:
        raise ValueError("proposal changed since review")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("a human reviewer identifier is required")
    if not isinstance(floor, frozenset) or not floor:
        raise ValueError("the reviewer must explicitly select a nonempty floor")
    candidates = {r.attribute for r in proposal.report.attributes if r.dimension is not None and r.floor_eligible.numerator}
    if not floor <= candidates:
        raise ValueError("floor must name attributes with comparable structured evidence")
    confirmed_at = _aware(confirmed_at or datetime.now(timezone.utc))
    if confirmed_at < proposal.report.observed_at:
        raise ValueError("confirmation cannot predate the catalogue observation")
    schema = proposal.proposed_schema.model_copy(update={"floor": floor})
    # A changed human-selected floor is a different schema version.
    schema_payload = schema.model_dump(mode="json")
    schema_payload["floor"] = sorted(floor)
    revision = hashlib.sha256(json.dumps(schema_payload, sort_keys=True).encode()).hexdigest()[:16]
    schema = schema.model_copy(update={"version": f"{VERSION}:confirmed:{revision}"})
    no_values, cannot_verify = _floor_counts(proposal.publication_patterns, floor)
    report = proposal.report.model_copy(update={"floor": tuple(sorted(floor)),
                                                "floor_basis": "Explicitly selected by the human reviewer.",
                                                "no_comparable_attributes": no_values,
                                                "cannot_verify": cannot_verify})
    return ConfirmedSchema(category_schema=schema, report=report, proposal_id=proposal.proposal_id,
                           reviewer=reviewer.strip(), confirmed_at=confirmed_at)
