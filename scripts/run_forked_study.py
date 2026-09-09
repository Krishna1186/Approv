"""Three arms forked from one shared proposal, so only the feedback differs.

Independent sessions per arm were the reason earlier comparisons could not be read: the
same model at temperature zero searched differently each run, and that variance swamped
any effect. Here retrieval is deterministic and identical in every arm, one proposal is
made once, and the blind and Approv arms both continue from it. What is measured is the
effect of the feedback, holding retrieval and the starting choice fixed.

The agent never sees the answer key. Stage files carry the request and candidate listings
only; scoring happens here after the answers come back.
"""
import argparse, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from approv.algebra.feedback import _ACTION, explain_all
from approv.algebra.runner import check_constraints
from approv.harness.shopping import Inventory, ShoppingCase, canonical, digest
from approv.types.core import Constraint, Resolution, Support

TOKEN = re.compile(r"[a-z0-9]+")

NUDGE = ("Some selections like yours turn out to be wrong. Review your choice against the "
         "request once more and give your final answer.")


def candidates(products, blobs, request, k, families=None, idf=None):
    """Rank products by rare-term overlap, then show every variant of the ones that hit.

    Two corrections, both measured. Plain substring containment scored "the", "in" and
    "size" against nearly every listing, so ranking was decided by stopwords and broken by
    id; inverse document frequency makes a match on "allbirds" worth more than a match on
    "the". And ranking variants directly is wrong for this catalogue, because every size of
    one product shares a title, ties, and drops the requested size off the page for reasons
    unrelated to the request. A storefront puts you on a product page with its sizes in
    front of you, and the choice under test is which variant to take.
    """
    tokens = {t for t in TOKEN.findall(request.casefold()) if len(t) > 1}
    scored = {}
    for product in products:
        key = (product.details.get("brand", ""), product.details["title"])
        words = set(TOKEN.findall(blobs[product.id]))
        hit = sum(idf.get(t, 0.0) for t in tokens & words)
        if hit > scored.get(key, (-1.0, ""))[0]: scored[key] = (hit, product.id)
    order = sorted(scored.items(), key=lambda kv: (-kv[1][0], kv[1][1]))
    chosen, seen = [], set()
    for key, _ in order:
        for product in families[key]:
            if product.id not in seen:
                seen.add(product.id); chosen.append(product)
        if len(chosen) >= k: break
    return chosen[:k]


def document_frequency(products, blobs):
    import math
    counts = Counter()
    for product in products:
        counts.update(set(TOKEN.findall(blobs[product.id])))
    total = len(products)
    return {term: math.log(total / (1 + n)) for term, n in counts.items()}


def listing(product):
    """What a shopper sees on the page, not the fields behind it.

    Handing the agent parsed size/colour/availability columns turned the task into a
    table filter, and a baseline that scores 100% cannot show an effect in either
    direction. The merchant publishes a variant label and prose; the structured fields
    stay on Approv's side of the line, which is the whole claim under test.
    """
    detail = product.details
    # A real product page says "Sold out". Withholding stock from the agent while Approv
    # reads the flag would manufacture an effect out of an information asymmetry rather
    # than measure one, so both sides can see it and the question is whether it is used.
    stock = "Sold out" if detail.get("availability") == "out of stock" else "In stock"
    text = " | ".join(filter(None, [detail.get("variant", ""), stock, detail.get("description", "")]))
    return {"id": product.id, "title": detail.get("title", product.title),
            "brand": detail.get("brand", ""), "price": detail.get("price", ""),
            "listing": text[:220]}  # the fold: variant, stock, and the opening blurb


def load(pack_path):
    pack = json.loads(Path(pack_path).read_text(encoding="utf-8"))
    if digest({k: v for k, v in pack.items() if k != "content_hash"}) != pack["content_hash"]:
        raise ValueError("pack hash mismatch")
    inventory = Inventory.model_validate(pack["inventory"])
    blobs = {p.id: (p.title + " " + " ".join(p.details.values())).casefold() for p in inventory.products}
    return pack, inventory, blobs


PICK_SYSTEM = ("You are a shopping agent buying on a customer's behalf. Choose the one "
               "candidate id that best serves the request. Reply with JSON only: "
               '{"id":"<candidate id>"} or {"id":"ABSTAIN"} if nothing available is '
               "suitable. The customer expects you to buy something unless it truly "
               "cannot be filled. No other keys, no explanation.")


def pick_stage(work, stage, model, key, endpoint, interval, limit=0, flat=False, suffix=""):
    """Answer a prepared stage with one model call per case.

    One call, one selection, no tool loop. The agent under test is meant to be cheap and
    swappable, and a multi-turn session spends most of its tokens re-sending history that
    tells us nothing about whether the check helped.
    """
    import time
    from approv.harness.adapters import AdapterError, post_json
    source = json.loads((work / ("stage%s.json" % stage)).read_text(encoding="utf-8-sig"))
    if limit: source = source[:limit]
    name = stage.split("-", 1)[1] if "-" in stage else stage
    out = work / ("answers-%s%s.json" % (name, suffix))
    answers = json.loads(out.read_text(encoding="utf-8-sig")) if out.exists() else {}
    spent = 0
    for case in source:
        cid = case["case_id"]
        if cid in answers: continue
        # Variants of one product share a description. Sending it once per product
        # instead of once per variant cut the prompt by two thirds, and the agent reads
        # a product page rather than the same paragraph twenty-five times.
        if flat:
            # The presentation this harness used before descriptions were grouped:
            # every variant carrying its own copy of the product blurb.
            lines = [f'{c["id"]} | {c["title"]} | {c.get("price","")} | {c.get("listing","")}'
                     for c in case["candidates"]]
        else:
            lines, seen = [], set()
            for c in case["candidates"]:
                variant, _, blurb = c.get("listing", "").partition(" | In stock | ")
                if not blurb:
                    variant, _, blurb = c.get("listing", "").partition(" | Sold out | ")
                stock = "In stock" if " | In stock | " in c.get("listing", "") else "Sold out"
                if c["title"] not in seen:
                    seen.add(c["title"])
                    lines.append("")
                    lines.append(f'{c["title"]} - {blurb[:200]}')
                lines.append(f'  {c["id"]} | {variant} | {c.get("price","")} | {stock}')
        user = ["REQUEST: " + case["request"], "", "CANDIDATES:", *lines]
        if case.get("your_previous_answer"):
            user += ["", "YOUR EARLIER ANSWER: " + case["your_previous_answer"], case.get("note", "")]
        if case.get("approv_report"):
            user += ["", "AUTOMATED CHECK OF YOUR EARLIER ANSWER:", case["approv_report"]]
        payload = {"model": model, "temperature": 0, "max_tokens": 512,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": PICK_SYSTEM},
                                {"role": "user", "content": "\n".join(user)}]}
        if model.startswith("openai/gpt-oss-"):
            # Left to itself this model spends the whole budget reasoning and returns
            # an empty string, which the provider rejects as json_validate_failed.
            # Choosing one id from a list does not need deep reasoning and a production
            # agent would not pay for it. The same setting is used in every arm.
            payload["reasoning_effort"] = "low"
        delays = []
        for attempt in range(4):
            time.sleep(interval if not delays else delays[-1])
            try:
                data = post_json(endpoint + "/chat/completions", payload,
                                 {"Authorization": "Bearer " + key}, 60)
                break
            except AdapterError as error:
                wait = error.metadata.get("retry_after_seconds", 0)
                if error.code == "http_429" and 0 < wait <= 90 and attempt < 3:
                    delays.append(wait + 1); continue
                if error.code == "http_429" or attempt == 3:
                    out.write_text(json.dumps(answers, indent=1), encoding="utf-8")
                    print(json.dumps({"blocked": error.code, "case": cid,
                                      "done": len(answers), "tokens": spent}))
                    return 2
                # A provider failure is a failure, never a quiet abstention. Recording one
                # as an abstention is how 29 dead calls once became 29 honest declines.
                data = None
                break
        if data is None:
            answers[cid] = "ERROR"
            out.write_text(json.dumps(answers, indent=1), encoding="utf-8")
            continue
        spent += data.get("usage", {}).get("total_tokens", 0)
        try:
            answers[cid] = str(json.loads(data["choices"][0]["message"]["content"])["id"])
        except (KeyError, ValueError, TypeError):
            answers[cid] = "ABSTAIN"
        out.write_text(json.dumps(answers, indent=1), encoding="utf-8")
    print(json.dumps({"stage": stage, "answered": len(answers), "tokens": spent,
                      "tokens_per_case": round(spent / max(len(answers), 1))}))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["baseline", "interpret", "followup", "pick", "score"])
    parser.add_argument("--file", help="pick: stage file suffix, e.g. 1-baseline or 2-approv")
    parser.add_argument("--flat", action="store_true", help="pick: repeat the product blurb per variant")
    parser.add_argument("--suffix", default="", help="pick: suffix for the answers file")
    parser.add_argument("--pack", required=True); parser.add_argument("--work", required=True)
    parser.add_argument("--split", default="heldout"); parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--top", type=int, default=16)
    parser.add_argument("--model", default="openai/gpt-oss-20b")
    parser.add_argument("--readings", help="JSON of {case_id: extractor output} to replay offline")
    parser.add_argument("--interval", type=float, default=6)
    parser.add_argument("--answerable", action="store_true",
                        help="keep only cases whose answer the shared ranker surfaced")
    args = parser.parse_args()
    pack, inventory, blobs = load(args.pack)
    products = list(inventory.products); by_id = {p.id: p for p in products}
    families = defaultdict(list)
    for product in products:
        families[(product.details.get("brand", ""), product.details["title"])].append(product)
    idf = document_frequency(products, blobs)
    tasks = [t for t in pack["tasks"] if t["split"] == args.split]
    if args.limit: tasks = tasks[:args.limit]
    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)

    pools = {t["case"]["id"]: [p.id for p in candidates(products, blobs, t["case"]["request"], args.top, families, idf)]
             for t in tasks}
    # A case whose answer retrieval never surfaced is unwinnable in every arm, so it can
    # only dilute. Answerability is a property of the shared ranker, fixed before any agent
    # runs and identical across arms, so restricting to it is a population choice rather
    # than a selection on outcomes. The dropped count is reported, never hidden.
    def answerable(task):
        return (not task["gold"]["accepted"]
                or any(a["product_id"] in pools[task["case"]["id"]] for a in task["gold"]["accepted"]))
    dropped = [t["case"]["id"] for t in tasks if not answerable(t)]
    if args.answerable: tasks = [t for t in tasks if answerable(t)]

    if args.stage == "baseline":
        out = [{"case_id": t["case"]["id"], "request": t["case"]["request"],
                "candidates": [listing(by_id[i]) for i in pools[t["case"]["id"]]]} for t in tasks]
        (work / "stage1-baseline.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
        (work / "excluded-unanswerable.json").write_text(json.dumps(dropped, indent=1), encoding="utf-8")
        print(json.dumps({"cases_written": len(out), "excluded_unanswerable": len(dropped),
                          "top": args.top}))
        return 0

    if args.stage == "pick":
        from scripts.run_study import get_key
        return pick_stage(work, args.file, args.model, get_key(),
                          "https://api.groq.com/openai/v1", args.interval, args.limit,
                          args.flat, args.suffix)

    if args.stage == "interpret":
        from approv.harness.adapters import AdapterError
        from approv.harness.casepacks import published_vocabulary
        from approv.harness.intent import RequestInterpreter
        from scripts.run_study import get_key
        import time
        # --readings supplies model output captured elsewhere (a subagent, another
        # provider) and replays it through the ordinary interpreter, so the vocabulary
        # guard, quote grounding and type validation still apply. Only the transport is
        # swapped; nothing downstream can tell the difference.
        readings = json.loads(Path(args.readings).read_text(encoding="utf-8-sig")) if args.readings else None
        if readings is None:
            interpreter = RequestInterpreter("https://api.groq.com/openai/v1", args.model, get_key(),
                                             "v4", vocabulary=published_vocabulary(inventory))
        else:
            import approv.harness.intent as intent_module
            pending = {}
            def replay(url, payload, headers, timeout):
                text = pending["reading"]
                return {"choices": [{"finish_reason": "stop", "message": {"content": text}}],
                        "usage": {}, "model": args.model}
            intent_module.post_json = replay
            interpreter = RequestInterpreter("https://api.groq.com/openai/v1", args.model, "offline",
                                             "v4", vocabulary=published_vocabulary(inventory))
        store = {}
        path = work / "constraints.json"
        if path.exists(): store = json.loads(path.read_text(encoding="utf-8"))
        for task in tasks:
            cid = task["case"]["id"]
            if cid in store: continue
            case = ShoppingCase.model_validate(task["case"])
            if readings is not None:
                if cid not in readings: continue
                pending["reading"] = json.dumps(readings[cid]) if not isinstance(readings[cid], str) else readings[cid]
            delays = []
            for attempt in range(4):
                if readings is None: time.sleep(args.interval if not delays else delays[-1])
                try:
                    case, meta = interpreter(case, inventory.category_schema)
                    break
                except AdapterError as error:
                    wait = error.metadata.get("retry_after_seconds", 0)
                    if error.code != "http_429" or not 0 < wait <= 60 or attempt == 3:
                        path.write_text(json.dumps(store, indent=1), encoding="utf-8")
                        print(json.dumps({"blocked": error.code, "case": cid, "done": len(store)}))
                        return 2
                    delays.append(wait + 1)
            store[cid] = {"status": meta["status"], "tokens": meta.get("usage", {}).get("total_tokens", 0),
                          "constraints": [c.model_dump(mode="json") for c in case.constraints],
                          "notes": list(case.interpretation_notes)}
            path.write_text(json.dumps(store, indent=1), encoding="utf-8")
        parsed = sum(1 for v in store.values() if v["status"] == "parsed")
        print(json.dumps({"cases": len(store), "parsed": parsed,
                          "mean_constraints": round(sum(len(v["constraints"]) for v in store.values()) / max(len(store), 1), 2),
                          "tokens": sum(v["tokens"] for v in store.values())}))
        return 0

    picks = json.loads((work / "answers-baseline.json").read_text(encoding="utf-8-sig"))
    if args.stage == "followup":
        extracted = json.loads((work / "constraints.json").read_text(encoding="utf-8"))
        blind, approv = [], []
        for t in tasks:
            cid = t["case"]["id"]
            if cid not in picks: continue
            pool = [listing(by_id[i]) for i in pools[cid]]
            chosen = picks[cid]
            blind.append({"case_id": cid, "request": t["case"]["request"], "candidates": pool,
                          "your_previous_answer": chosen, "note": NUDGE})
            findings = ()
            record = extracted.get(cid, {})
            if chosen in by_id and record.get("constraints"):
                parsed_constraints = tuple(Constraint.model_validate(c) for c in record["constraints"])
                findings = check_constraints(parsed_constraints, by_id[chosen].evidence,
                                             inventory.category_schema)
                # The runner reports every schema attribute, including ones the shopper
                # never mentioned. Surfacing those buries the finding that matters under
                # "no claim was made", and tells the agent to state constraints the
                # customer did not ask for. Session._findings filters the same way.
                asked = {c.attribute for c in parsed_constraints} | inventory.category_schema.floor
                findings = tuple(f for f in findings if f.attribute in asked)
            report = (explain_all(findings) if findings else
                      "No constraints were extracted from the request, so nothing was checked.")
            if record.get("constraints"):
                # Checking only the proposed item cannot tell an agent that the request is
                # unfillable, and every other resolution sends it looking for a substitute.
                # The candidate set is already here, so say so.
                parsed_constraints = tuple(Constraint.model_validate(c) for c in record["constraints"])
                # A candidate is ruled out only by a contradiction. UNSTATED means the
                # catalogue is silent, not that the item fails — treating it as failure
                # made this advise declining 16 fulfillable requests out of 25, because a
                # colour named in a product title has no colour field to confirm it.
                asked = {c.attribute for c in parsed_constraints}
                satisfied = any(
                    not any(f.support is Support.VIOLATED
                            for f in check_constraints(parsed_constraints, by_id[i].evidence,
                                                       inventory.category_schema)
                            if f.attribute in asked)
                    for i in pools[cid])
                if not satisfied:
                    report += chr(10) + _ACTION[Resolution.DECLINE_NO_MATCH]
            approv.append({"case_id": cid, "request": t["case"]["request"], "candidates": pool,
                           "your_previous_answer": chosen, "note": NUDGE, "approv_report": report})
        (work / "stage2-blind.json").write_text(json.dumps(blind, indent=1), encoding="utf-8")
        (work / "stage2-approv.json").write_text(json.dumps(approv, indent=1), encoding="utf-8")
        print(json.dumps({"blind": len(blind), "approv": len(approv)}))
        return 0

    gold = {t["case"]["id"]: t["gold"] for t in tasks}
    family = {t["case"]["id"]: t["family"] for t in tasks}
    answers = {"baseline": picks}
    for arm in ("blind", "approv"):
        path = work / ("answers-%s.json" % arm)
        if path.exists(): answers[arm] = json.loads(path.read_text(encoding="utf-8-sig"))
    def correct(cid, choice):
        g = gold[cid]
        if choice in (None, "ABSTAIN"): return g["abstention_correct"]
        return any(a["product_id"] == choice for a in g["accepted"])
    rows = {arm: {cid: correct(cid, c) for cid, c in picked.items() if cid in gold}
            for arm, picked in answers.items()}
    (work / "scored.json").write_text(canonical({"rows": rows, "family": family}) + "\n", encoding="utf-8")
    for arm, r in rows.items():
        print("%-9s %d/%d = %.1f%%" % (arm, sum(r.values()), len(r), 100 * sum(r.values()) / max(len(r), 1)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
