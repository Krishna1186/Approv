import hashlib
import json
from pathlib import Path

import pytest

from approv.config import load_deployment
from approv.receipts.keys import KeyStore
from approv.receipts.store import ReceiptStore
from approv.types.core import AttributeSpec, CategorySchema, Dimension, FieldProfile, Criticality, Certainty, Liability


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class Interpreter:
    calls = 0
    fail = False

    def __init__(self, endpoint, model, key, version):
        pass

    def __call__(self, case, schema):
        type(self).calls += 1
        if type(self).fail:
            raise TimeoutError("secret-extractor-key PRIVATE CUSTOMER REQUEST")
        from approv.types.core import Constraint, Term, Channel
        constraints = () if "Readiness" in case.request else (
            Constraint(attribute="size", value=Term(surface="M"), raw_text="size M", channel=Channel.AGENT_MESSAGE),)
        return case.model_copy(update={"constraints": constraints}), {
            "status": "parsed", "usage": {"prompt_tokens": 20, "completion_tokens": 10,
                                           "prompt_tokens_details": {"cached_tokens": 5}}}


@pytest.fixture
def deployment(tmp_path):
    Interpreter.calls, Interpreter.fail = 0, False
    schema = CategorySchema(category_id="apparel", version="reviewed-1",
                            attributes=(AttributeSpec(name="size", dimension=Dimension.NOMINAL, criticality=Criticality.HARD),),
                            floor=frozenset({"size"}),
                            field_profiles=(FieldProfile(field_name="size", attributes=("size",), is_variant_axis=True,
                                                         certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),))
    schema_asset = write_json(tmp_path / "schema.json", json.loads(schema.model_dump_json()))
    for name, content in (("password", "secret-key-password"), ("extractor", "secret-extractor-key"),
                          ("token", "secret-api-token")):
        file = tmp_path / name
        file.write_text(content, encoding="utf-8")
        file.chmod(0o600)
    keys = KeyStore(tmp_path / "keys", password=b"secret-key-password")
    key_id = keys.rotate()
    public = tmp_path / "public-keys.json"
    keys.publish(public)
    ReceiptStore(tmp_path / "receipts.sqlite3")
    config = {"format": "approv-deployment-v1", "deployment_id": "pilot-test", "merchant_id": "merchant-1",
              "schemas": [schema_asset],
              "catalogue_reader": "approv.surface.verification:evidence_from_snapshot",
              "extractor": {"endpoint": "http://127.0.0.1:9999/v1", "model": "fixture-model", "prompt_version": "v6",
                            "credential": {"file": "extractor"},
                            "prices": {"input_per_million_usd": 1, "cached_input_per_million_usd": .5,
                                       "output_per_million_usd": 4, "as_of": "test-only"}},
              "signing": {"backend": "encrypted-file", "directory": "keys",
                          "password": {"file": "password"}, "key_id": key_id},
              "public_keys": {"path": "public-keys.json", "sha256": hashlib.sha256(public.read_bytes()).hexdigest()},
              "store": "receipts.sqlite3", "api_token": {"file": "token"},
              "floor_policy": {"unread_policy": "withdraw"}}
    path = tmp_path / "deployment.json"
    write_json(path, config)
    return load_deployment(path)


@pytest.fixture
def body():
    return {"merchant_id": "merchant-1", "correlation_id": "correlation-1", "category_id": "apparel",
            "order": {"order_id": "order-1", "product_id": "product-1", "sku": "sku-M", "quantity": 1,
                      "unit_price": {"kind": "money", "amount": "10.00", "currency": "USD"}},
            "product_snapshot": {"product_id": "product-1", "size": "M"},
            "artifact": {"shape": "structured", "protocol": "acp", "fields": {"size": "M"}}}


@pytest.fixture
def runtime(deployment):
    from approv.ops.app import Runtime
    return Runtime(deployment, interpreter_factory=Interpreter)
