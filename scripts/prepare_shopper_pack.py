"""Freeze the v2 shopper pack: same DR 0018 answer-key method, ten sentence shapes.

    python scripts/prepare_shopper_pack.py --output data/cache/shopping-study/shopper-v2.json

shopify_shopper_pack_v2 (approv/harness/casepacks.py) fixes the spec — colour, size,
availability, an optional price cap — before it writes a sentence, exactly like the v1
pack it sits beside. What's new is sentence shape: correction, negation, question,
indirect and hedged phrasing alongside the original plain/budget/casual/terse/impossible,
plus an off-schema distractor clause drawn independently of shape. The answer key does
not change; run scripts/score_extraction.py against this pack's constraints the same way
as against shopper.json.

Does not overwrite an existing output file, and does not touch shopper.json — that pack's
published numbers (progress.md) stay reproducible against exactly what produced them.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from approv.harness.casepacks import shopify_shopper_pack_v2, write_pack

# The raw catalogue's own product timestamps cluster on this date; captured_at is
# provenance metadata carried into the frozen inventory, not an input to any score.
CAPTURED_AT = datetime(2026, 9, 10, tzinfo=timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', default='data/cache/shopify-raw.json')
    parser.add_argument('--output', required=True)
    parser.add_argument('--cases', type=int, default=120)
    parser.add_argument('--catalogue', type=int, default=25000)
    parser.add_argument('--seed', type=int, default=20260913)
    args = parser.parse_args()

    out = Path(args.output)
    if out.exists():
        raise FileExistsError('refusing to overwrite an existing pack: %s' % out)

    raw = json.loads(Path(args.source).read_text(encoding='utf-8'))
    pack = shopify_shopper_pack_v2(raw, CAPTURED_AT, catalogue=args.catalogue,
                                   cases=args.cases, seed=args.seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_pack(out, pack)

    families, splits = {}, {}
    for task in pack['tasks']:
        families[task['family']] = families.get(task['family'], 0) + 1
        splits[task['split']] = splits.get(task['split'], 0) + 1
    print(json.dumps({'output': str(out), 'tasks': len(pack['tasks']),
                      'variants': len(pack['inventory']['products']),
                      'splits': splits, 'families': families}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
