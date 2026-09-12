# Receipt operations

The comparison format and Ed25519/SHA-256 construction are retained. `seal()` now
fills `key_id` with the SHA-256 fingerprint of the public key and accepts only
`signature_version="ed25519-sha256-v1"`. Both fields are inside the signed digest.
The only excluded fields remain `prev_hash`, `hash`, and `signature`; the predecessor
is bound separately in the existing signed envelope.

## Keys

```python
from getpass import getpass
from approv.receipts.keys import KeyStore

keys = KeyStore("/private/approv-keys", password=getpass("Key password: ").encode())
keys.rotate()                       # first key, or the next rotation
keys.publish("/publication/public-keys.json")
signing_key = keys.load_private()   # active key; callers may hold it for in-flight work
```

The layout is `private/<fingerprint>.pem`, `public/<fingerprint>.json`, and
`active.json`. Private keys are encrypted PKCS8 PEMs. Keep the password in the
deployment's secret manager, separately from the directory. New keys use exclusive
file creation; activation and publication use atomic replacement. On POSIX the
directories/files are owner-restricted; on Windows use a service-owned directory
ACL as well as the mandatory encryption.

Rotation publishes the new public key before switching the active pointer. Old
private files and public keys remain available; public-key publication includes
every historical key. Rotation does not invalidate old signatures or re-sign old
receipts. Publish through a trusted merchant/Approv channel: a file supplied solely
by an adversary is not a trust anchor. Key compromise/revocation policy is distinct
from routine rotation and is not implemented by marking old signatures invalid.

## Append-only store

```python
import json
from pathlib import Path
from approv.receipts.store import ReceiptStore

store = ReceiptStore("/data/receipts.sqlite")
receipt = store.append(unsigned_record, keys.load_private())
exported = store.export()
Path("receipts.json").write_text(json.dumps(exported), encoding="utf-8")
Path("checkpoint.json").write_text(json.dumps(exported["checkpoint"]), encoding="utf-8")
```

`append()` owns the chain head and signs under `BEGIN IMMEDIATE`. Separate processes
cannot allocate the same next link. Receipt, public key and signed checkpoint commit
together with SQLite WAL and FULL synchronous mode. Immutable tables and INSERT
guards reject updates, deletes, conflicting IDs and `INSERT OR REPLACE`, including
through ordinary SQL connections. Readers/exporters use one consistent transaction.

A retry of the same unsigned record returns the original sealed receipt, including
after rotation and restart. Reuse of its correlation ID for different content raises
`ReplayError`. Recreate neither the timestamp nor the request on a retry: retain the
original input or resend the sealed receipt. Replay identity is scoped to this store;
payment execution and distributed cross-store replay prevention belong to the calling
service. Correlation IDs must distinguish separate legitimate decisions.

Already signed receipts are verified and retained exactly, never relinked or re-signed.
They must extend the current head, unless they are exact retries. Register the original
published key with `register_public_key()` before importing an identified receipt
signed under a key other than the checkpoint signing key. A stale signed predecessor
raises `ChainConflict`; the caller must not silently rewrite that historical receipt.

The store retains the complete signed JSON, key history and a signed checkpoint for
every append. It reconstructs and validates the chain from the database alone without
private keys or today's schema reserialization. The receipt's original decision time,
request, order line and snapshot remain signed data. No caller-owned mutable dict can
change a committed row.

## Independent verification

Copy only `scripts/verify_receipt.py`, the exported JSON and the published public-key
file to another machine with Python and `cryptography`. No Approv package is needed.

```powershell
python verify_receipt.py receipts.json --keys public-keys.json --checkpoint checkpoint.json
python verify_receipt.py single-receipt.json --key OLD_PUBLIC_KEY_HEX
```

The first command verifies a chain spanning rotations, its signed count/head, and an
independently retained checkpoint. A single receipt object verifies individually even
when its predecessor is elsewhere; the verifier explicitly does not claim chain
completeness for that case. Legacy receipts without key identifiers/version fields
still verify against an explicitly pinned historical public key, using their original
JSON field set. Unknown explicit versions and altered key mappings are rejected.

Retain checkpoints outside the writable database/export boundary at issuance, and
keep their public keys trusted. SQL triggers enforce append-only behaviour but cannot
stop a database administrator from replacing the whole file or dropping the schema.
An old complete chain still has valid signatures; comparing it with a later retained
checkpoint exposes rollback. An embedded checkpoint alone cannot expose replacement
of the entire bundle with an older valid bundle.

Signatures attest the recorded snapshot and order, not physical fulfilment, catalogue
truth or an independently certified clock. External retention establishes that the
signed snapshot existed by the time the checkpoint was retained. This implementation
provides the checkpoint artifact; deployment must provide that independent retention.

The isolated acceptance test is
`test_a_stranger_verifies_before_and_after_rotation_from_the_reopened_store` in
`tests/test_receipt_hardening.py`. Existing receipt/verifier tests remain unchanged.
