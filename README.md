# Approv

The dispute artifact for agent-authorised transactions. A stated request and a product go
in; per-attribute findings, one decision (allow/confirm/refuse) and a signed, hash-chained
record come out. The record answers one question when a refund is demanded — did the
merchant deliver what was asked for? No model in the decision path.

```powershell
python -m pytest -q -p no:cacheprovider
python scripts/demo_receipt.py --out output/demo          # request -> decision -> receipt
python scripts/verify_receipt.py output/demo/receipts.json --key (Get-Content output/demo/public_key.txt)
python scripts/score_gate.py --pack PACK --constraints WORK/constraints.json
```

`CLAUDE.md` is the contract. `progress.md` is what is measured and what is not — read it
before quoting any number. `docs/decisions/README.md` indexes the decision records.

No underwriting, priced guarantee, live payment or certification is implemented.
