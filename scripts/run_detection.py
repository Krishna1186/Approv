"""Measure whether Approv's findings separate human-exact from non-exact candidates.

One model interpretation per case, then deterministic checks over every judged candidate.
That yields candidate-level observations rather than one outcome per session, so a real
interval is affordable at a fraction of an end-to-end study's tokens.

This measures detection, not agent behaviour. It says whether the findings carry signal;
it does not say that an agent acts on them. Labels are original ESCI human judgements and
are read only after the findings are computed.
"""
import argparse, json, sys, time
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from approv.harness.adapters import AdapterError
from approv.harness.intent import RequestInterpreter
from approv.harness.shopping import Inventory, ShoppingCase, canonical, digest
from approv.algebra.runner import check_constraints
from approv.harness.coverage import wilson
from approv.types.core import Support
from scripts.run_study import get_key


def ranked(products, blobs, query, k):
    tokens = query.casefold().split()
    order = sorted(products, key=lambda p: (-sum(t in blobs[p.id] for t in tokens), p.id))
    return order[:k]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', required=True); parser.add_argument('--output', required=True)
    parser.add_argument('--split', choices=['dev', 'heldout'], required=True)
    parser.add_argument('--model', default='openai/gpt-oss-20b')
    parser.add_argument('--version', choices=['v1', 'v2', 'v3', 'v4'], default='v4')
    parser.add_argument('--limit', type=int, default=0); parser.add_argument('--top', type=int, default=20)
    parser.add_argument('--interval', type=float, default=2)
    args = parser.parse_args()

    pack = json.loads(Path(args.pack).read_text(encoding='utf-8'))
    if digest({k: v for k, v in pack.items() if k != 'content_hash'}) != pack['content_hash']:
        raise ValueError('pack hash mismatch')
    inventory = Inventory.model_validate(pack['inventory'])
    schema = inventory.category_schema
    products = list(inventory.products)
    blobs = {p.id: (p.title + ' ' + ' '.join(p.details.values()) + ' '
                    + ' '.join(e.raw_text or str(e.value) for e in p.evidence)).casefold() for p in products}
    by_id = {p.id: p for p in products}
    tasks = [t for t in pack['tasks'] if t['split'] == args.split]
    if args.limit: tasks = tasks[:args.limit]

    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    from approv.harness.casepacks import published_vocabulary
    vocabulary = published_vocabulary(inventory)
    interpreter = RequestInterpreter('https://api.groq.com/openai/v1', args.model, get_key(),
                                     args.version, vocabulary=vocabulary)
    for task in tasks:
        file = output / (task['case']['id'] + '.json')
        if file.exists(): continue
        case = ShoppingCase.model_validate(task['case'])
        delays = []
        for attempt in range(4):
            time.sleep(args.interval if not delays else delays[-1])
            try:
                case, interpretation = interpreter(case, schema)
                interpretation['rate_limit_retry_delays'] = delays
                break
            except AdapterError as e:
                wait = e.metadata.get('retry_after_seconds', 0)
                if e.code != 'http_429' or not 0 < wait <= 60 or attempt == 3:
                    print(canonical({'blocked': e.code, 'case': case.id, 'retry': e.metadata}), flush=True)
                    return 2
                delays.append(wait + 1)
        rows = []
        for product in ranked(products, blobs, task['case']['request'], args.top):
            findings = check_constraints(case.constraints, by_id[product.id].evidence, schema)
            rows.append({'product_id': product.id,
                'flagged': any(f.support is Support.VIOLATED for f in findings),
                'unstated': any(f.support is Support.UNSTATED for f in findings),
                'supports': {f.attribute: f.support.value for f in findings},
                'label': task['gold']['labels'].get(product.id)})
        record = {'case_id': case.id, 'request': case.request, 'model': args.model,
                  'version': args.version, 'top': args.top,
                  'constraints': [c.model_dump(mode='json') for c in case.constraints],
                  'interpretation': interpretation, 'candidates': rows}
        file.write_text(canonical(record) + '\n', encoding='utf-8')
        print(canonical({'case': case.id, 'status': interpretation['status'],
                         'constraints': len(case.constraints),
                         'flagged': sum(r['flagged'] for r in rows)}), flush=True)
    return 0


def report(folder):
    rows = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(Path(folder).glob('*.json'))]
    counts = Counter(); status = Counter()
    for record in rows:
        status[record['interpretation']['status']] += 1
        for candidate in record['candidates']:
            if candidate['label'] is None: continue
            exact = candidate['label'] == 'E'
            counts[('exact' if exact else 'non_exact', 'flagged' if candidate['flagged'] else 'clean')] += 1
    tp = counts[('non_exact', 'flagged')]; fn = counts[('non_exact', 'clean')]
    fp = counts[('exact', 'flagged')]; tn = counts[('exact', 'clean')]
    print('cases %d   interpretation status %s' % (len(rows), dict(status)))
    print('judged candidates: non-exact %d, exact %d' % (tp + fn, fp + tn))
    print('  flag rate on NON-EXACT (true):  %d/%d = %.1f%%  95%% CI %s' % (
        tp, tp + fn, 100 * tp / max(tp + fn, 1), ['%.1f%%' % (100 * x) for x in wilson(tp, tp + fn)]))
    print('  flag rate on EXACT   (false):  %d/%d = %.1f%%  95%% CI %s' % (
        fp, fp + tn, 100 * fp / max(fp + tn, 1), ['%.1f%%' % (100 * x) for x in wilson(fp, fp + tn)]))
    if fp + tp: print('  precision of a flag: %.1f%%' % (100 * tp / (tp + fp)))
    return 0


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == 'report': raise SystemExit(report(sys.argv[2]))
    raise SystemExit(main())
