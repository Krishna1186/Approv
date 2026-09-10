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
from datetime import datetime
from decimal import Decimal
from enum import Enum

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from pydantic import BaseModel

from approv.types.core import ComparisonRecord

VERSION = "chain-v1"

# The three fields that are *about* the record rather than *in* it. They are excluded
# from the digest because two of them are derived from it and the third signs it, so
# including any of them would make the hash depend on itself.
_UNSEALED = ("prev_hash", "hash", "signature")


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


def sealed_bytes(record: ComparisonRecord, prev_hash: str | None) -> bytes:
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
    payload = json.loads(record.model_dump_json(exclude=set(_UNSEALED)))
    return canonical_json({"prev_hash": prev_hash, "record": payload}).encode("utf-8")


def canonical_json(value) -> str:
    """The one dump format. Sorted keys, no whitespace, NaN refused.

    Deliberately trivial and stdlib-only, so the verifier in `scripts/verify_receipt.py`
    is the same three arguments and not a reimplementation of anything.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def record_hash(record: ComparisonRecord, prev_hash: str | None) -> str:
    return hashlib.sha256(sealed_bytes(record, prev_hash)).hexdigest()


def generate_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def public_key_hex(private_key: Ed25519PrivateKey) -> str:
    """The public half, as hex, for a verifier who has none of our code."""
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def seal(record: ComparisonRecord, private_key: Ed25519PrivateKey,
         prev_hash: str | None = None) -> ComparisonRecord:
    """Return the record with its link, digest and signature filled in.

    A new object rather than a mutation, because `ComparisonRecord` is frozen and because
    a half-sealed record should never exist: either it carries all three fields or none.
    """
    digest = record_hash(record, prev_hash)
    signature = private_key.sign(digest.encode("utf-8")).hex()
    return record.model_copy(update={"prev_hash": prev_hash, "hash": digest,
                                     "signature": signature})


def verify(record: ComparisonRecord, public_key_hex_value: str) -> None:
    """Raise unless this record hashes and verifies as sealed. Returns None on success.

    Raising rather than returning False: a verifier whose failure path is a falsy value
    is one call site away from being ignored, and this one gates whether a piece of
    evidence is admissible.
    """
    if not record.hash or not record.signature:
        raise ValueError("record is unsealed")
    if record_hash(record, record.prev_hash) != record.hash:
        raise ValueError("record content does not match its hash")
    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex_value))
    try:
        key.verify(bytes.fromhex(record.signature), record.hash.encode("utf-8"))
    except InvalidSignature as error:
        raise ValueError("signature does not verify under this key") from error


def verify_chain(records: list[ComparisonRecord], public_key_hex_value: str) -> None:
    """Raise unless the whole chain is intact, in order, from a null-linked genesis.

    Checked as a sequence and not per record, because the per-record check cannot see a
    *deletion*: every surviving record still verifies on its own. Only the links do.
    """
    previous = None
    seen = set()
    for index, record in enumerate(records):
        if record.prev_hash != previous:
            raise ValueError(f"chain broken at index {index} ({record.correlation_id})")
        # A reused correlation id means the same session was decided twice, which is the
        # replay in the error catalogue, and it is invisible to hashing.
        if record.correlation_id in seen:
            raise ValueError(f"correlation id reused at index {index}")
        seen.add(record.correlation_id)
        verify(record, public_key_hex_value)
        previous = record.hash
