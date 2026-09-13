"""Turn a receipt into the document, from a shell.

    python -m approv.artifact record.json
    python -m approv.artifact record.json --html dispute.html --key <public-key-hex>

A merchant's returns desk does not write Python, and a rendering surface that only a
developer can invoke is not a document anybody is handed. This is the thinnest possible
wrapper: read one record, print or write the two renderings.

`--key` is the Ed25519 public key to print in the verification instructions. It is
optional, and leaving it out prints the placeholder plus an instruction to ask for the
key rather than silently dropping the section — see `signature.KEY_PLACEHOLDER`.

Verification is deliberately *not* run here. `scripts/verify_receipt.py` is the standalone
verifier, it imports none of our code, and a "verified" stamp printed by our own renderer
would prove that we agree with ourselves. The document says how a stranger checks it.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from approv.artifact.render import render_html, render_text
from approv.types.core import ComparisonRecord


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m approv.artifact", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("record", help="one ComparisonRecord as JSON, as issued")
    parser.add_argument("--key", help="Ed25519 public key, hex, printed in section 5")
    parser.add_argument("--html", help="write the HTML page here instead of stdout")
    parser.add_argument("--text", help="write the plain text here instead of stdout")
    args = parser.parse_args(argv)

    path = pathlib.Path(args.record)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"could not read {path}: {error}", file=sys.stderr)
        return 1
    if isinstance(payload, list):
        print("this takes one record; that file holds a chain of them", file=sys.stderr)
        return 1
    record = ComparisonRecord.model_validate(payload)

    # The file the instructions tell the reader to check is the file they were given.
    written = False
    if args.html:
        pathlib.Path(args.html).write_text(
            render_html(record, public_key=args.key, record_file=path.name),
            encoding="utf-8")
        written = True
    if args.text:
        pathlib.Path(args.text).write_text(
            render_text(record, public_key=args.key, record_file=path.name),
            encoding="utf-8")
        written = True
    if not written:
        sys.stdout.write(render_text(record, public_key=args.key, record_file=path.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
