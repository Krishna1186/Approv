# Merchant pilot operations

This release supplies a runnable service, configuration loader, signing backends,
SQLite administration and measurements. It provisions nothing. The founder chooses
the host, region, provider contract, ingress, secret delivery, retention and budget.

## Operating boundary

Use `python -m approv.ops serve`, not the unconfigured API factory. The operations
adapter calls the existing `verify_order`, then signs and commits the result before
returning HTTP 200. `allow`, `confirm` and `refuse` remain the purchase decisions.
DR 0004's separate `completion` field distinguishes a completed comparison from an
unavailable provider, unreadable response/catalogue or exceeded comparison budget.
Those incomplete records are also signed, retained and returned as HTTP 200, with
`decision=confirm`, `covered=false` and no guaranteed findings. **HTTP 200 alone is
never permission to proceed as verified.** Key, storage and assembly failures that
prevent issuing a trustworthy record return HTTP 503 `system_failure` with a stage.
The merchant must handle that as verification unavailable, never an implicit allow.

The initial target is one merchant, one process, one SQLite database on a persistent
local disk. Do not run multiple worker processes or put SQLite WAL on NFS. The SQL
store serializes writers, while extraction can run concurrently. `max_inflight`
bounds verification work; excess calls return 503. JSON bodies have a configured
size limit and a 10-second receive-idle timeout. Configure an ingress body deadline,
rate limit and TLS; the development listener defaults to loopback.

Receipt operations currently audit the retained chain on lookup and append. That
cost grows with history, and KMS signing happens inside the writer transaction.
Measure p95 at the pilot's expected retained receipt count before increasing traffic.
This release does not assert a sub-500ms budget or a throughput guarantee.

## Configuration and secrets

Copy `deployment.example.json` outside the repository, replace every placeholder,
and select it with `APPROV_CONFIG` or `--config`. The example is intentionally invalid
until real reviewed assets, key fingerprints and provider prices are supplied.
Relative paths resolve against the configuration file, not the process directory.
There is no automatic `.env` loading, fallback schema, fallback key or empty store.

| Input | Deployment source | Failure behaviour |
|---|---|---|
| Categories and floor | SHA-256-pinned JSON `CategorySchema` files, or confirmed onboarding exports | Missing, changed, duplicate category or empty floor prevents startup |
| Catalogue reader | Explicit trusted `module:callable` in configuration | Import failure or an incompatible known profile format prevents startup |
| Unread policy and calibrated returns | Explicit `floor_policy.unread_policy`: `withdraw` or `escalate` | Missing or invalid policy prevents startup; measurement-only `ignore` is rejected |
| Extractor | HTTPS endpoint, model identifier, existing `v6` prompt, credential file, contract prices | Missing secret prevents startup; transport or malformed interpretation is retained with its distinct incomplete outcome |
| Signing | Explicit backend and published key fingerprint | Missing key or substitution prevents startup; signing failures return 503 |
| Receipt database | Explicit durable path, already initialized and migrated | Missing or wrong-version database prevents startup |
| Merchant authentication | One merchant ID and bearer-token file | Missing token prevents startup; other merchants get 403 |

Configuration is trusted executable deployment input: only the release operator may
write it or its reader module. A request cannot override schemas, signing, extraction,
reader or floor policy. Schema hashes establish which reviewed file was loaded; they
do not authenticate a reviewer. Preserve the review and release approval separately.
Use `ConfirmedSchema.model_dump_json(round_trip=True)` when exporting onboarding data.

Select `withdraw` to retain DR 0022's coverage-withdrawal policy for an unfinished
reading, or explicitly select `escalate`. Neither option allows an incomplete
verification to authorise: the independent completion axis always fails its floor.

The existing default `evidence_from_snapshot` reader accepts dotted field profiles,
such as `variant.size`. Onboarding's `/.../*/...#name=...` locators require a compatible
reader supplied by that integration. This configuration loader explicitly rejects
those profiles with the dotted-field reader; it does not silently sign missing
evidence. It does not implement that separate catalogue adapter. For the first pilot,
deploy reviewed schemas and a reader that agree, and exercise actual selected-SKU
snapshots before admitting traffic. Readiness's empty-snapshot check establishes
reader availability, not correctness on the merchant's catalogue.

Secrets are file references only. A secret delivery agent, container secret mount or
operator supplies their contents. The app does not create secret-manager resources.
Use owner-only POSIX permissions (`0600`, owned by the service UID); on Windows restrict
NTFS ACLs to the service identity and administrators. One trailing newline is removed.
Empty, multiline, oversized or missing values fail closed. Keep secret values out of
command arguments, images, source control and configuration JSON. Provider and token
files are re-read on use, allowing atomic file replacement. Restart to activate
configuration, schema, public-key publication or signing-key changes.

The signed checkpoint binds a request hash, the retained deployment manifest hash
and the exact response hash. The manifest retains the schema, reader identifier,
model/prompt, policy and price assumptions without credentials or secret paths.
Records carry the actual configured model and prompt identifiers instead of the
surface's placeholder version. Use immutable provider model IDs when available;
a provider alias cannot prove which model weights the provider ran.

## Production signing decision

**Recommend KMS for production.** Approv's signing-key integrity is the product.
An additional network cost is preferable to allowing an exported key to support
undetectable offline signatures indefinitely after a host compromise. This is a
recommendation; the backend has no default and the founder explicitly selects it.

| Choice | Latency and availability | Host compromise |
|---|---|---|
| KMS asymmetric signing | One network hop per signature; this store signs the receipt **and** its checkpoint, so two signing calls per new verification. KMS failure makes verification unavailable. | Private material stays in KMS. A compromised workload can still misuse its signing permission until revoked. |
| Secrets manager delivers an encrypted private key and password to the host | Key retrieval occurs at startup/refresh; local signing has no per-signature network hop. Local decryption still has a cost. | The host can access the decrypted key. Compromise can enable permanent offline forgery under that key even after workload credentials are revoked. |

The KMS adapter supports an Ed25519 `SIGN_VERIFY` key, an immutable key ARN and a
separately published fingerprint. It obtains the public key once, checks it against
that publication and locally verifies each returned signature. It uses
`ED25519_SHA_512` with `MessageType=RAW` over the same 64 ASCII digest bytes the local
signer signs. Ed25519ph is a different signature contract and is rejected.
[AWS Sign API](https://docs.aws.amazon.com/kms/latest/APIReference/API_Sign.html),
[public-key export](https://docs.aws.amazon.com/kms/latest/APIReference/API_GetPublicKey.html).

For provisioning, the founder supplies an existing key ARN, its public key and a
workload identity restricted to `kms:GetPublicKey` and `kms:Sign` on that key. This
code neither creates keys in AWS nor grants permissions. SDK retries are disabled;
connect and read timeouts are explicit. Public keys remain locally publishable and
offline-verifiable during a KMS outage. Choose a region after measuring signing
latency from the intended host, including both calls and writer contention.

For an explicitly accepted local-key pilot, replace `signing` with:

```json
{
  "backend": "encrypted-file",
  "directory": "/run/secrets/approv/keys",
  "password": {"file": "/run/secrets/approv/signing-password"},
  "key_id": "ed25519:REPLACE_WITH_PUBLISHED_FINGERPRINT"
}
```

Generate or rotate local material only as an administration action:

```sh
python -m approv.ops rotate-local-key --directory /secure/keys --password-file /secure/signing-password --publish /release/public-keys.json
```

Use a managed secret service to retain and deliver that encrypted directory and
password, with distinct administration permissions. Caching avoids a remote read per
signature, but does not remove the host's ability to obtain private material.
[AWS secret retrieval and caching guidance](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html).

Rotation: publish the new public key **alongside every old key**, independently
distribute the publication, update the pinned publication hash and active fingerprint,
then restart and check readiness. Use a new immutable KMS key ARN for a KMS rotation;
do not repoint an alias behind a running process. Retain old public keys forever.
Existing retries return the original signed response without extraction or re-signing.
Never regenerate the receipt timestamp to process a retry. A changed request under
the same correlation ID gets 409; use one durable ID per order-line verification.
A retry of a recorded incomplete verification returns that same incomplete record,
even after the provider recovers. A new verification attempt needs a new correlation ID.

## Install, initialize and start

From an isolated environment at the reviewed commit:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements-pilot.txt
.venv/bin/python -m approv.ops migrate --store /var/lib/approv/receipts.sqlite3
.venv/bin/python -m approv.ops check-config --config /etc/approv/deployment.json
.venv/bin/python -m approv.ops check-config --config /etc/approv/deployment.json --readiness
.venv/bin/python -m approv.ops serve --config /etc/approv/deployment.json
```

On Windows use `.venv\Scripts\python.exe`. Startup does not generate keys or migrate
storage. Run administration under the service's filesystem identity. Never initialize
a new empty file to recover a missing production database; follow restore instead.

`Dockerfile.pilot` and `compose.pilot.yaml` provide a non-root, read-only application
image with explicit configuration, secret and persistent-state mounts. Build and run
only after provisioning is approved. Set `APPROV_CONFIG_DIR`, `APPROV_SECRET_DIR` and
`APPROV_STATE_DIR` to existing directories; no secret values go in these variables.
UID/GID 10001 must own the state directory and be able to read the restricted mounts.
Keep encrypted local key files in the secret mount. Configure workload identity
separately for KMS. A container image should be retained by digest for rollback.

```sh
docker compose -f compose.pilot.yaml build
docker compose -f compose.pilot.yaml run --rm approv migrate --store /var/lib/approv/receipts.sqlite3
docker compose -f compose.pilot.yaml run --rm approv check-config --readiness
docker compose -f compose.pilot.yaml up -d
```

The container healthcheck checks liveness only. Configure ingress readiness separately;
Docker reporting “healthy” is not permission to admit merchant verification traffic.

## Health and operational measurements

| Endpoint | Authentication | Meaning |
|---|---|---|
| `GET /livez` and legacy `/v1/health` | None | Process answers HTTP; dependency health is not implied |
| `GET /readyz` | Merchant bearer token | Committed store write, signing challenge, configured reader callable, and authenticated parseable extractor call for each category |
| `GET /ops/metrics` | Merchant bearer token | Rolling p50/p95, sample count, outcomes, tokens and cost estimates |
| `GET /metrics` | Merchant bearer token | Prometheus cumulative latency histogram and counters |
| `GET /v1/keys` | None | Pinned public-key publication, including historical keys |

Readiness is cached for the configured TTL, default 60 seconds. It is a real synthetic
extraction call per category, not merely a DNS/TCP check, and consumes tokens. Its
token counts and costs are labelled `readiness`, separate from `verification`.
No synthetic receipt is created: writability uses a separate operational pulse row.
A recent green readiness result does not override a subsequent request failure.
Scrape readiness at a controlled rate on the private operations network.

Stdout emits JSON `extraction` and `verification` events joined by a generated
operation ID, also returned in `X-Approv-Operation-ID`. Events include elapsed time,
stage, outcome, extractor calls, provider-reported input/output tokens and an estimated
USD amount at the configured prices. Missing provider usage is `null` and increments
an unknown-usage counter; it is never presented as a free model call. Cached input
tokens use the separately configured cache price. A failed parse still retains its
reported usage. A transport failure's unknown bill requires invoice reconciliation.
Events exclude request text, snapshots, raw provider output, credentials and merchant
identifiers. Disable ingress body/authorization logging too.

Four pilot measurements: **p50 verification latency, p95 verification latency,
tokens per extractor call, estimated USD per verification**. The JSON percentiles
use nearest rank over the last `metrics_window` attempts, with an explicit denominator.
They cover admitted verification work through the durable outcome, including request
reading, queuing, extraction and signing/storage, but exclude network transit and
response delivery. Retries and failures are identified in events. Structured-only
calls use zero model tokens. There is no aggregation with `mark` or `gate`.

Prometheus's histogram can aggregate time windows; the local rolling quantiles cannot
be averaged across processes. For p95, use:

```promql
histogram_quantile(0.95, sum by (le) (rate(approv_verification_seconds_bucket[5m])))
```

Use 0.50 for p50. Keep a log/metrics collector outside the application host: local
counters reset on restart and stdout is not a durable receipt store. Watch failure
and unknown-usage counters alongside the four measures. Set latency, failure-rate,
disk-space and backup-age alert thresholds from the pilot agreement, not invented
SLOs. The existing extractor transport still has its fixed 45-second socket timeout;
this task instruments it without changing the extractor. `comparison_budget_seconds`
optionally supplies the existing surface's computation budget; `null` means no budget
has been agreed. Exceeding it yields a retained `budget_exceeded` record. It does not
interrupt the network request and does not include signing, storage or network transit.
The full verification latency is measured separately. There is no automatic bypass
or invented end-to-end deadline. Incomplete records and their distinct completion
codes are counted even though their HTTP response is 200; issuing no trustworthy
record because storage or signing failed remains a 503 operational event.

## Forward migrations, backup and restore

Store v1 retains its signed JSON byte-for-byte. V2 adds the deployment/submission
bindings, migration history and a separate writable readiness row. DDL and version
advancement run in one `BEGIN IMMEDIATE` transaction; a failed migration rolls back.
Unknown newer versions are rejected. There are no down migrations and no automatic
receipt rewrites. The receipt, checkpoint, key, identity, deployment, submission and
migration-history tables reject SQL updates, deletes and replacement inserts.

Before upgrading an existing v1 store: stop/drain writers, retain its latest published
keys and independently held checkpoint, and take a SQLite online-API snapshot of
the old database to a **new** file. For example, under the service identity:

```sh
python -c "import sqlite3; open('/backup/before-v2.sqlite3','xb').close(); s=sqlite3.connect('file:/var/lib/approv/receipts.sqlite3?mode=ro',uri=True); d=sqlite3.connect('/backup/before-v2.sqlite3'); s.backup(d); d.close(); s.close()"
python -m approv.ops migrate --store /var/lib/approv/receipts.sqlite3
python -m approv.ops audit --store /var/lib/approv/receipts.sqlite3 --keys /retained/public-keys.json --checkpoint /retained/checkpoint.json
```

The normal backup CLI requires v2. It uses SQLite's online backup API, which captures
committed WAL data consistently while a writer runs. Do not copy only the live main
`.sqlite3` file. [SQLite backup documentation](https://sqlite.org/backup.html).

```sh
python -m approv.ops backup --store /var/lib/approv/receipts.sqlite3 --keys /retained/public-keys.json --destination /backup/pilot-20260913T120000Z
```

Each new backup directory contains `receipts.sqlite3`, `receipts.json`,
`public-keys.json`, `checkpoint.json` and a `COMPLETE.json` marker written last.
An interrupted backup lacks a valid completion marker and must not be used. The JSON
export includes the retained deployment manifests and submission bindings as well
as the original receipts. Backup operations check SQLite integrity, foreign keys,
every receipt/checkpoint signature, the chain and manifest bindings. They reject
keys absent from the independently supplied publication.

Schedule backups and copy **completed** bundles to encrypted storage in a separate
failure and administration domain. Independently retain the exported checkpoint and
public-key publication there; neither is independently trusted merely because it is
inside the backup. Keep configuration/schema release assets and local encrypted keys
and their recovery secret separately recoverable. KMS private keys are never in a
database backup. The founder chooses retention, recovery point and recovery time
targets. A backup every N minutes leaves up to N minutes of receipt loss after total
disk failure. For zero loss of acknowledged receipts, replication/external retention
must be designed before promising that guarantee; SQLite alone cannot supply it.

Restore drill, then the same procedure during an incident:

1. Stop writers and preserve the damaged database with its WAL/SHM sidecars for review.
2. Retrieve a completed backup, independently retained public keys and the matching
   checkpoint. An anchor newer than the backup fails; do not silently downgrade the
   trusted anchor to conceal lost receipts.
3. Restore to a new path. The CLI refuses an existing target or SQLite sidecars:

   ```sh
   python -m approv.ops restore --source /recovery/pilot-20260913T120000Z --destination /var/lib/approv/restored.sqlite3 --keys /independent/public-keys.json --checkpoint /independent/checkpoint.json
   python -I scripts/verify_receipt.py /recovery/pilot-20260913T120000Z/receipts.json --keys /independent/public-keys.json --checkpoint /independent/checkpoint.json
   ```

4. Audit the restored store, point reviewed deployment configuration at the new file,
   start, pass readiness and retrieve/retry a known order-line receipt. Its original
   signature, timestamp and historical key ID must survive. Restore tests include a
   stranger's isolated verifier across rotation and backup recovery.
5. Reopen merchant traffic only after reconciling the recovery point with acknowledged
   orders. Preserve the old file; restoration never deletes or updates its receipts.

Application rollback means selecting a release that understands the current store
version. Do not run the pre-v2 writer against a v2 database or roll back `user_version`.
If recovery from the pre-migration v1 snapshot is necessary, copy it to a new target,
run the forward migration there, and audit against the independent v1 checkpoint
before starting a compatible application.

The standalone verifier still needs only Python, `cryptography`, the script, exported
JSON and published public keys. It imports no Approv code. A signature proves the
record's contents were signed; the timestamp is Approv's own claim. Independently
retained checkpoints detect rewriting/truncation relative to their recorded heads,
but neither a local database nor a signature supplies an independent trusted clock
or proof of physical fulfilment. Preserve receipts/checkpoints outside the signing
host's control as they are issued if disputes require stronger timing evidence.

## Verification before a release

```sh
python -m pip install pytest httpx fastapi
python -m pytest tests approv/schema/tests approv/ops/tests -q
python -m pip check
```

The ops tests live under their owned module so no shared test files need editing.
The explicit command includes them without changing `pyproject.toml`. Tests exercise
real local HTTP extraction, boot the service as a subprocess, verify KMS-compatible
signatures offline, and restore receipts spanning rotation. Live AWS latency, cloud
permissions, disk durability and the merchant's extractor/schema combination must
be checked on the provisioned pilot; local stubs cannot establish those properties.
