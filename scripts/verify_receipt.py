#!/usr/bin/env python3
"""Verify an Approv receipt chain. Independent of Approv.

This file imports nothing from `approv` and nothing outside the standard library except
`cryptography`. That constraint is the entire point: a receipt whose only verifier is our
own code proves that we agree with ourselves. Section 10's bar for this stage is that a
stranger checks a receipt with a public key and none of our code, so this is written to
be read by that stranger, copied, or reimplemented in another language in an afternoon.

    python scripts/verify_receipt.py receipts.json --key <public-key-hex>

`receipts.json` is one record object or a JSON array of them, in chain order.

What it checks
    1. Each record hashes to its stated `hash`, over the record minus the three sealing
       fields, wrapped with the `prev_hash` it claims. Editing any field breaks this.
    2. That hash carries a valid Ed25519 signature under the given public key.
    3. Each `prev_hash` equals the previous record's `hash`, starting from null. This is
       what catches a *deletion*: every surviving record still passes checks 1 and 2 on
       its own, and only the links notice that one is gone.
    4. No `correlation_id` appears twice, which would be the same decision recorded twice.

What it cannot tell you
    That the product data was true, that the catalogue was honest, or that the decision
    was correct. It tells you the record is the one that was signed, and that none of it
    has moved since. Everything else is an argument about evidence, and this is what
    makes that argument possible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError:  # pragma: no cover - environment guard
    sys.exit("this verifier needs `cryptography`:  pip install cryptography")

# Fields that describe the sealing rather than the comparison, so they are removed before
# the digest is taken. Two are derived from it and one signs it.
UNSEALED = ("prev_hash", "hash", "signature")
SIGNATURE_VERSION = "ed25519-sha256-v1"


def canonical(value) -> str:
    """Sorted keys, no whitespace, NaN refused. The whole serialisation rule."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def record_hash(record: dict) -> str:
    body = {k: v for k, v in record.items() if k not in UNSEALED}
    return hashlib.sha256(
        canonical({"prev_hash": record.get("prev_hash"), "record": body}).encode("utf-8")
    ).hexdigest()


def verify_one(record: dict, public_key: Ed25519PublicKey) -> None:
    stated = record.get("hash")
    signature = record.get("signature")
    if not stated or not signature:
        raise ValueError("record is unsealed: no hash or no signature")
    recomputed = record_hash(record)
    if recomputed != stated:
        raise ValueError(f"content does not match its hash\n"
                         f"      stated     {stated}\n"
                         f"      recomputed {recomputed}")
    version = record.get("signature_version")
    if "signature_version" in record and version != SIGNATURE_VERSION:
        raise ValueError("unsupported signature_version")
    raw_key = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = "ed25519:" + hashlib.sha256(raw_key).hexdigest()
    if record.get("key_id") and (record["key_id"] != key_id or version != SIGNATURE_VERSION):
        raise ValueError("signature does not verify: signing key or version mismatch")
    try:
        public_key.verify(bytes.fromhex(signature), stated.encode("utf-8"))
    except InvalidSignature:
        raise ValueError("signature does not verify under this key") from None


def public_key_for(record: dict, keys: str | dict) -> Ed25519PublicKey:
    if isinstance(keys, str):
        return Ed25519PublicKey.from_public_bytes(bytes.fromhex(keys))
    key_id = record.get("key_id")
    if not key_id or key_id not in keys:
        raise ValueError("unknown signing key; legacy receipts require an explicitly pinned public key")
    raw = bytes.fromhex(keys[key_id])
    if key_id != "ed25519:" + hashlib.sha256(raw).hexdigest():
        raise ValueError("published key does not match its key_id")
    return Ed25519PublicKey.from_public_bytes(raw)


def verify_chain(records: list[dict], key_hex: str | dict) -> list[str]:
    previous, seen, lines = None, set(), []
    for index, record in enumerate(records):
        label = record.get("correlation_id", "?")
        if not isinstance(label, str) or not label.strip() or label == "?":
            raise ValueError("record needs a nonempty correlation_id")
        if record.get("prev_hash") != previous:
            raise ValueError(f"chain broken at index {index} ({label}): "
                             f"prev_hash does not point at the record before it. "
                             f"A record has been removed, reordered or inserted.")
        if label in seen:
            raise ValueError(f"correlation id reused at index {index} ({label}): "
                             f"the same decision appears twice")
        seen.add(label)
        try:
            verify_one(record, public_key_for(record, key_hex))
        except ValueError as error:
            raise ValueError(f"record {index} ({label}): {error}") from None
        lines.append(f"  [{index}] {label:24s} {record.get('decision','?'):8s} "
                     f"{record.get('product_id','?')}")
        previous = record["hash"]
    return lines


def verify_checkpoint(checkpoint: dict, records: list[dict], keys: str | dict) -> None:
    if checkpoint.get("format") != "approv-receipt-checkpoint-v1":
        raise ValueError("unsupported checkpoint format")
    if not isinstance(checkpoint.get("store_id"), str) or not checkpoint["store_id"]:
        raise ValueError("checkpoint needs a store_id")
    if type(checkpoint.get("count")) is not int or checkpoint["count"] != len(records):
        raise ValueError("checkpoint count does not match export; possible truncation")
    if checkpoint.get("head_hash") != (records[-1]["hash"] if records else None):
        raise ValueError("checkpoint head does not match export")
    verify_one(checkpoint, public_key_for(checkpoint, keys))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=_unique_object)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("receipts", help="a record object, or an array of them in chain order")
    trust = parser.add_mutually_exclusive_group(required=True)
    trust.add_argument("--key", help="pinned Ed25519 public key, hex (also verifies legacy receipts)")
    trust.add_argument("--keys", help="published public-keys JSON; includes retired rotation keys")
    parser.add_argument("--checkpoint", help="independently retained signed checkpoint for this exact export")
    args = parser.parse_args()

    try:
        keys = args.key
        if args.keys:
            published = read_json(args.keys)
            if published.get("format") != "approv-public-keys-v1":
                raise ValueError("unsupported public key publication format")
            keys = published["keys"]
            if not isinstance(keys, dict) or not keys:
                raise ValueError("publication contains no keys")
        payload = read_json(args.receipts)
        checkpoint = None
        if isinstance(payload, dict) and payload.get("format") == "approv-receipt-export-v1":
            records, checkpoint = payload["records"], payload["checkpoint"]
            if not isinstance(records, list) or not records or not isinstance(checkpoint, dict):
                raise ValueError("export requires records and a signed checkpoint")
        elif isinstance(payload, dict):
            if args.checkpoint:
                raise ValueError("a chain checkpoint requires a complete chain export")
            verify_one(payload, public_key_for(payload, keys))
            print("OK: receipt signature valid. Standalone receipt; chain completeness not checked.")
            return 0
        else:
            records = payload
        if not isinstance(records, list) or not records:
            raise ValueError("no receipts to verify")
        lines = verify_chain(records, keys)
        if checkpoint:
            verify_checkpoint(checkpoint, records, keys)
        if args.checkpoint:
            retained = read_json(args.checkpoint)
            verify_checkpoint(retained, records, keys)
            if checkpoint and retained["store_id"] != checkpoint["store_id"]:
                raise ValueError("retained checkpoint belongs to a different store")
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
        print(f"FAILED: {error}")
        return 1

    print(f"OK: {len(records)} record(s), chain intact, every signature valid.")
    print("\n".join(lines))
    print("\nThis proves the records are the ones that were signed and that none has "
          "moved.\nIt does not prove the product data was true or the decision correct.")
    if not args.checkpoint:
        print("A retained external checkpoint is needed to detect rollback to an older valid export.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
