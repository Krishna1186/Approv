"""Explicit local administration. This CLI never provisions infrastructure."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

from approv.config import load_deployment
from approv.config.settings import ConfigError, SecretFile, read_json
from approv.receipts.backup import audit, backup, restore
from approv.receipts.chain import key_id_for
from approv.receipts.keys import KeyStore
from approv.receipts.store import ReceiptStore


def public_keys(path):
    publication = read_json(Path(path).read_bytes())
    if publication["format"] != "approv-public-keys-v1":
        raise ValueError("invalid publication")
    keys = publication["keys"]
    if any(key_id_for(value) != key for key, value in keys.items()):
        raise ValueError("invalid key fingerprint")
    return keys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("serve", "check-config"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path)
        command.add_argument("--namespace", choices=("production", "sandbox"), default="production")
        if name == "serve":
            command.add_argument("--host", default="127.0.0.1")
            command.add_argument("--port", type=int, default=8000)
        else:
            command.add_argument("--readiness", action="store_true")
    command = commands.add_parser("migrate")
    command.add_argument("--store", required=True, type=Path)
    command.add_argument("--namespace", choices=("production", "sandbox"), default="production")
    command = commands.add_parser("rotate-local-key")
    command.add_argument("--directory", required=True, type=Path)
    command.add_argument("--password-file", required=True, type=Path)
    command.add_argument("--publish", required=True, type=Path)
    for name in ("backup", "audit", "restore"):
        command = commands.add_parser(name)
        command.add_argument("--namespace", choices=("production", "sandbox"), default="production")
        command.add_argument("--keys", required=True, type=Path)
        command.add_argument("--checkpoint", type=Path, required=name == "restore")
        if name == "restore":
            command.add_argument("--source", required=True, type=Path)
        else:
            command.add_argument("--store", required=True, type=Path)
        if name in ("backup", "restore"):
            command.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(argv)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("approv.ops")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        if args.command in ("serve", "check-config"):
            from approv.ops.app import Application, Runtime
            runtime = Runtime(load_deployment(args.config), namespace=args.namespace)
            if args.command == "serve":
                import uvicorn
                uvicorn.run(Application(runtime), host=args.host, port=args.port, workers=1,
                            access_log=False, server_header=False, timeout_keep_alive=5)
            elif args.readiness:
                state = runtime.ready()
                print(json.dumps(state))
                return 0 if state["status"] == "ready" else 1
            else:
                print(json.dumps({"status": "configuration_valid", "deployment_hash": runtime.deployment.digest}))
        elif args.command == "migrate":
            store = ReceiptStore(args.store, namespace=args.namespace)
            print(json.dumps({"status": "migrated", "store": str(store.path), **store.progress()}))
        elif args.command == "rotate-local-key":
            password = SecretFile(file=args.password_file.resolve()).read(Path.cwd())
            keys = KeyStore(args.directory, password=password)
            key_id = keys.rotate()
            keys.publish(args.publish)
            print(json.dumps({"key_id": key_id, "status": "published; update deployment explicitly to activate"}))
        else:
            keys = public_keys(args.keys)
            checkpoint = read_json(args.checkpoint.read_bytes()) if args.checkpoint else None
            if args.command == "restore":
                store = restore(args.source, args.destination, keys, checkpoint, namespace=args.namespace)
                print(json.dumps({"status": "restored", "store": str(store.path)}))
            else:
                store = ReceiptStore(args.store, namespace=args.namespace, create=False, migrate=False)
                bundle = audit(store, keys, checkpoint)
                if args.command == "backup":
                    result = backup(store, args.destination, keys)
                    print(json.dumps({"status": "backup_complete", "path": str(result)}))
                else:
                    print(json.dumps({"status": "verified", "count": len(bundle["records"]),
                                      "store_namespace": store.namespace,
                                      "last_correlation_id": bundle["records"][-1]["correlation_id"] if bundle["records"] else None,
                                      "checkpoint": bundle["checkpoint"]}))
        return 0
    except Exception as error:
        # No traceback, repr, provider prose, schema contents or secret values on stdout.
        print(json.dumps({"error": "operation_failed", "command": args.command,
                          "error_type": type(error).__name__,
                          "detail": str(error) if isinstance(error, ConfigError) else "check the configured dependency and retained audit inputs"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
