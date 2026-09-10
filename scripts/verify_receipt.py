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
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError:  # pragma: no cover - environment guard
    sys.exit("this verifier needs `cryptography`:  pip install cryptography")

# Fields that describe the sealing rather than the comparison, so they are removed before
# the digest is taken. Two are derived from it and one signs it.
UNSEALED = ("prev_hash", "hash", "signature")


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
    try:
        public_key.verify(bytes.fromhex(signature), stated.encode("utf-8"))
    except InvalidSignature:
        raise ValueError("signature does not verify under this key") from None


def verify_chain(records: list[dict], key_hex: str) -> list[str]:
    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex))
    previous, seen, lines = None, set(), []
    for index, record in enumerate(records):
        label = record.get("correlation_id", "?")
        if record.get("prev_hash") != previous:
            raise ValueError(f"chain broken at index {index} ({label}): "
                             f"prev_hash does not point at the record before it. "
                             f"A record has been removed, reordered or inserted.")
        if label in seen:
            raise ValueError(f"correlation id reused at index {index} ({label}): "
                             f"the same decision appears twice")
        seen.add(label)
        try:
            verify_one(record, public_key)
        except ValueError as error:
            raise ValueError(f"record {index} ({label}): {error}") from None
        lines.append(f"  [{index}] {label:24s} {record.get('decision','?'):8s} "
                     f"{record.get('product_id','?')}")
        previous = record["hash"]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("receipts", help="a record object, or an array of them in chain order")
    parser.add_argument("--key", required=True, help="Ed25519 public key, hex")
    args = parser.parse_args()

    with open(args.receipts, encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload if isinstance(payload, list) else [payload]

    try:
        lines = verify_chain(records, args.key)
    except (ValueError, KeyError) as error:
        print(f"FAILED: {error}")
        return 1

    print(f"OK: {len(records)} record(s), chain intact, every signature valid.")
    print("\n".join(lines))
    print("\nThis proves the records are the ones that were signed and that none has "
          "moved.\nIt does not prove the product data was true or the decision correct.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
