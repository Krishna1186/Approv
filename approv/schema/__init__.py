"""Schema onboarding: derive a proposal, then record explicit human confirmation."""
from .derive import confirm_schema, propose_schema
from .models import (
    AttributeReport, ConfirmedSchema, SchemaProposal, Share, SourcePolicy,
    VerifiabilityReport,
)

__all__ = ["propose_schema", "confirm_schema", "SchemaProposal", "ConfirmedSchema",
           "VerifiabilityReport", "AttributeReport", "Share", "SourcePolicy"]
