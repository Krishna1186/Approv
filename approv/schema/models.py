"""Reviewable onboarding objects. A proposal is never deployment configuration."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from approv.harness.coverage import AttributeCoverage, wilson
from approv.types.core import CategorySchema, Certainty, Dimension, Liability


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Share(Frozen):
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_counts(self):
        if self.numerator > self.denominator:
            raise ValueError("numerator exceeds denominator")
        return self

    @computed_field
    @property
    def rate(self) -> float | None:
        # An empty catalogue supplies no rate, not perfect or zero coverage.
        return self.numerator / self.denominator if self.denominator else None

    @computed_field
    @property
    def interval(self) -> tuple[float, float]:
        return wilson(self.numerator, self.denominator)

    @classmethod
    def publication(cls, attribute: str, count: int, total: int):
        coverage = AttributeCoverage(attribute, count, total)
        return cls(numerator=coverage.published, denominator=coverage.total)


class SourcePolicy(Frozen):
    """Trusted onboarding configuration, never read from product records.

    These are the existing source-attribution labels, not a legal or insurance claim.
    Policies can reduce certainty; they cannot promote prose to EXACT.
    """
    liability: Liability = Liability.MERCHANT_GUARANTEED
    certainty: Certainty = Certainty.EXACT
    is_advice: bool = False


class SourceReport(Frozen):
    field_name: str
    liability: Liability
    certainty: Certainty
    is_variant_axis: bool
    occupied: Share
    published: Share


class AttributeReport(Frozen):
    attribute: str
    dimension: Dimension | None
    observed_dimensions: tuple[Dimension, ...]
    occupied: Share
    published: Share
    exact: Share
    floor_eligible: Share
    parsed_only: Share
    conflicted: Share
    variant_groups: Share
    variant_basis: tuple[str, ...] = ()
    sources: tuple[SourceReport, ...]
    issues: tuple[str, ...] = ()


class PublicationPattern(Frozen):
    """Aggregate sets, so a reviewed floor can be counted without retaining products."""
    attributes: tuple[str, ...]
    count: int = Field(ge=1)


class VerifiabilityReport(Frozen):
    category_id: str
    observed_at: datetime
    derivation_version: str
    model_version: Literal["none-deterministic"] = "none-deterministic"
    prompt_version: Literal["none"] = "none"
    input_records: int
    listings: int
    denominator_unit: Literal["expanded listings; one row for an unexpanded input record"] = "expanded listings; one row for an unexpanded input record"
    interval_method: Literal["Wilson 95%; descriptive catalogue counts, not accuracy"] = "Wilson 95%; descriptive catalogue counts, not accuracy"
    attributes: tuple[AttributeReport, ...]
    floor: tuple[str, ...]
    floor_basis: str
    no_comparable_attributes: Share
    cannot_verify: Share
    warnings: tuple[str, ...]


class SchemaProposal(Frozen):
    status: Literal["proposed"] = "proposed"
    proposed_schema: CategorySchema
    report: VerifiabilityReport
    publication_patterns: tuple[PublicationPattern, ...]
    catalogue_digest: str

    @computed_field
    @property
    def proposal_id(self) -> str:
        payload = self.model_dump(mode="json", exclude={"proposal_id"}, round_trip=True)
        # Pydantic serializes frozensets as lists; canonicalize before hashing.
        payload["proposed_schema"]["floor"] = sorted(self.proposed_schema.floor)
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class ConfirmedSchema(Frozen):
    status: Literal["confirmed"] = "confirmed"
    category_schema: CategorySchema
    report: VerifiabilityReport
    proposal_id: str
    reviewer: str = Field(min_length=1)
    confirmed_at: datetime
