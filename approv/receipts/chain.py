"""Hashing, signing and chaining comparison records.

The threat this answers is not a stranger forging a record. It is *us* editing one after
the outcome is known — quietly turning a `confirm` we issued into the `allow` the dispute
needs, or dropping the record of a refusal that cost a sale. A signature stops an
outsider; the chain stops the insider, because changing any earlier record breaks every
hash after it and the tampering shows up at the head rather than at the row that moved.

Ed25519 rather than RSA or ECDSA: deterministic (no per-signature nonce to leak a key
through), small keys and signatures, and no parameter choices to get wrong.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from pydantic import AfterValidator, BaseModel

from approv.types.core import ComparisonRecord, OrderEvidenceRecord

VERSION = "chain-v1"
SIGNATURE_VERSION = "ed25519-sha256-v1"

# The three fields that are *about* the record rather than *in* it. They are excluded
# from the digest because two of them are derived from it and the third signs it, so
# including any of them would make the hash depend on itself.
_UNSEALED = ("prev_hash", "hash", "signature")


class SandboxReceipt(ComparisonRecord):
    """Store-owned extension: sandbox is independent of shadow/enforce mode.

    These fields are inside the digest. Keep the whole JSON when verifying; parsing
    it as the narrower ComparisonRecord deliberately fails on the extra fields.
    Production receipts retain their existing wire schema.
    """

    store_namespace: Literal["sandbox"]
    store_id: str


class SandboxOrderEvidence(OrderEvidenceRecord):
    """The same store-owned extension for the cart-only product. See `SandboxReceipt`.

    A separate class rather than a shared mixin because the two wire schemas must stay
    independently narrow: parsing either as anything but itself has to fail on the extra
    fields, and that property is what `_check_record_namespace` leans on.
    """

    store_namespace: Literal["sandbox"]
    store_id: str


# Both receipt products seal, chain and verify by exactly the same rules, because the
# digest is taken over a record's JSON and the only thing the chain asks of a record is
# that it carry the sealing field set. The alternative — keeping the ledger
# ComparisonRecord-only — would have forced cart-only orders back into a verification
# with an empty request, which is the shape `OrderEvidenceRecord` exists to stop. So the
# ledger learns the second product; the second product does not learn to impersonate the
# first. An order with no stated request is the population DR 0020 most wants measured,
# and a receipt outside the chain is not evidence.
_SEALABLE = (ComparisonRecord, OrderEvidenceRecord)
_SANDBOX_MODEL = {"verification": SandboxReceipt, "order_evidence": SandboxOrderEvidence}
_RECEIPT_MODEL = {"verification": ComparisonRecord, "order_evidence": OrderEvidenceRecord}


def require_unsealed(record):
    """Reject signed, partially signed, or caller-linked inputs before any write."""
    if not isinstance(record, _SEALABLE):
        raise TypeError("append requires an unsealed ComparisonRecord or OrderEvidenceRecord")
    if any(getattr(record, field) is not None for field in (*_UNSEALED, "key_id")):
        raise ValueError("store requires an unsealed record; use get() to read a retained receipt")
    if record.signature_version != SIGNATURE_VERSION:
        raise ValueError("unsupported signature_version")
    # Validate and detach caller-owned dictionaries before entering the transaction.
    return type(record).model_validate_json(record.model_dump_json())


UnsealedRecord = Annotated[
    Union[ComparisonRecord, OrderEvidenceRecord], AfterValidator(require_unsealed),
]


def load_receipt(payload: dict):
    """Read the signed field set without adding defaults to historical receipts.

    `kind` decides the product and defaults to a verification, so receipts written before
    the field existed still read as what they were.
    """
    sandboxed = "store_namespace" in payload or "store_id" in payload
    table = _SANDBOX_MODEL if sandboxed else _RECEIPT_MODEL
    return table[payload.get("kind", "verification")].model_validate(payload)


def canonical(value) -> str:
    """One byte sequence per record, so a signature means something.

    A signature covers bytes, not objects. If the same record can serialise two ways —
    keys reordered, a Decimal rendered as float here and string there, a timezone
    written two ways — then a verifier can be handed bytes that do not match what was
    signed and reject a record that is genuinely ours. Sorted keys, no whitespace,
    Decimal as its exact string, datetimes as ISO 8601, and NaN refused outright.
    """
    def normalise(item):
        if isinstance(item, BaseModel):
            return normalise(item.model_dump(mode="python"))
        if isinstance(item, dict):
            return {k: normalise(v) for k, v in item.items()}
        if isinstance(item, (set, frozenset)):
            return sorted((normalise(v) for v in item),
                          key=lambda v: json.dumps(v, sort_keys=True))
        if isinstance(item, (list, tuple)):
            return [normalise(v) for v in item]
        if isinstance(item, datetime):
            return item.isoformat()
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, Enum):
            return item.value
        return item
    return json.dumps(normalise(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def record_json(record) -> dict:
    """Preserve the fields actually signed, including records from older schemas."""
    if isinstance(record, _SEALABLE):
        return json.loads(record.model_dump_json(exclude_unset=bool(record.signature)))
    return dict(record)


def sealed_bytes(record: ComparisonRecord | Mapping, prev_hash: str | None) -> bytes:
    """Exactly what gets hashed and signed: the record's content plus its link.

    Defined over the record's **JSON** form, not its Python objects. That is not a detail.
    A third party holds a `.json` file and nothing else, so if the digest were taken over
    Python objects they would have to reproduce Pydantic's Decimal and datetime handling
    exactly to check a signature — and any drift between the two serialisations rejects a
    record that is genuinely ours. Hashing the JSON means the verifier's job is: load,
    drop three fields, re-dump with sorted keys, SHA-256. Writing the standalone verifier
    is what surfaced this; the object-mode digest could not have been reproduced.

    `prev_hash` is bound in rather than left alongside. If the link sat outside the
    signature, a record could be lifted out of one chain and pasted into another with its
    signature still valid, which is the whole attack the chain exists to stop.
    """
    payload = {k: v for k, v in record_json(record).items() if k not in _UNSEALED}
    return canonical_json({"prev_hash": prev_hash, "record": payload}).encode("utf-8")


def canonical_json(value) -> str:
    """The one dump format. Sorted keys, no whitespace, NaN refused.

    Deliberately trivial and stdlib-only, so the verifier in `scripts/verify_receipt.py`
    is the same three arguments and not a reimplementation of anything.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def record_hash(record: ComparisonRecord | Mapping, prev_hash: str | None) -> str:
    return hashlib.sha256(sealed_bytes(record, prev_hash)).hexdigest()


def generate_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def public_key_hex(private_key: Ed25519PrivateKey) -> str:
    """The public half, as hex, for a verifier who has none of our code."""
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def key_id_for(public_hex: str) -> str:
    """A content-addressed ID; publication cannot silently reassign an ID to a key."""
    raw = bytes.fromhex(public_hex)
    Ed25519PublicKey.from_public_bytes(raw)
    return "ed25519:" + hashlib.sha256(raw).hexdigest()


def public_key_for(record: Mapping, trusted_keys: str | Mapping[str, str]) -> str:
    if isinstance(trusted_keys, str):
        return trusted_keys
    key_id = record.get("key_id")
    if not key_id or key_id not in trusted_keys:
        raise ValueError("unknown signing key; legacy receipts require an explicitly pinned public key")
    public_hex = trusted_keys[key_id]
    if key_id_for(public_hex) != key_id:
        raise ValueError("published key does not match its key_id")
    return public_hex


def seal(record: ComparisonRecord, private_key: Ed25519PrivateKey,
         prev_hash: str | None = None) -> ComparisonRecord:
    """Return the record with its link, digest and signature filled in.

    A new object rather than a mutation, because `ComparisonRecord` is frozen and because
    a half-sealed record should never exist: either it carries all three fields or none.
    """
    if record.hash is not None or record.signature is not None:
        raise ValueError("record is already sealed; retain its original signature and link")
    if record.signature_version != SIGNATURE_VERSION:
        raise ValueError("unsupported signature_version")
    key_id = key_id_for(public_key_hex(private_key))
    if record.key_id not in (None, key_id):
        raise ValueError("key_id does not identify the signing key")
    # Materialise all defaults before signing. On subsequent reads the exact signed
    # field set survives, even if a future schema acquires new defaulted fields.
    record = type(record).model_validate_json(record.model_dump_json())
    record = record.model_copy(update={"key_id": key_id})
    digest = record_hash(record, prev_hash)
    signature = private_key.sign(digest.encode("utf-8")).hex()
    return record.model_copy(update={"prev_hash": prev_hash, "hash": digest,
                                     "signature": signature})


def verify(record: ComparisonRecord | Mapping, public_key_hex_value: str | Mapping[str, str]) -> None:
    """Raise unless this record hashes and verifies as sealed. Returns None on success.

    Raising rather than returning False: a verifier whose failure path is a falsy value
    is one call site away from being ignored, and this one gates whether a piece of
    evidence is admissible.
    """
    payload = record_json(record)
    if not payload.get("hash") or not payload.get("signature"):
        raise ValueError("record is unsealed")
    if record_hash(payload, payload.get("prev_hash")) != payload["hash"]:
        raise ValueError("record content does not match its hash")
    version = payload.get("signature_version")
    if "signature_version" in payload and version != SIGNATURE_VERSION:
        raise ValueError("unsupported signature_version")
    public_hex = public_key_for(payload, public_key_hex_value)
    if payload.get("key_id") and (version != SIGNATURE_VERSION or
                                   payload["key_id"] != key_id_for(public_hex)):
        raise ValueError("signature does not verify: signing key or version mismatch")
    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex))
    try:
        key.verify(bytes.fromhex(payload["signature"]), payload["hash"].encode("utf-8"))
    except InvalidSignature as error:
        raise ValueError("signature does not verify under this key") from error


def verify_chain(records: list[ComparisonRecord | Mapping], public_key_hex_value: str | Mapping[str, str]) -> None:
    """Raise unless the whole chain is intact, in order, from a null-linked genesis.

    Checked as a sequence and not per record, because the per-record check cannot see a
    *deletion*: every surviving record still verifies on its own. Only the links do.
    """
    previous = None
    seen = set()
    for index, record in enumerate(records):
        payload = record_json(record)
        if payload.get("prev_hash") != previous:
            raise ValueError(f"chain broken at index {index} ({payload.get('correlation_id')})")
        # A reused correlation id means the same session was decided twice, which is the
        # replay in the error catalogue, and it is invisible to hashing.
        correlation = payload.get("correlation_id")
        if not isinstance(correlation, str) or not correlation.strip():
            raise ValueError("record needs a nonempty correlation_id")
        if correlation in seen:
            raise ValueError(f"correlation id reused at index {index}")
        seen.add(correlation)
        verify(record, public_key_hex_value)
        previous = payload["hash"]
