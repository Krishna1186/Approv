"""Shopping experiments: public inventory, human cases, any traceable agent."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from approv.harness.adapters import ChatAgent, ToolChatAgent, CommandAgent, HttpAgent
from approv.harness.experiment import (
    Annotation, GoldSet, report, run_experiment, save_experiment, validate_cases, validate_gold,
)
from approv.harness.inventory import import_off
from approv.harness.shopping import Arm, Inventory, RunConfig, Session, ShoppingCase, canonical, digest
from approv.harness.storefront import Store, make_server


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as file:
        file.write(canonical(value) + "\n")


def load_inputs(args):
    inventory = Inventory.model_validate(read(args.inventory))
    cases = [ShoppingCase.model_validate(c) for c in read(args.cases)]
    validate_cases(cases)
    for case in cases:
        Session(inventory, case, Arm.BASELINE, RunConfig())
    return inventory, cases


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import-off", help="Import existing public JSON, no new fetch")
    imp.add_argument("source")
    imp.add_argument("--output", required=True)
    imp.add_argument("--captured-at", required=True, help="Frozen snapshot/export time with timezone; not a claim of catalogue freshness")
    schemas = sub.add_parser("schemas", help="Write authoring schemas, not generated evaluation data")
    schemas.add_argument("--directory", required=True)
    author = sub.add_parser("author", help="Interactively write one human case and its separate label")
    author.add_argument("--inventory", required=True)
    author.add_argument("--cases", required=True)
    author.add_argument("--gold", required=True)
    for name in ("validate", "run", "serve", "report"):
        command = sub.add_parser(name)
        command.add_argument("--inventory", required=True)
        command.add_argument("--cases", required=True)
        if name in ("validate", "report", "run"):
            command.add_argument("--gold")
        if name == "report":
            command.add_argument("--experiment", required=True)
            command.add_argument("--output", required=True)
        if name in ("run", "serve"):
            command.add_argument("--output", required=True)
            command.add_argument("--max-actions", type=int, default=12)
            command.add_argument("--review-rounds", type=int, default=1)
            command.add_argument("--surface", choices=("mark", "verify"), default="mark")
            command.add_argument("--seed", type=int, default=42)
        if name == "serve":
            command.add_argument("--port", type=int, default=8765)
            command.add_argument("--agent-name", required=True)
        if name == "run":
            command.add_argument("--transport", choices=("compatible", "compatible_tools", "gemini", "http", "command"), required=True)
            command.add_argument("--endpoint")
            command.add_argument("--model")
            command.add_argument("--api-key-env")
            command.add_argument("--command-json", help="JSON array of executable and arguments; no shell")
            command.add_argument("--max-tokens", type=int, default=1024)
            command.add_argument("--token-parameter", choices=("max_tokens", "max_completion_tokens"), default="max_tokens")
            command.add_argument("--temperature", type=float)
            command.add_argument("--timeout", type=float, default=45)
    args = parser.parse_args(argv)
    if args.command == "import-off":
        records = read(args.source)
        if isinstance(records, dict):
            records = records["products"]
        inventory, summary = import_off(records, datetime.fromisoformat(args.captured_at))
        write_new(args.output, inventory)
        print(canonical({**summary, "inventory_hash": digest(inventory)}))
        return 0
    if args.command == "schemas":
        folder = Path(args.directory)
        folder.mkdir(parents=True, exist_ok=True)
        for model in (Inventory, ShoppingCase, GoldSet):
            write_new(folder / (model.__name__ + ".schema.json"), model.model_json_schema())
        print("Schemas written. Requests and labels must be authored independently by a human.")
        return 0
    if args.command == "author":
        return author_case(args)
    inventory, cases = load_inputs(args)
    gold = GoldSet.model_validate(read(args.gold)) if getattr(args, "gold", None) else None
    if gold:
        validate_gold(gold, inventory, cases)
    if args.command == "validate":
        print(canonical({"inventory_hash": digest(inventory), "cases": len(cases),
            "case_hashes": {c.id: digest(c) for c in cases}, "human_labels": len(gold.annotations) if gold else 0}))
        return 0
    if args.command == "report":
        result = report(read(args.experiment), inventory, cases, gold)
        write_new(args.output, result)
        print(canonical(result))
        return 0
    config = RunConfig(max_actions=args.max_actions, review_rounds=args.review_rounds,
                       surface=args.surface, seed=args.seed)
    if Path(args.output).exists():
        raise FileExistsError(args.output)
    if args.command == "serve":
        server = make_server(Store(inventory, cases, config, Path(args.output), args.agent_name), args.port)
        print(f"Test storefront: http://127.0.0.1:{server.server_port}/", flush=True)
        print("Reset the external agent's context between tasks. Gold is never served.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if not 0 < args.timeout <= 60:
        raise ValueError("timeout must be in (0, 60]")
    if args.transport == "command":
        command = json.loads(args.command_json or "[]")
        if not isinstance(command, list) or not command or not all(isinstance(s, str) for s in command):
            raise ValueError("command-json must be a nonempty string array")
        factory = lambda: CommandAgent(command, args.timeout)
        metadata = {"transport": "command", "command_hash": digest(command), "timeout": args.timeout}
    elif args.transport == "http":
        factory = lambda: HttpAgent(args.endpoint or "", args.timeout)
        metadata = {"transport": "http", "endpoint": factory().endpoint, "timeout": args.timeout}
    else:
        key = os.environ.get(args.api_key_env, "") if args.api_key_env else ""
        if args.api_key_env and not key:
            raise ValueError("configured API key environment variable is empty")
        adapter = ToolChatAgent if args.transport == "compatible_tools" else ChatAgent
        factory = lambda: adapter(args.endpoint or "", args.model or "", key,
            provider="compatible" if args.transport == "compatible_tools" else args.transport, max_tokens=args.max_tokens, token_parameter=args.token_parameter,
            temperature=args.temperature, timeout=args.timeout)
        metadata = factory().manifest()
    # Validate adapter config before starting; then every arm gets a fresh instance.
    factory()
    def checkpoint(result):
        suffix = digest({"case": result["case_id"], "arm": result["binding"]["arm"]})[:16]
        write_new(args.output + ".session-" + suffix + ".json", result)
        print(f"{result['case_id']} {result['binding']['arm']}: {result['status']}", flush=True)
    experiment = run_experiment(inventory, cases, config, factory, agent_metadata=metadata, on_result=checkpoint)
    save_experiment(Path(args.output), experiment)
    summary = report(experiment, inventory, cases, gold)
    write_new(args.output + ".report.json", summary)
    print(canonical(summary))
    return 0


def author_case(args):
    if Path(args.cases).resolve() == Path(args.gold).resolve():
        raise ValueError("cases and gold must be separate files")
    inventory = Inventory.model_validate(read(args.inventory))
    # This interactive command records the human's answers verbatim; it never infers a label.
    if Path(args.cases).exists() != Path(args.gold).exists():
        raise ValueError("existing cases and gold must be supplied together")
    existing = [ShoppingCase.model_validate(c) for c in read(args.cases)] if Path(args.cases).exists() else []
    previous = GoldSet.model_validate(read(args.gold)) if Path(args.gold).exists() else None
    if previous:
        validate_gold(previous, inventory, existing)
    print("Inspect the frozen inventory before choosing acceptable outcomes. All answers are human-authored.")
    author = input("Your name/annotator ID: ").strip()
    case_id = input("Unique case ID: ").strip()
    request = input("Shopper request (verbatim): ").strip()
    cluster = input("Cluster ID (shared for related products/requests): ").strip()
    constraints = json.loads(input("Typed constraints JSON array (see ShoppingCase.schema.json): "))
    scope = input("Quantity scope [per_sale_unit/cart_total]: ").strip()
    requested_units = input("Required number of sale units (blank if unspecified): ").strip()
    case = ShoppingCase(id=case_id, request=request, constraints=constraints, author=author, cluster=cluster,
                        quantity_scope=scope, requested_units=int(requested_units) if requested_units else None)
    accepted = json.loads(input('Accepted outcomes JSON array [{"product_id":"...","units":1}], or []: '))
    abstention = input("Is abstaining correct? [yes/no]: ").strip().casefold()
    if abstention not in ("yes", "no"):
        raise ValueError("answer yes or no")
    notes = input("Evidence inspected and rationale: ").strip()
    annotation = Annotation(case_id=case.id, case_hash=digest(case), accepted=accepted,
        abstention_correct=abstention == "yes", annotator=author, evidence_notes=notes)
    cases = [*existing, case]
    validate_cases(cases)
    gold = GoldSet(inventory_hash=digest(inventory), provenance="Interactive human annotation",
        annotations=(*previous.annotations, annotation) if previous else (annotation,))
    validate_gold(gold, inventory, cases)
    # Validated additions only; retain originals alongside changes for review.
    for path, value in ((Path(args.cases), [c.model_dump(mode="json") for c in cases]), (Path(args.gold), gold)):
        if path.exists():
            backup = path.with_name(path.name + "." + digest(read(path))[:12] + ".bak")
            if not backup.exists():
                backup.write_bytes(path.read_bytes())
        path.write_text(canonical(value) + "\n", encoding="utf-8")
    print("Case and separate answer key saved. Keep the gold file outside the agent workspace.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        # Config/input errors are local; never print provider response bodies.
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(2)
