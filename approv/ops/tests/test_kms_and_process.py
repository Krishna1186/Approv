import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from threading import Thread
import time
import urllib.error
import urllib.request

from cryptography.hazmat.primitives import serialization
import pytest

from approv.config import load_deployment
from approv.ops.app import Runtime
from approv.ops.telemetry import Operation, usage_cost
from approv.receipts.chain import generate_key, key_id_for, public_key_hex, verify
from approv.receipts.signers import KMSSigner
from test_store_operations import stranger


ARN = "arn:aws:kms:eu-west-1:123456789012:key/00000000-0000-0000-0000-000000000001"


class FakeKMS:
    """The AWS wire contract, backed by a real local Ed25519 key for offline proof."""
    def __init__(self):
        self.key = generate_key()
        self.calls = []
    def get_public_key(self, **kwargs):
        assert kwargs == {"KeyId": ARN}
        return {"KeyId": ARN, "KeyUsage": "SIGN_VERIFY", "KeySpec": "ECC_NIST_EDWARDS25519",
                "SigningAlgorithms": ["ED25519_SHA_512"],
                "PublicKey": self.key.public_key().public_bytes(
                    serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)}
    def sign(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["KeyId"] == ARN
        assert kwargs["MessageType"] == "RAW"
        assert kwargs["SigningAlgorithm"] == "ED25519_SHA_512"
        return {"KeyId": ARN, "SigningAlgorithm": "ED25519_SHA_512",
                "Signature": self.key.sign(kwargs["Message"])}


def test_kms_and_local_keys_share_the_standalone_verifier_after_rotation(runtime, body, tmp_path):
    assert runtime.verify(json.dumps(body).encode(), Operation())[0] == 200
    kms = FakeKMS()
    public = public_key_hex(kms.key)
    key_id = key_id_for(public)
    publication = {**runtime.deployment.public_keys, key_id: public}
    public_path = runtime.deployment.base / "public-keys.json"
    public_path.write_text(json.dumps({"format": "approv-public-keys-v1", "keys": publication}))
    path = runtime.deployment.base / "deployment.json"
    config = json.loads(path.read_text())
    config["signing"] = {"backend": "aws-kms", "region": "eu-west-1", "key_arn": ARN, "key_id": key_id}
    config["public_keys"]["sha256"] = hashlib.sha256(public_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(config))
    switched = Runtime(load_deployment(path), kms_client=kms, interpreter_factory=runtime.extractor.interpreter_factory)
    status, response = switched.verify(json.dumps({**body, "correlation_id": "kms-receipt"}).encode(), Operation())
    assert status == 200 and response["record"]["key_id"] == key_id
    assert len(kms.calls) == 2  # Receipt AND retained checkpoint, two network hops per new verification.
    assert all(len(call["Message"]) == 64 for call in kms.calls)
    verify(response["record"], publication)
    bundle = switched.store.export()
    stranger(tmp_path, bundle, publication, bundle["checkpoint"])


def test_kms_substitution_and_algorithm_drift_fail_closed():
    kms = FakeKMS()
    with pytest.raises(ValueError, match="published"):
        KMSSigner(kms, ARN, public_key_hex(generate_key()))
    signer = KMSSigner(kms, ARN, public_key_hex(kms.key))
    original = kms.sign
    def drift(**kwargs):
        return {**original(**kwargs), "SigningAlgorithm": "ED25519_PH_SHA_512"}
    kms.sign = drift
    with pytest.raises(ValueError, match="algorithm"):
        signer.sign(b"test")


def test_kms_sdk_model_accepts_the_documented_ed25519_contract():
    boto3 = pytest.importorskip("boto3")
    client = boto3.client("kms", region_name="eu-west-1", aws_access_key_id="fixture", aws_secret_access_key="fixture")
    shape = client.meta.service_model.operation_model("Sign").input_shape
    assert "ED25519_SHA_512" in shape.members["SigningAlgorithm"].enum


@pytest.mark.parametrize("usage", [{}, {"prompt_tokens": 2}, {"prompt_tokens": True, "completion_tokens": 2},
                                   {"prompt_tokens": 1, "completion_tokens": 1, "prompt_tokens_details": {"cached_tokens": 2}}])
def test_missing_or_invalid_usage_is_never_counted_as_free(deployment, usage):
    assert usage_cost(usage, deployment.settings.extractor.prices) is None


class Provider(BaseHTTPRequestHandler):
    fail = False
    malformed = False
    calls = 0
    credentials = []
    def log_message(self, *args):
        pass
    def do_POST(self):
        cls = type(self)
        cls.calls += 1
        cls.credentials.append(self.headers.get("Authorization"))
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if cls.fail:
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"secret-extractor-key private provider prose"}}')
            return
        text = json.loads(payload["messages"][1]["content"])["request"]
        requirements = [] if "Readiness" in text else [
            {"attribute": "size", "value": {"kind": "term", "surface": "M"}, "quote": "size M"}]
        content = "invalid JSON" if cls.malformed else json.dumps({"requirements": requirements, "unverified": []})
        response = {"model": "fixture-provider-model", "choices": [{"finish_reason": "stop", "message": {"content": content}}],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 10}}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())


@pytest.fixture
def provider(deployment):
    Provider.fail, Provider.malformed, Provider.calls, Provider.credentials = False, False, 0, []
    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config_path = deployment.base / "deployment.json"
    config = json.loads(config_path.read_text())
    config["extractor"]["endpoint"] = f"http://127.0.0.1:{server.server_port}/v1"
    config_path.write_text(json.dumps(config))
    try:
        yield load_deployment(config_path)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_interpreter_transport_and_malformed_provider_are_measured(provider, body):
    runtime = Runtime(provider)
    assert runtime.ready()["checks"]["extractor"] == "ok"
    body["artifact"] = {"shape": "free_text", "text": "size M"}
    status, result = runtime.verify(json.dumps(body).encode(), Operation())
    assert status == 200 and result["record"]["request_constraints"][0]["value"]["surface"] == "M"
    assert Provider.credentials == ["Bearer secret-extractor-key"] * 2
    Provider.malformed = True
    status, error = runtime.verify(json.dumps({**body, "correlation_id": "invalid-model-output"}).encode(), Operation())
    assert status == 200 and error["record"]["completion"] == "unreadable_response"
    assert error["record"]["decision"] == "confirm" and not error["covered"]
    verify(error["record"], runtime.deployment.public_keys)
    snapshot = runtime.metrics.snapshot()
    assert snapshot["tokens_and_estimates"]["verification_input"] == 100
    assert len(runtime.store.export()["records"]) == 2


def test_bootable_process_health_http_verification_and_cli_backup(provider, body, tmp_path):
    pytest.importorskip("uvicorn")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    root = Path(__file__).resolve().parents[3]
    config = provider.base / "deployment.json"
    output = tmp_path / "server.log"
    with output.open("w", encoding="utf-8") as log:
        # subprocess.Popen creates no interactive window. No external service is contacted.
        process = subprocess.Popen([sys.executable, "-m", "approv.ops", "serve", "--config", str(config),
                                    "--port", str(port)], cwd=root, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            base = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 15
            while True:
                try:
                    with urllib.request.urlopen(base + "/livez", timeout=.5) as response:
                        assert response.status == 200
                    break
                except (OSError, urllib.error.URLError):
                    if process.poll() is not None or time.monotonic() >= deadline:
                        pytest.fail("service failed to boot: " + output.read_text())
                    time.sleep(.05)
            def request(path, payload=None):
                return urllib.request.urlopen(urllib.request.Request(
                    base + path, data=json.dumps(payload).encode() if payload else None,
                    headers={"Authorization": "Bearer secret-api-token", "Content-Type": "application/json"}), timeout=10)
            with request("/readyz") as response:
                assert json.load(response)["status"] == "ready"
            body["artifact"] = {"shape": "free_text", "text": "size M"}
            with request("/v1/verify", body) as response:
                record = json.load(response)["record"]
                verify(record, provider.public_keys)
            with request("/ops/metrics") as response:
                assert json.load(response)["window_count"] == 1
            command = subprocess.run([sys.executable, "-m", "approv.ops", "backup", "--store", str(provider.base / "receipts.sqlite3"),
                                      "--keys", str(provider.base / "public-keys.json"), "--destination", str(tmp_path / "cli-backup")],
                                     cwd=root, capture_output=True, text=True, timeout=20)
            assert command.returncode == 0, command.stderr
        finally:
            process.terminate()
            process.wait(timeout=10)
    logs = output.read_text()
    assert '"event":"verification"' in logs and '"event":"extraction"' in logs
    assert "secret-extractor-key" not in logs and "secret-api-token" not in logs
