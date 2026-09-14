import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import logging

import httpx
import pytest

from approv.config import load_deployment
from approv.config.settings import ConfigError
from approv.ops.app import Application, Runtime
from approv.ops.telemetry import Operation
from approv.receipts.chain import verify
from approv.receipts.keys import KeyStore
from approv.receipts.store import ReceiptStore


def call(runtime, method="GET", path="/livez", body=None, *, authorized=True, raw=None):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=Application(runtime)), base_url="http://test") as client:
            headers = {"Authorization": "Bearer secret-api-token"} if authorized else {}
            if raw is not None:
                headers["Content-Type"] = "application/json"
                return await client.request(method, path, content=raw, headers=headers)
            return await client.request(method, path, json=body, headers=headers)
    return asyncio.run(run())


def test_configuration_and_secrets_are_required_not_defaults(deployment, monkeypatch):
    path = deployment.base / "deployment.json"
    original = json.loads(path.read_text())
    for field in ("schemas", "catalogue_reader", "extractor", "signing", "public_keys", "store", "api_token", "floor_policy"):
        config = {k: v for k, v in original.items() if k != field}
        path.write_text(json.dumps(config))
        with pytest.raises(ConfigError):
            load_deployment(path)
    monkeypatch.delenv("APPROV_CONFIG", raising=False)
    with pytest.raises(ConfigError, match="APPROV_CONFIG"):
        load_deployment()
    path.write_text(json.dumps(original))
    (deployment.base / "extractor").unlink()
    with pytest.raises(ConfigError):
        Runtime(load_deployment(path))


@pytest.mark.parametrize("path,new_value", [
    (("extractor", "endpoint"), "http://example.com/v1"),
    (("extractor", "endpoint"), "https://user:secret@example.com"),
    (("floor_policy", "unread_policy"), "ignore"),
    (("extractor", "prices", "output_per_million_usd"), -1),
    (("signing", "backend"), "fallback"),
])
def test_invalid_deployment_fails_closed_without_echoing_values(deployment, path, new_value):
    file = deployment.base / "deployment.json"
    config = json.loads(file.read_text())
    target = config
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = new_value
    file.write_text(json.dumps(config))
    with pytest.raises(ConfigError) as error:
        load_deployment(file)
    assert "secret" not in str(error.value)


def test_pinned_schema_edits_and_duplicate_json_are_rejected(deployment):
    (deployment.base / "schema.json").write_text('{}')
    with pytest.raises(ConfigError, match="digest"):
        load_deployment(deployment.base / "deployment.json")
    (deployment.base / "deployment.json").write_text('{"format":"a","format":"b"}')
    with pytest.raises(ConfigError):
        load_deployment(deployment.base / "deployment.json")


def test_missing_store_is_not_replaced_with_an_empty_ledger(deployment):
    file = deployment.base / "receipts.sqlite3"
    file.unlink()
    with pytest.raises(ValueError, match="missing"):
        Runtime(deployment)
    assert not file.exists()


def test_sandbox_runtime_requires_its_own_store_and_ignores_no_namespace_override(runtime, body):
    sandbox_path = runtime.deployment.base / "sandbox.sqlite3"
    ReceiptStore(sandbox_path, namespace="sandbox")
    deployment = replace(runtime.deployment,
                         settings=runtime.deployment.settings.model_copy(update={"store": sandbox_path}))
    with pytest.raises(ValueError, match="namespace"):
        Runtime(deployment, interpreter_factory=runtime.extractor.interpreter_factory)
    sandbox = Runtime(deployment, namespace="sandbox", interpreter_factory=runtime.extractor.interpreter_factory)
    response = call(sandbox, "POST", "/v1/verify", body)
    assert response.status_code == 200
    original = response.json()
    assert original["record"]["store_namespace"] == "sandbox"
    verify(original["record"], deployment.public_keys)
    assert call(sandbox, "POST", "/v1/verify", body).json() == original
    assert call(sandbox, path="/readyz").json()["store_namespace"] == "sandbox"
    assert runtime.store.export()["records"] == []
    for field in ("namespace", "store_namespace", "sandbox"):
        assert call(runtime, "POST", "/v1/verify", {**body, field: "sandbox"}).status_code == 422
    assert runtime.store.export()["records"] == []


def test_authentication_and_deployment_values_are_not_caller_controlled(runtime, body):
    assert call(runtime, "POST", "/v1/verify", body, authorized=False).status_code == 401
    assert call(runtime, "POST", "/v1/verify", {**body, "merchant_id": "other"}).status_code == 403
    for field in ("schemas", "signing_key", "extract", "read_evidence", "unread_policy", "floor_policy"):
        assert call(runtime, "POST", "/v1/verify", {**body, field: {}}).status_code == 422
    assert runtime.store.export()["records"] == []


def test_live_and_ready_distinguish_real_dependencies_and_do_not_create_receipts(runtime, monkeypatch):
    assert call(runtime, path="/livez", authorized=False).status_code == 200
    ready = call(runtime, path="/readyz")
    assert ready.status_code == 200 and set(ready.json()["checks"].values()) == {"ok"}
    first_count = runtime.extractor.interpreter_factory.calls
    assert call(runtime, path="/readyz").status_code == 200
    assert runtime.extractor.interpreter_factory.calls == first_count
    for dependency, obj, method in (("extractor", runtime, "extractor"),
                                     ("key", runtime.signers, "probe"),
                                     ("store", runtime.store, "probe_writable")):
        with monkeypatch.context() as patch:
            patch.setattr(obj, method, lambda *a: (_ for _ in ()).throw(OSError("private details")))
            runtime._ready_at = 0
            response = call(runtime, path="/readyz")
            assert response.status_code == 503
            assert response.json()["checks"][dependency] == "unavailable"
            assert "private details" not in response.text
            assert call(runtime, path="/livez").status_code == 200
    assert runtime.store.export()["records"] == []
    snapshot = runtime.metrics.snapshot()
    assert snapshot["window_count"] == 0
    assert snapshot["counts"]["readiness_extractor_calls"] > 0


def test_response_is_committed_and_retry_survives_restart_and_rotation(runtime, body):
    response = call(runtime, "POST", "/v1/verify", body)
    assert response.status_code == 200
    original = response.json()
    assert runtime.store.export()["records"] == [original["record"]]
    verify(original["record"], runtime.deployment.public_keys)
    assert original["record"]["model_version"] == "none-structured"
    keys = KeyStore(runtime.deployment.base / "keys", password=b"secret-key-password")
    new_id = keys.rotate()
    public = runtime.deployment.base / "public-keys.json"
    keys.publish(public)
    path = runtime.deployment.base / "deployment.json"
    config = json.loads(path.read_text())
    config["signing"]["key_id"] = new_id
    config["public_keys"]["sha256"] = hashlib.sha256(public.read_bytes()).hexdigest()
    path.write_text(json.dumps(config))
    restarted = Runtime(load_deployment(path), interpreter_factory=runtime.extractor.interpreter_factory)
    assert call(restarted, "POST", "/v1/verify", body).json() == original
    after = call(restarted, "POST", "/v1/verify", {**body, "correlation_id": "correlation-2"})
    assert after.status_code == 200 and after.json()["record"]["key_id"] == new_id
    assert len(restarted.store.export()["records"]) == 2
    assert call(restarted, "POST", "/v1/verify", {**body, "product_snapshot": {"size": "L"}}).status_code == 409


def test_real_mismatch_is_a_successful_committed_comparison(runtime, body):
    body["product_snapshot"]["size"] = "L"
    response = call(runtime, "POST", "/v1/verify", body)
    assert response.status_code == 200 and response.json()["record"]["decision"] == "refuse"
    assert len(runtime.store.export()["records"]) == 1


def test_concurrent_http_retry_identity_has_one_receipt(runtime, body):
    def run(_):
        return runtime.verify(json.dumps(body).encode(), Operation())
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(run, range(4)))
    assert all(status == 200 for status, _ in responses)
    assert all(response == responses[0][1] for _, response in responses)
    assert len(runtime.store.export()["records"]) == 1


def test_provider_failure_is_a_retained_incomplete_record_and_usage_is_unknown(runtime, body, caplog):
    runtime.extractor.interpreter_factory.fail = True
    body["artifact"] = {"shape": "free_text", "text": "PRIVATE CUSTOMER REQUEST size M"}
    with caplog.at_level(logging.INFO, logger="approv.ops"):
        response = call(runtime, "POST", "/v1/verify", body)
    assert response.status_code == 200
    result = response.json()
    assert result["record"]["completion"] == "provider_unavailable"
    assert result["record"]["decision"] == "confirm" and not result["covered"]
    assert runtime.store.export()["records"] == [result["record"]]
    verify(result["record"], runtime.deployment.public_keys)
    assert "secret-extractor-key" not in result["record"]["completion_detail"]
    assert "PRIVATE CUSTOMER" not in caplog.text and "secret-extractor-key" not in caplog.text
    events = [json.loads(record.message) for record in caplog.records]
    assert events[-1]["estimated_usd"] is None and events[-1]["unknown_usage_calls"] == 1
    assert events[-1]["completion"] == "provider_unavailable"
    runtime.extractor.interpreter_factory.fail = False
    assert call(runtime, "POST", "/v1/verify", body).json() == result


def test_catalogue_failure_is_retained_without_leaking_exception_contents(runtime, body):
    def broken_reader(snapshot, schema):
        raise ValueError("reader credential SECRET and private snapshot")
    runtime.deployment = replace(runtime.deployment, reader=broken_reader)
    response = call(runtime, "POST", "/v1/verify", body)
    assert response.status_code == 200
    result = response.json()
    assert result["record"]["completion"] == "catalogue_unreadable"
    assert result["record"]["decision"] == "confirm" and not result["covered"]
    assert "SECRET" not in result["record"]["completion_detail"]
    verify(result["record"], runtime.deployment.public_keys)


def test_reader_with_wrong_return_type_is_not_ready(runtime, body):
    runtime.deployment = replace(runtime.deployment, reader=lambda *a: None)
    readiness = call(runtime, path="/readyz")
    assert readiness.status_code == 503
    assert readiness.json()["checks"]["catalogue_reader"] == "unavailable"
    result = call(runtime, "POST", "/v1/verify", body).json()
    assert result["record"]["completion"] == "catalogue_unreadable"
    assert result["record"]["decision"] == "confirm" and not result["covered"]


def test_configured_surface_budget_is_bound_and_cannot_authorize(runtime, body):
    path = runtime.deployment.base / "deployment.json"
    settings = json.loads(path.read_text())
    settings["comparison_budget_seconds"] = 0
    path.write_text(json.dumps(settings))
    runtime = Runtime(load_deployment(path), interpreter_factory=runtime.extractor.interpreter_factory)
    response = call(runtime, "POST", "/v1/verify", body)
    assert response.status_code == 200
    result = response.json()
    assert result["record"]["completion"] == "budget_exceeded"
    assert result["record"]["decision"] == "confirm" and not result["covered"]
    assert "guaranteed" not in result["record"]["coverage"]
    assert runtime.deployment.manifest["comparison_budget_seconds"] == 0
    verify(result["record"], runtime.deployment.public_keys)


def test_usage_cost_quantiles_and_prometheus_are_measured(runtime, body, caplog):
    body["artifact"] = {"shape": "free_text", "text": "size M"}
    with caplog.at_level(logging.INFO, logger="approv.ops"):
        response = call(runtime, "POST", "/v1/verify", body)
    assert response.status_code == 200
    record = response.json()["record"]
    assert record["model_version"] == "fixture-model" and record["prompt_version"] == "v6"
    event = next(json.loads(r.message) for r in caplog.records if json.loads(r.message)["event"] == "extraction")
    assert event["input_tokens"] == 20 and event["output_tokens"] == 10
    assert event["estimated_usd"] == pytest.approx((15 + 2.5 + 40) / 1_000_000)
    metrics = call(runtime, path="/ops/metrics").json()
    assert metrics["window_count"] == 1 and metrics["p95_seconds"] >= metrics["p50_seconds"] > 0
    assert metrics["counts"]["verification_extractor_calls"] == 1
    text = call(runtime, path="/metrics").text
    assert "approv_verification_seconds_count 1" in text
    assert 'approv_verification_seconds_bucket{le="+Inf"} 1' in text
    assert "PRIVATE" not in text and "merchant-1" not in text


def test_storage_failure_cannot_return_unsigned_success(runtime, body, monkeypatch):
    monkeypatch.setattr(runtime.store, "commit_verification", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    response = call(runtime, "POST", "/v1/verify", body)
    assert response.status_code == 503 and response.json()["stage"] == "sign_and_store"
    assert "record" not in response.json()
    assert runtime.store.export()["records"] == []


def test_disappearing_store_is_not_recreated_by_a_verification(runtime, body):
    runtime.store.path.unlink()
    assert call(runtime, "POST", "/v1/verify", body).status_code == 503
    assert not runtime.store.path.exists()


def test_duplicate_wire_keys_and_oversized_body_fail_closed(runtime, body):
    response = call(runtime, "POST", "/v1/verify", raw=b'{"merchant_id":"a","merchant_id":"b"}')
    assert response.status_code == 422
    response = call(runtime, "POST", "/v1/verify", raw=b"x" * 262145)
    assert response.status_code == 413
    assert runtime.store.export()["records"] == []


def test_deployment_manifest_and_response_are_bound_in_signed_checkpoint(runtime, body):
    response = call(runtime, "POST", "/v1/verify", body).json()
    bundle = runtime.store.export()
    context = bundle["checkpoint"]["context"]
    assert context["deployment_hash"] == runtime.deployment.digest
    assert runtime.deployment.digest in bundle["deployments"]
    assert context["response_hash"] == hashlib.sha256(
        bundle["submissions"][0]["response_body"].encode()).hexdigest()
    manifest_text = json.dumps(bundle["deployments"])
    assert "password" not in manifest_text and "credential" not in manifest_text
    verify(bundle["checkpoint"], runtime.deployment.public_keys)
