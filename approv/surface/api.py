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
    ProductMismatch, UnknownCategory, VerificationRequest, VerificationResult,
    evidence_from_snapshot, verify_order,
)
from approv.types.core import CategorySchema, UnreadPolicy

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
    signing_key=None,
    unread_policy: UnreadPolicy = UnreadPolicy.WITHDRAW,
    returns: Mapping[str, float] | None = None,
    title: str = "Approv order verification",
):
    """One endpoint, and its configuration bound once rather than per request.

    Schemas, the catalogue reader, the extractor, the signing key and the floor policy are
    deployment configuration, not request payload. Taking them here is what stops a caller
    supplying their own schema — which would let the party being defended define what
    counts as a match, and the record would be worth nothing.
    """
    app = FastAPI(title=title, version=VERSION)

    @app.get("/v1/health")
    def health() -> dict:
        return {"status": "ok", "version": VERSION, "categories": sorted(schemas)}

    @app.post("/v1/verify", response_model=VerificationResult)
    def verify(request: VerificationRequest) -> VerificationResult:
        """Verify one order line. Returns the record; never 4xx for a REFUSE.

        A refusal is a successful verification with an unwelcome answer, so it is a 200
        with `decision: refuse`. Returning an error status would invite a caller to treat
        it as a transport failure and retry until it went away.
        """
        try:
            return verify_order(request, schemas=schemas, read_evidence=read_evidence,
                                extract=extract, signing_key=signing_key,
                                unread_policy=unread_policy, returns=returns)
        except UnknownCategory as error:
            raise HTTPException(status_code=404,
                                detail="unknown category: %s" % error) from error
        except ProductMismatch as error:
            # The caller sent an internally inconsistent request, not a hard case. 422,
            # because answering it at all would produce a record that looks like evidence
            # and is about the wrong product.
            raise HTTPException(status_code=422, detail=str(error)) from error

    return app
