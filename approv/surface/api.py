"""The HTTP surface. The only module in the repo that imports a web framework.

§9: FastAPI at the surface layer only, the engine framework-free. `verification.py` holds
the whole request path and imports nothing from here, so this file is a router and a
dependency wiring diagram — if it grew logic, the boundary would have moved without
anybody deciding to move it.

FastAPI is an optional dependency (`pip install approv[api]`). Importing this module
without it fails with a sentence saying so rather than a traceback into site-packages,
because the engine and every test run perfectly well without a server.
"""

from __future__ import annotations

from typing import Mapping

from approv.surface.verification import (
    ModeMismatch, ProductMismatch, UnknownCategory, VerificationRequest,
    VerificationResult, evidence_from_snapshot, ingest_outcome, verify_order,
)
from approv.types.core import CategorySchema, Mode, OrderOutcome, UnreadPolicy

try:
    from fastapi import FastAPI, HTTPException
except ModuleNotFoundError as error:  # pragma: no cover - exercised by absence, not by test
    raise ModuleNotFoundError(
        "approv.surface.api needs FastAPI: pip install 'approv[api]'. The engine, the "
        "record and approv.surface.verification all work without it."
    ) from error

VERSION = "api-v1"


def create_app(
    schemas: Mapping[str, CategorySchema],
    *,
    read_evidence=evidence_from_snapshot,
    extract=None,
    unread_policy: UnreadPolicy = UnreadPolicy.WITHDRAW,
    returns: Mapping[str, float] | None = None,
    budget_seconds: float | None = None,
    mode: Mode = Mode.SHADOW,
    record_outcome=None,
    title: str = "Approv order verification",
):
    """One endpoint, and its configuration bound once rather than per request.

    Schemas, the catalogue reader, the extractor and the floor policy are deployment
    configuration, not request payload. Taking them here is what stops a caller supplying
    their own schema — which would let the party being defended define what counts as a
    match, and the record would be worth nothing.

    No signing key. The record this returns is **unsealed**: only the store knows the chain
    head, so the store signs. A deployment that wants a receipt appends what it gets back.
    """
    app = FastAPI(title=title, version=VERSION)

    @app.get("/v1/health")
    def health() -> dict:
        return {"status": "ok", "version": VERSION, "mode": mode.value,
                "categories": sorted(schemas),
                "outcomes": record_outcome is not None}

    @app.post("/v1/verify", response_model=VerificationResult)
    def verify(request: VerificationRequest) -> VerificationResult:
        """Verify one order line. Returns the record; never 4xx for a REFUSE.

        A refusal is a successful verification with an unwelcome answer, so it is a 200
        with `decision: refuse`. Returning an error status would invite a caller to treat
        it as a transport failure and retry until it went away.

        **A verification that did not complete is also a 200** (DR 0004), carrying
        `completion` and `completion_detail` and a `confirm` decision. A 5xx would hand the
        merchant nothing to keep, and their integration's most likely response to one is to
        ship anyway — which is failing open through the error handler rather than through
        the gate. The record is what makes the abort auditable instead of invisible.
        """
        try:
            return verify_order(request, schemas=schemas, read_evidence=read_evidence,
                                extract=extract, unread_policy=unread_policy,
                                returns=returns, budget_seconds=budget_seconds, mode=mode)
        except UnknownCategory as error:
            raise HTTPException(status_code=404,
                                detail="unknown category: %s" % error) from error
        except ProductMismatch as error:
            # The caller sent an internally inconsistent request, not a hard case. 422,
            # because answering it at all would produce a record that looks like evidence
            # and is about the wrong product.
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/v1/outcomes", response_model=OrderOutcome)
    def outcome(outcome: OrderOutcome) -> OrderOutcome:
        """Take one later fact about one verified order, joined by `correlation_id`.

        Nothing decides on it, here or downstream. The merchant's reason text is stored as
        they wrote it, and a deployment that has not been given somewhere to put outcomes
        says so rather than accepting and dropping them — an ingestion endpoint that
        silently discards is worse than none, because it reports success.
        """
        if record_outcome is None:
            raise HTTPException(status_code=501,
                                detail="this deployment has no outcome store configured")
        try:
            return ingest_outcome(outcome, record_outcome=record_outcome, mode=mode)
        except ModeMismatch as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return app
