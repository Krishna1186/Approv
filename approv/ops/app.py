"""ASGI deployment adapter around the existing framework-free verification surface.

Run with one Uvicorn worker. No endpoint lets a caller configure the comparison.
Only a committed, signed response is a successful verification.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
from threading import Lock
import time

from pydantic import ValidationError

from approv.config import load_deployment
from approv.config.settings import read_json
from approv.ops.extractor import Extractor
from approv.ops.telemetry import CURRENT, Metrics, Operation
from approv.receipts.backup import audit
from approv.receipts.chain import canonical_json
from approv.receipts.signers import SignerLoader
from approv.receipts.store import ReceiptStore, ReplayError
from approv.surface.verification import (
    ProductMismatch, UnknownCategory, VerificationRequest, verify_order,
)


class Runtime:
    def __init__(self, deployment, *, interpreter_factory=None, kms_client=None):
        self.deployment = deployment
        config, base = deployment.settings, deployment.base
        # No silent empty ledger, ephemeral key, missing extractor or automatic migration.
        config.api_token.read(base)
        config.extractor.credential.read(base)
        self.store = ReceiptStore(base / config.store, create=False, migrate=False)
        audit(self.store, deployment.public_keys)
        self.signers = SignerLoader(deployment, kms_client=kms_client)
        self.signers.load()
        self.metrics = Metrics(config.metrics_window)
        options = {"interpreter_factory": interpreter_factory} if interpreter_factory else {}
        self.extractor = Extractor(config.extractor, base, self.metrics, **options)
        self._ready_lock = Lock()
        self._ready_at = 0.0
        self._ready = None

    def ready(self):
        with self._ready_lock:
            if self._ready is not None and time.monotonic() - self._ready_at < self.deployment.settings.readiness_ttl_seconds:
                return self._ready
            operation = Operation(kind="readiness")
            token = CURRENT.set(operation)
            checks = {}
            try:
                checks_to_run = {
                    "store": self.store.probe_writable,
                    "key": self.signers.probe,
                    "catalogue_reader": lambda: [self.deployment.reader({}, s) for s in self.deployment.schemas.values()],
                    "extractor": lambda: [self.extractor("Readiness probe. No purchase requested.", s)
                                          for s in self.deployment.schemas.values()],
                }
                for name, check in checks_to_run.items():
                    try:
                        check()
                        checks[name] = "ok"
                    except Exception:
                        checks[name] = "unavailable"
                self._ready = {"status": "ready" if all(v == "ok" for v in checks.values()) else "not_ready",
                               "checks": checks, "deployment_hash": self.deployment.digest,
                               "checked_at_unix": time.time(),
                               "cache_seconds": self.deployment.settings.readiness_ttl_seconds}
                self._ready_at = time.monotonic()
                return self._ready
            finally:
                CURRENT.reset(token)

    def verify(self, body, operation):
        token = CURRENT.set(operation)
        status, outcome, replay = 503, "system_failure", False
        try:
            operation.stage = "request"
            request = VerificationRequest.model_validate(read_json(body))
            if request.merchant_id != self.deployment.settings.merchant_id:
                status, outcome = 403, "invalid_request"
                return status, {"error": "merchant_not_authorized"}
            request_hash = hashlib.sha256(canonical_json(
                request.model_dump(mode="json")).encode()).hexdigest()
            operation.stage = "store_lookup"
            prior = self.store.lookup_verification(request.correlation_id, request_hash)
            if prior is not None:
                replay = True
                status, outcome = 200, "success"
                return status, prior
            operation.stage = "comparison"
            started = time.perf_counter()
            def read_evidence(snapshot, schema):
                operation.stage = "catalogue"
                began = time.perf_counter()
                try:
                    evidence = self.deployment.reader(snapshot, schema)
                finally:
                    operation.timings["catalogue_seconds"] = time.perf_counter() - began
                operation.stage = "comparison"
                return evidence
            result = verify_order(request, schemas=self.deployment.schemas,
                                  read_evidence=read_evidence, extract=self.extractor,
                                  strict_unread=self.deployment.settings.floor_policy.strict_unread,
                                  returns=self.deployment.settings.floor_policy.returns)
            operation.timings["comparison_including_extraction_seconds"] = time.perf_counter() - started
            # The surface's placeholder surface-v1 is replaced with what actually ran.
            record = result.record.model_copy(update={
                "model_version": self.deployment.settings.extractor.model if operation.calls else "none-structured",
                "prompt_version": self.deployment.settings.extractor.prompt_version if operation.calls else "none"})
            response = result.model_copy(update={"record": record}).model_dump(mode="json")
            operation.stage = "signing_key"
            started = time.perf_counter()
            signer = self.signers.load()
            operation.timings["key_load_seconds"] = time.perf_counter() - started
            operation.stage = "sign_and_store"
            started = time.perf_counter()
            response = self.store.commit_verification(response, request_hash,
                                                      self.deployment.manifest, signer)
            operation.timings["sign_and_store_seconds"] = time.perf_counter() - started
            status, outcome = 200, "success"
            return status, response
        except ReplayError:
            status, outcome = 409, "replay_conflict"
            return status, {"error": "correlation_id_conflict"}
        except UnknownCategory:
            status, outcome = 404, "invalid_request"
            return status, {"error": "unknown_category"}
        except ProductMismatch:
            status, outcome = 422, "invalid_request"
            return status, {"error": "product_mismatch"}
        except (ValidationError, ValueError, UnicodeError):
            # Malformed request is 422; downstream storage/reader failures are 503.
            if operation.stage == "request":
                status, outcome = 422, "invalid_request"
                return status, {"error": "invalid_request"}
            return 503, {"error": "system_failure", "stage": operation.stage}
        except Exception:
            return 503, {"error": "system_failure", "stage": operation.stage}
        finally:
            self.metrics.finish(operation, outcome, status, replay=replay)
            CURRENT.reset(token)


class Application:
    def __init__(self, runtime):
        self.runtime = runtime
        self.inflight = 0
        self.ready_lock = asyncio.Lock()

    @staticmethod
    async def respond(send, status, payload, *, content_type=b"application/json", operation=None):
        body = payload.encode() if isinstance(payload, str) else canonical_json(payload).encode()
        headers = [(b"content-type", content_type), (b"content-length", str(len(body)).encode()),
                   (b"cache-control", b"no-store")]
        if operation:
            headers.append((b"x-approv-operation-id", operation.id.encode()))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        path, method = scope["path"], scope["method"]
        if method == "GET" and path in ("/livez", "/v1/health"):
            return await self.respond(send, 200, {"status": "alive"})
        if method == "GET" and path == "/v1/keys":
            return await self.respond(send, 200, {"format": "approv-public-keys-v1",
                                                  "keys": self.runtime.deployment.public_keys})
        headers = dict(scope.get("headers", []))
        try:
            config = self.runtime.deployment.settings
            expected = b"Bearer " + config.api_token.read(self.runtime.deployment.base)
        except Exception:
            return await self.respond(send, 503, {"error": "system_failure", "stage": "authentication"})
        if not hmac.compare_digest(headers.get(b"authorization", b""), expected):
            return await self.respond(send, 401, {"error": "unauthorized"})
        if method == "GET" and path == "/readyz":
            # A slow probe occupies one thread, not the whole verification executor.
            async with self.ready_lock:
                result = await asyncio.to_thread(self.runtime.ready)
            return await self.respond(send, 200 if result["status"] == "ready" else 503, result)
        if method == "GET" and path == "/ops/metrics":
            return await self.respond(send, 200, self.runtime.metrics.snapshot())
        if method == "GET" and path == "/metrics":
            return await self.respond(send, 200, self.runtime.metrics.prometheus(),
                                      content_type=b"text/plain; version=0.0.4; charset=utf-8")
        if path != "/v1/verify" or method != "POST":
            return await self.respond(send, 404, {"error": "not_found"})
        operation = Operation()
        if self.inflight >= config.max_inflight:
            self.runtime.metrics.finish(operation, "overloaded", 503)
            return await self.respond(send, 503, {"error": "system_failure", "stage": "capacity"}, operation=operation)
        if headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower() != b"application/json":
            self.runtime.metrics.finish(operation, "invalid_request", 415)
            return await self.respond(send, 415, {"error": "json_required"}, operation=operation)
        self.inflight += 1
        try:
            body = bytearray()
            while True:
                try:
                    message = await asyncio.wait_for(receive(), timeout=10)
                except TimeoutError:
                    self.runtime.metrics.finish(operation, "invalid_request", 408)
                    return await self.respond(send, 408, {"error": "request_timeout"}, operation=operation)
                if message["type"] == "http.disconnect":
                    self.runtime.metrics.finish(operation, "disconnected", 499)
                    return
                body.extend(message.get("body", b""))
                if len(body) > config.max_body_bytes:
                    self.runtime.metrics.finish(operation, "invalid_request", 413)
                    return await self.respond(send, 413, {"error": "request_too_large"}, operation=operation)
                if not message.get("more_body", False):
                    break
            # Do not cancel a writer on disconnect: a retry returns its committed result.
            status, response = await asyncio.to_thread(self.runtime.verify, bytes(body), operation)
            return await self.respond(send, status, response, operation=operation)
        finally:
            self.inflight -= 1


def create_app():
    return Application(Runtime(load_deployment()))
