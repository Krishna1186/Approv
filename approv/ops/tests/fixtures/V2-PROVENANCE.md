These are synthetic catalogue/order comparisons, not merchant/customer data.

`v2-receipts.sql` was produced on 2026-09-14 by running the actual Approv release
`9484f81` in an isolated temporary checkout. Its unchanged `verify_order` produced
24 structured apparel comparisons (allow, confirm and refuse); its unchanged v2
`ReceiptStore.commit_verification` signed and retained them with three independently
generated Ed25519 keys, rotating every eight receipts. The SQL is SQLite `iterdump()`
plus `PRAGMA user_version=2`; it contains the exact receipt/checkpoint JSON strings,
submission responses, request hashes, deployment manifest and append-only guards.

The public-key publication and final checkpoint were exported by that same release.
No private key was saved. The migration test recreates this frozen database without
Git, any old Approv code, signing keys or a network connection. It checks byte-preserving
migration and verifies the whole chain and every individual receipt in isolated
subprocesses using only the standalone verifier and published public keys.
