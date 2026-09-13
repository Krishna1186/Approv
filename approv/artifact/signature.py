"""How to check the signature without trusting Approv, or running any of its code.

`scripts/verify_receipt.py` already meets §10's bar for an engineer: a standalone
verifier importing nothing of ours. This is the same procedure written for the document
itself, so the instructions travel with the evidence rather than living in a repository
the reader has no access to. A merchant arguing a dispute cannot tell their counterparty
to clone something.

The steps are deliberately the short ones. The digest is taken over the record's **JSON**
minus three fields, wrapped with the link it claims, dumped with sorted keys and no
whitespace — so the whole procedure is load, drop three keys, re-dump, SHA-256, verify.
Anyone can reimplement that in an afternoon in another language, which is what makes the
record evidence rather than an assertion.
"""

from __future__ import annotations

KEY_PLACEHOLDER = "<Approv's published Ed25519 public key, hex>"

# The three fields that describe the sealing rather than the comparison. Two are derived
# from the digest and the third signs it, so all three come out before it is taken.
UNSEALED = ("prev_hash", "hash", "signature")

UNSIGNED_STEPS = (
    "This record carries no signature, so there is nothing to check. It cannot be shown "
    "to be the record Approv issued, and it should not be relied on in a dispute.",
    "Ask Approv for the signed copy of this record before using it.",
)

STEPS = (
    "Take the record as JSON, exactly as the verification call returned it. Not a "
    "re-export, not a copy pasted out of a spreadsheet: one changed byte changes the "
    "digest.",
    "Remove the three sealing fields: prev_hash, hash and signature.",
    'Wrap what is left as {"prev_hash": <the record\'s prev_hash, or null>, "record": '
    "<the rest>}.",
    "Serialise that with sorted keys and no whitespace, then take its SHA-256. The hex "
    "digest must equal the record digest printed above. If it does not, the record has "
    "been altered since it was signed.",
    "Check the signature field, read as hex, as an Ed25519 signature over the ASCII "
    "bytes of that hex digest, using Approv's published public key.",
    "If this record follows another, the prev_hash above is the previous record's "
    "digest. Checking a run of records in order is what catches a deleted one: each "
    "surviving record still passes on its own, and only the links notice a gap.",
)

CANNOT_PROVE = (
    "A valid signature proves this is the record Approv issued and that nothing in it "
    "has moved since. It does not prove the catalogue data was true, that the merchant's "
    "own fields were honest, or that the decision was the right one. Those are arguments "
    "about evidence, and this is what makes them possible."
)

_SNIPPET = '''import hashlib, json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PUBLIC_KEY = "__KEY__"
with open("__FILE__", encoding="utf-8") as handle:
    record = json.load(handle)

body = {k: v for k, v in record.items()
        if k not in ("prev_hash", "hash", "signature")}
blob = json.dumps({"prev_hash": record.get("prev_hash"), "record": body},
                  sort_keys=True, separators=(",", ":"),
                  ensure_ascii=False, allow_nan=False)
digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
assert digest == record["hash"], "this record has been altered since it was signed"

Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY)).verify(
    bytes.fromhex(record["signature"]), digest.encode("utf-8"))
print("verified:", record["correlation_id"], record["decision"])'''


def snippet(public_key: str | None = None, record_file: str = "record.json") -> str:
    """The procedure as runnable Python. Standard library plus one signature library.

    Nothing of Approv's appears in it, which is the point: a verifier built out of our
    code proves only that we agree with ourselves. Asserted by test, both that the text
    imports nothing of ours and that running it verbatim actually verifies a sealed
    record and rejects an altered one.
    """
    return _SNIPPET.replace("__KEY__", public_key or KEY_PLACEHOLDER).replace(
        "__FILE__", record_file)


def steps(*, signed: bool) -> tuple[str, ...]:
    return STEPS if signed else UNSIGNED_STEPS
