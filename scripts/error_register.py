"""Count what Approv said, how often, and what happened next.

Approv is meant to improve from outcomes, and that is impossible while the failure modes
are anecdotes. This reads a completed forked study and reports frequencies for both
directions: which findings fire, and which of them actually changed an outcome. It
computes nothing new — it only counts what the run already recorded.
"""
import argparse, json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load(work):
    work = Path(work)
    read = lambda name: json.loads((work / name).read_text(encoding="utf-8-sig"))
    scored = read("scored.json")
    reports = {x["case_id"]: x["approv_report"] for x in read("stage2-approv.json")}
    constraints = read("constraints.json")
    return scored, reports, constraints, {arm: read("answers-%s.json" % arm)
                                          for arm in ("baseline", "blind", "approv")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True)
    args = parser.parse_args()
    scored, reports, constraints, answers = load(args.work)
    rows = scored["rows"]; family = scored["family"]
    cases = list(rows["baseline"])

    verdicts = Counter(); attributes = Counter(); extracted = Counter()
    for cid in cases:
        for line in reports.get(cid, "").splitlines():
            head = line.split(":")[0].split()
            if len(head) == 2: verdicts[head[0]] += 1; attributes[(head[0], head[1])] += 1
    for cid, record in constraints.items():
        for c in record["constraints"]: extracted[c["attribute"]] += 1

    print("REQUEST EXTRACTION — what Approv understood the shopper to want")
    for name, n in extracted.most_common():
        print("   %-14s %3d requests (%.0f%%)" % (name, n, 100 * n / max(len(constraints), 1)))
    print("\nFINDINGS EMITTED — %d lines across %d cases" % (sum(verdicts.values()), len(cases)))
    for verdict, n in verdicts.most_common():
        print("   %-11s %3d" % (verdict, n))
        for (v, attribute), m in attributes.most_common():
            if v == verdict: print("       %-12s %3d" % (attribute, m))

    print("\nDETECTION — the report against the truth about the agent's pick")
    flagged = {c: "MISMATCH" in reports.get(c, "") for c in cases}
    grid = Counter((rows["baseline"][c], flagged[c]) for c in cases)
    print("   wrong pick, flagged      %3d   true catch" % grid[(False, True)])
    print("   wrong pick, reported ok  %3d   FALSE CLEAR" % grid[(False, False)])
    print("   right pick, flagged      %3d   false alarm" % grid[(True, True)])
    print("   right pick, reported ok  %3d" % grid[(True, False)])

    print("\nOUTCOMES — what each arm did with the agent's mistakes")
    wrong = [c for c in cases if not rows["baseline"][c]]
    right = [c for c in cases if rows["baseline"][c]]
    for arm in ("blind", "approv"):
        if arm not in rows: continue
        print("   %-7s fixed %2d/%2d mistakes, broke %2d/%2d successes, final %2d/%2d = %.1f%%" % (
            arm, sum(rows[arm][c] for c in wrong), len(wrong),
            sum(1 for c in right if not rows[arm][c]), len(right),
            sum(rows[arm].values()), len(cases), 100 * sum(rows[arm].values()) / len(cases)))

    print("\nBY REQUEST FAMILY — where the remaining errors are")
    print("   %-12s %8s %8s %8s" % ("family", "baseline", "blind", "approv"))
    for fam in sorted(set(family[c] for c in cases)):
        members = [c for c in cases if family[c] == fam]
        cells = ["%d/%d" % (sum(rows[a][c] for c in members), len(members))
                 for a in ("baseline", "blind", "approv") if a in rows]
        print("   %-12s %8s %8s %8s" % (fam, *cells))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
