"""The weekly partner report: what a design partner receives, and what renews the pilot.

    from approv.report import render_text, load_outcomes

    print(render_text(records, load_outcomes("returns.json"), partner="Hearth & Loom"))

Two halves, and only one of them is ours. The receipt side — volume, decisions,
provenance — is read off the signed chain and is complete today. The outcome side needs
returns data that arrives through an ingestion path that does not exist yet, so the feed
declares where it came from and every row derived from it carries that to the page.

Separate from `approv.artifact` on purpose. The artifact renders one record for a returns
desk settling one refund; this aggregates many for a partner deciding whether to keep
paying attention to us. Same discipline, different arithmetic, different reader — and
folding them together would make `artifact/` two things.
"""

from approv.report.document import VERSION, ReportDocument, build
from approv.report.outcomes import (
    FeedSource, Outcome, OutcomeFeed, Status, empty_feed, from_rows,
)
from approv.report.outcomes import load as load_outcomes
from approv.report.render import render_html, render_text, to_html, to_text

__all__ = ["VERSION", "ReportDocument", "build", "FeedSource", "Outcome", "OutcomeFeed",
           "Status", "empty_feed", "from_rows", "load_outcomes", "render_html",
           "render_text", "to_html", "to_text"]
