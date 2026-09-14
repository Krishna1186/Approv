"""The dispute artifact: what a merchant hands a returns desk.

DR 0020 §"What the record is for" makes the `ComparisonRecord` a dispute artifact whose
primary forum is the merchant's own returns desk — not a card network, because most
wrong-item losses become returns, where the merchant is judge and payer and nobody
external has to accept our format. That only works if a person can read it. This package
is the reading surface: one record in, one document out, in plain text or as a
self-contained HTML page.

    from approv.artifact import render_html, render_text

    print(render_text(record, public_key=key_hex))
    pathlib.Path("dispute.html").write_text(render_html(record, public_key=key_hex))

`build(record)` returns the structured document if a caller wants to render it some other
way. Nothing in this package decides anything, recomputes coverage, or adds a fact the
signed record does not carry.
"""

from approv.artifact.document import VERSION, Document, build
from approv.artifact.evidence import EvidenceDocument, build_evidence
from approv.artifact.render import is_evidence, render_html, render_text, to_html, to_text

__all__ = ["VERSION", "Document", "build", "EvidenceDocument", "build_evidence",
           "is_evidence", "render_html", "render_text", "to_html", "to_text"]
