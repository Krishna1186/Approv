"""The backtest: a partner's historical export, run offline, into receipts and a report.

    partner export files -> batch verification -> stored receipts -> the report

The first pilot is this and not live shadow. The partner sends files and we touch nothing
of theirs - no endpoint, no integration, no traffic. What comes back is a signed ledger
they can verify with a published key and none of our code, and the weekly report over it.

**Nothing here is backdated.** A backtest receipt proves what the backtest compared, on
the day it compared it. The store owns the timestamp and stamps now; the historical dates
stay in the export where they belong. A receipt that claimed to have been written at the
time of a sale it was not present for would be the one forgery this whole system exists to
make impossible.

**A backtest with no extractor measures our configuration, not their traffic.** Free text
and search queries need a reader. Run without one and every such order arrives with no
recovered constraints, which the engine correctly records as no stated request - and the
provenance and coverage rows then describe what we chose to read rather than what their
customers said. That is not a footnote; `EXTRACTION_OFF` goes on the report as a banner,
counted, with the share of orders it affects.

**Correlation ids in a backtest are derived, not unguessable.** DR 0016 §7 wants an
unguessable join key because the agent's half is signed against it. A historical export
has no such key, so one is derived deterministically from merchant, order and line - which
makes retries idempotent, which is what the store needs, and which is *not* the same
security property. `DERIVED_IDS` says so on the report.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from approv.report import importing as imp
from approv.report import tiers as t
from approv.report.document import ReportDocument, build
from approv.report.importing import Column, Problem, Severity
from approv.report.outcomes import (
    FeedSource, OutcomeFeed, empty_feed, from_order_outcomes,
)

VERSION = "report-backtest-v1"

# Chunk size for the store's batch path. The runbook's measured range: 1,000 rows amortise
# the history audit without holding the writer lock for a whole export.
CHUNK = 1000

EXTRACTION_OFF = (
    "This backtest ran with no extractor configured, so %d of %d orders arrived carrying "
    "free text or a search query that nothing read. Those orders are recorded as having "
    "no recoverable stated request, which is true of this run and is NOT a fact about "
    "your traffic: your customers said something and Approv was not configured to read "
    "it. Every provenance and coverage figure below is therefore a floor set by how this "
    "run was configured."
)

DERIVED_IDS = (
    "This export carried no Approv correlation id, so one was derived from merchant, "
    "order and line. It is stable across re-runs, which is what makes a repeated backtest "
    "return the same receipts rather than new ones. It is not unguessable, and a backtest "
    "receipt is therefore not a join key to an agent's signed half."
)

NOT_BACKDATED = (
    "Receipt timestamps are when Approv ran this backtest, never when the order was "
    "placed. The historical dates are in your export and in the period label. A receipt "
    "that claimed to predate the run would be a forgery, and the ledger will not produce "
    "one."
)


# --------------------------------------------------------------------------------------
# What an export looks like
# --------------------------------------------------------------------------------------

ORDER_COLUMNS = (
    Column("order_id", ("order", "order_number", "order_ref", "order_no", "ordernumber"),
           required=True),
    Column("line_id", ("line", "line_number", "line_item_id", "item_id", "lineitem"),
           buys="tells two lines of one order apart. Without it, an order that returned "
                "one of two items cannot be matched to the right receipt."),
    Column("category_id", ("category", "category_ref", "product_type", "producttype"),
           required=True),
    Column("product_id", ("product", "product_ref", "item", "parent_id"), required=True),
    Column("sku", ("variant_sku", "item_sku", "sku_code"), required=True),
    Column("variant_id", ("variant", "variant_ref", "option_id")),
    Column("quantity", ("qty", "units", "quantity_ordered"), required=True,
           parse=imp.parse_int),
    Column("unit_price", ("price", "unit_amount", "item_price", "line_price"),
           required=True, parse=imp.parse_money),
    Column("currency", ("currency_code", "ccy", "cur"), required=True),
    Column("ordered_at", ("order_date", "created_at", "placed_at", "order_datetime"),
           required=True, parse=imp.parse_timestamp),
    Column("availability", ("stock_status", "availability_status", "inventory_status"),
           buys="records what the catalogue said about stock at the time, which a "
                "returns desk reads when the dispute is about a substitution."),
    Column("catalogue_version", ("catalog_version", "snapshot_version"),
           buys="pins which revision of your catalogue the comparison ran against."),
    Column("correlation_id", ("approv_id", "request_id", "agent_request_id"),
           buys="the agent's own join key, where your checkout captured one. Without it "
                "Approv derives a stable id and says so."),
)

REQUEST_COLUMNS = (
    Column("order_id", ("order", "order_number", "order_ref", "order_no")),
    Column("line_id", ("line", "line_number", "line_item_id", "item_id")),
    Column("correlation_id", ("approv_id", "request_id", "agent_request_id")),
    Column("shape", ("type", "request_type", "channel", "source", "kind"),
           buys="which of the four request shapes this was: a protocol call, an on-site "
                "search, a declared-intent paragraph, or nothing at all."),
    Column("protocol", ("agent_protocol", "spec", "standard")),
    Column("fields", ("slots", "parameters", "attributes", "request_fields"),
           parse=imp.parse_mapping),
    Column("query", ("search_query", "q", "search_terms", "keywords")),
    Column("filters", ("facets", "search_filters", "refinements"),
           parse=imp.parse_mapping),
    Column("text", ("declared_intent", "request_text", "message", "prompt", "note")),
    Column("signed_mandate", ("mandate", "signed"), parse=imp.parse_bool),
)

OUTCOME_COLUMNS = (
    Column("order_id", ("order", "order_number", "order_ref", "order_no")),
    Column("line_id", ("line", "line_number", "line_item_id", "item_id")),
    Column("correlation_id", ("approv_id", "request_id")),
    Column("kind", ("event", "event_type", "status", "outcome"), required=True),
    Column("occurred_at", ("event_date", "date", "timestamp", "created_at"),
           required=True, parse=imp.parse_timestamp),
    Column("merchant_reason", ("reason", "reason_text", "comment", "notes"),
           buys="the desk's own words. Quoted on a dispute artifact and read by nothing."),
    Column("complained_attribute", ("attribute", "complaint_attribute",
                                    "returned_attribute", "issue"),
           buys="sharper attribution. Where your desk records which attribute the "
                "customer complained about, that decides who a wrong-item return is "
                "attributable to; without it the record as a whole decides, and that is "
                "the weaker instrument."),
    Column("reason_code", ("return_reason_code", "return_code", "code", "reason_id"),
           buys="the GOOD tier. Precision, recall and attribution all rest on your desk's "
                "own coding of why an order came back."),
    Column("ship_date", ("shipped_at", "dispatch_date", "dispatched_at", "fulfilled_at"),
           parse=imp.parse_timestamp,
           buys="with the window length, the MINIMUM tier: it is what makes a kept order "
                "distinguishable from one still inside its window."),
    Column("return_window_days", ("window_days", "returns_window", "return_period_days"),
           parse=imp.parse_int,
           buys="with the ship date, the MINIMUM tier. A single number for the whole "
                "export is fine; pass it with --window-days."),
    Column("return_window_closes_at", ("window_closes", "window_close_date",
                                       "returnable_until"), parse=imp.parse_timestamp,
           buys="the MINIMUM tier outright, and more accurately than ship date plus a "
                "nominal window, because it already has your holiday rules in it."),
)

FILES = (
    ("orders", ORDER_COLUMNS, True,
     "one row per order line you want verified. The backtest cannot run without it."),
    ("requests", REQUEST_COLUMNS, False,
     "what was asked for, one row per order line. Without it every order is recorded as "
     "carrying no stated request, which is the honest reading and makes the report almost "
     "empty."),
    ("catalogue", (), True,
     "your product data as it stood, JSON or JSONL keyed by product id, or a CSV whose "
     "columns use dotted paths like `variant.size`. The comparison runs against this."),
    ("outcomes", OUTCOME_COLUMNS, False,
     "what happened next, one row per event. Which columns it carries decides which rung "
     "of the data ladder the report reaches."),
)


def key_of(values: Mapping[str, Any]) -> tuple[str, str | None]:
    return (str(values.get("order_id", "")), values.get("line_id"))


def derived_correlation_id(merchant_id: str, order_id: str, line_id: str | None) -> str:
    """A stable id for an export that has none. Deterministic, and not unguessable.

    Deterministic matters: the store treats an identical decision under an existing id as
    a retry and returns the original receipt, so a backtest re-run after a fixed column
    produces the same ledger rather than a second one. Random ids would double it.
    """
    seed = "|".join((merchant_id, order_id, line_id or ""))
    return "bt-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


@dataclass
class Export:
    """One partner export, read and joined, with everything wrong with it still attached."""

    directory: Path
    merchant_id: str
    orders: list[imp.Row] = field(default_factory=list)
    requests: dict[tuple, imp.Row] = field(default_factory=dict)
    catalogue: dict[str, dict] = field(default_factory=dict)
    outcomes: list[imp.Row] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    mappings: dict[str, imp.Mapped] = field(default_factory=dict)
    present: dict[str, list[str]] = field(default_factory=dict)
    window_days: int | None = None

    @property
    def notes(self) -> list[Problem]:
        return [p for p in self.problems if p.severity is Severity.NOTE]

    def correlation_for(self, row: imp.Row) -> str:
        stated = row.get("correlation_id")
        return stated or derived_correlation_id(
            self.merchant_id, str(row.get("order_id")), row.get("line_id"))

    @property
    def derived_ids(self) -> bool:
        return not any(row.get("correlation_id") for row in self.orders)


def _catalogue_rows(path: Path) -> tuple[list[dict], list[Problem]]:
    if path.suffix.lower() in (".json", ".jsonl", ".ndjson"):
        rows, problems = imp.read_json_rows(path)
        out = []
        for row in rows:
            values = dict(row.values)
            key = values.pop("_key", None)
            if key is not None and "product_id" not in values:
                values["product_id"] = key
            out.append(values)
        return out, problems
    rows, _, problems = imp.read_rows(path, (Column("product_id", ("id", "product"),
                                                    required=True),))
    text, _, more = imp.decode(path)
    problems += more
    # Re-read as raw cells: a catalogue's columns are the partner's own field names and a
    # fixed spec cannot know them. Dotted names become the nesting the snapshot needs.
    import csv as _csv
    reader = _csv.DictReader(text.splitlines())
    out = []
    for line, raw in enumerate(reader, start=2):
        cleaned = {k: v for k, v in raw.items() if k and v not in (None, "")}
        try:
            out.append(imp.expand_dotted(cleaned))
        except ValueError as error:
            problems.append(Problem(path.name, line, None, "unreadable", str(error)))
    return out, problems


def load(directory: str | Path, *, merchant_id: str, day_first: bool | None = None,
         window_days: int | None = None) -> Export:
    """Read every file of an export and join them. Raises `ExportRejected` on anything fatal.

    Deliberately reads *everything* before raising. A partner who fixes the first fatal
    problem and resubmits only to be told about the second is a partner who stops
    resubmitting, and there is no technical reason to make them do it twice.
    """
    directory = Path(directory)
    export = Export(directory=directory, merchant_id=merchant_id, window_days=window_days)
    if not directory.is_dir():
        raise imp.ExportRejected([Problem(str(directory), None, None, "no_export",
                                          "not a directory")])

    for stem, columns, required, _ in FILES:
        paths = list(imp.iter_files(directory, stem))
        export.present[stem] = [p.name for p in paths]
        if not paths:
            if required:
                export.problems.append(Problem(
                    str(directory), None, None, "missing_file",
                    "no `%s` file found. Approv looked for any file whose name starts "
                    "with `%s`." % (stem, stem)))
            continue
        for path in paths:
            if stem == "catalogue":
                rows, problems = _catalogue_rows(path)
                export.problems += problems
                for values in rows:
                    identity = values.get("product_id") or values.get("id")
                    if identity:
                        export.catalogue[str(identity)] = values
                continue
            rows, mapped, problems = imp.read_rows(path, columns, day_first=day_first)
            export.problems += problems
            export.mappings[stem] = mapped
            if stem == "orders":
                rows, more = imp.deduplicate(rows, lambda r: key_of(r.values),
                                             file=path.name)
                export.problems += more
                export.orders += rows
            elif stem == "requests":
                rows, more = imp.deduplicate(rows, lambda r: key_of(r.values),
                                             file=path.name)
                export.problems += more
                for row in rows:
                    export.requests[key_of(row.values)] = row
            else:
                export.outcomes += rows

    _join_problems(export)
    imp.raise_if_fatal(export.problems)
    return export


def _join_problems(export: Export) -> None:
    """What the files say about each other. The failures no single file can show.

    An order with no catalogue record cannot be compared at all and is fatal - running it
    would produce a receipt whose evidence side is empty, which reads as "we checked and
    found nothing wrong". An outcome with no order is not fatal and is the most
    interesting row in the export: it is their traffic that never reached us.
    """
    for row in export.orders:
        product = str(row.get("product_id"))
        if product not in export.catalogue:
            export.problems.append(Problem(
                "orders", row.line, "product_id",
                "no_catalogue_record",
                "product `%s` has no record in the catalogue file. Approv will not "
                "compare an order against a snapshot it does not have." % product))
    known = {key_of(row.values) for row in export.orders}
    orphans = [row for row in export.outcomes if key_of(row.values) not in known
               and not row.get("correlation_id")]
    if orphans:
        export.problems.append(Problem(
            "outcomes", orphans[0].line, None, "outcome_without_order",
            "%d outcome row(s) name an order that is not in the orders file. They are "
            "kept and counted: they are the share of your traffic that never reached "
            "Approv, and no other number in the report can see it." % len(orphans),
            Severity.NOTE))
    if export.orders and not export.requests:
        export.problems.append(Problem(
            "requests", None, None, "no_requests",
            "no request file, so every order is recorded as carrying no stated request. "
            "The report will be honest and almost empty.", Severity.NOTE))


# --------------------------------------------------------------------------------------
# The dry run
# --------------------------------------------------------------------------------------


@dataclass
class Survey:
    """What an export contains and what it would buy, without verifying anything.

    The artifact the founder sends back after the first data conversation. It answers one
    question - *which rung does this land on, and what is missing to reach the next* - and
    it answers it without running the engine, so it costs the partner nothing to ask.
    """

    directory: Path
    files: dict[str, list[str]]
    counts: dict[str, int]
    tier: t.Tier
    mappings: dict[str, imp.Mapped]
    problems: list[Problem]
    missing: dict[str, tuple[str, str]] = field(default_factory=dict)
    readable: bool = True
    unread_requests: int = 0
    total_orders: int = 0


def _tier_of_columns(export: Export) -> t.Tier:
    """Which rung this export's outcome columns reach, before a single row is verified.

    Read off the columns that resolved and the values actually present, not off the
    partner's description of their data. A column that exists and is empty in every row
    buys nothing, and saying otherwise would put a rung on the page that the numbers
    underneath then refuse.
    """
    if not export.outcomes:
        return t.Tier.NONE
    values = lambda name: any(row.get(name) is not None for row in export.outcomes)
    window = (values("return_window_closes_at")
              or (values("ship_date") and (values("return_window_days")
                                           or export.window_days is not None)))
    if not window:
        return t.Tier.RETURNS_ONLY
    if not values("reason_code"):
        return t.Tier.MINIMUM
    kinds = {str(row.get("kind", "")).strip().lower() for row in export.outcomes}
    if not ({"disputed", "dispute", "chargeback"} & kinds):
        return t.Tier.GOOD
    return t.Tier.BEST


def survey(directory: str | Path, *, merchant_id: str, day_first: bool | None = None,
           window_days: int | None = None) -> Survey:
    """Read the export and report what it would buy. Never raises on a fatal problem.

    A dry run that refused to produce an answer for a broken export would be useless
    precisely when it is most needed: the first export is usually broken, and the point of
    this is to say how.
    """
    directory = Path(directory)
    try:
        export = load(directory, merchant_id=merchant_id, day_first=day_first,
                      window_days=window_days)
        readable = True
    except imp.ExportRejected as rejected:
        readable = False
        export = Export(directory=directory, merchant_id=merchant_id,
                        problems=list(rejected.problems))
        # Re-read leniently so the survey can still describe what is there. The fatal
        # problems are already captured; this is only to count files and columns.
        try:
            export = _lenient(directory, merchant_id, day_first, window_days,
                              rejected.problems)
        except Exception:                                     # pragma: no cover - defensive
            pass

    tier = _tier_of_columns(export)
    missing = {}
    for stem, columns, _, _ in FILES:
        mapped = export.mappings.get(stem)
        if mapped is None:
            continue
        for name in mapped.missing_optional:
            column = next(c for c in columns if c.name == name)
            if column.buys:
                missing[stem + "." + name] = (name, column.buys)
    unread = sum(1 for row in export.requests.values()
                 if row.get("text") or row.get("query"))
    return Survey(directory=directory, files=export.present,
                  counts={"orders": len(export.orders),
                          "requests": len(export.requests),
                          "catalogue": len(export.catalogue),
                          "outcomes": len(export.outcomes)},
                  tier=tier, mappings=export.mappings, problems=export.problems,
                  missing=missing, readable=readable, unread_requests=unread,
                  total_orders=len(export.orders))


def _lenient(directory, merchant_id, day_first, window_days, problems) -> Export:
    """A second pass that keeps going past fatal problems, for the survey only.

    Never used to verify anything. Its whole job is to let the dry run say "you have 41,000
    orders and no ship date" about an export that also has a broken date on line 12,841,
    instead of saying only the second thing.
    """
    export = Export(directory=Path(directory), merchant_id=merchant_id,
                    problems=list(problems), window_days=window_days)
    for stem, columns, _, _ in FILES:
        paths = list(imp.iter_files(Path(directory), stem))
        export.present[stem] = [p.name for p in paths]
        for path in paths:
            if stem == "catalogue":
                rows, _ = _catalogue_rows(path)
                for values in rows:
                    identity = values.get("product_id") or values.get("id")
                    if identity:
                        export.catalogue[str(identity)] = values
                continue
            rows, mapped, _ = imp.read_rows(path, columns, day_first=day_first)
            export.mappings[stem] = mapped
            if stem == "orders":
                export.orders += rows
            elif stem == "requests":
                for row in rows:
                    export.requests[key_of(row.values)] = row
            else:
                export.outcomes += rows
    return export


def _wrapped(text: str, indent: str = "  ", width: int = 84) -> str:
    import textwrap
    return textwrap.fill(text, width=width, initial_indent=indent,
                         subsequent_indent=indent)


def survey_text(result: Survey) -> str:
    """The dry run as a page. Plain text on purpose: it is pasted into an email reply."""
    width = 84
    out = ["=" * width, "APPROV EXPORT SURVEY", str(result.directory),
           "No verification was run. Nothing was decided. This reads your files and says "
           "what they would support.", "=" * width, ""]
    out.append("FILES FOUND")
    for stem, _, required, why in FILES:
        found = result.files.get(stem) or []
        mark = "x" if found else (" " if not required else "!")
        out.append("  [%s] %-10s %s" % (mark, stem,
                                        ", ".join(found) if found else "not found"))
        out.append("      " + why)
    out.append("")
    out.append("ROWS READ")
    for name, count in result.counts.items():
        out.append("  %-12s %d" % (name, count))
    out.append("")

    spec = t.TIERS[result.tier]
    heading = ("THE RUNG THIS EXPORT LANDS ON: " if result.readable
               else "THE RUNG THIS EXPORT LANDS ON, AT LEAST: ")
    out += [heading + spec.name, "  " + spec.headline, ""]
    if not result.readable:
        # The rung is computed over the rows that parsed, and rows were refused. A partner
        # whose dates are unreadable would otherwise be told their data supports less than
        # it does, and would send fields they already have instead of fixing a format.
        out += [_wrapped("This export has problems that stopped some rows being read, so "
                         "the rung above is a floor rather than a reading: it was "
                         "computed over the rows that parsed. Fix the problems listed at "
                         "the end and run this again before deciding what to send.", "  "),
                ""]
    for item in spec.unlocks:
        out.append("  buys: " + item)
    for item in spec.cannot:
        out.append("  still cannot: " + item)
    out.append("")
    if result.tier < t.Tier.BEST:
        nxt = t.TIERS[t.Tier(result.tier + 1)]
        out += ["TO REACH " + nxt.name]
        for item in nxt.supplies:
            out.append("  send: " + item)
        out.append("")
    if result.missing:
        out.append("COLUMNS NOT FOUND, AND WHAT EACH WOULD BUY")
        for key, (name, buys) in sorted(result.missing.items()):
            out.append("  %s" % key)
            out.append("      " + buys)
        out.append("")
    if result.unread_requests:
        out += ["%d request(s) carry free text or a search query. Reading those needs an "
                "extractor; run without one and they are recorded as carrying no stated "
                "request, which understates your provenance rate."
                % result.unread_requests, ""]

    bad = [p for p in result.problems if p.severity is Severity.FATAL]
    notes = [p for p in result.problems if p.severity is Severity.NOTE]
    if bad:
        out += ["THIS EXPORT CANNOT BE RUN YET. %d problem(s) to fix:" % len(bad), ""]
        for problem in bad[:50]:
            out.append("  " + str(problem))
        if len(bad) > 50:
            out.append("  ... and %d more" % (len(bad) - 50))
    else:
        out.append("No blocking problems. This export can be run.")
    if notes:
        out += ["", "READ, WITH A NOTE:"]
        for problem in notes[:30]:
            out.append("  " + str(problem))
    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------


@dataclass
class Backtest:
    """What a run produced, and what it cost."""

    records: list
    feed: OutcomeFeed
    document: ReportDocument
    # Cart-only receipts, verified and reported but not in the ledger: the store does not
    # accept the type yet. Held separately rather than merged into `records` so that
    # "what is in the chain" and "what is on the report" cannot be confused for each other.
    evidence_only: tuple = ()
    verified: int = 0
    failed: tuple[Problem, ...] = ()
    seconds_verifying: float = 0.0
    seconds_storing: float = 0.0
    notes: tuple[str, ...] = ()

    @property
    def throughput(self) -> float:
        total = self.seconds_verifying + self.seconds_storing
        return self.verified / total if total else 0.0


def _is_evidence(record) -> bool:
    """The cart-only receipt product, read off its own signed `kind`."""
    return getattr(record, "kind", "") == "order_evidence"


def _artifact(row: imp.Row | None):
    """One request row as the intake shape it actually is.

    An export with no `shape` column still has a readable request: a row with filters and
    a query is an on-site search whatever it is labelled. Inferring the shape from the
    *fields that are populated* is safe in a way that inferring a value never is - it
    reads what is there rather than inventing what is not - and a row with nothing
    populated is `Undeclared`, which is a real answer and not a failure.
    """
    from approv.intake import FreeText, Search, Structured, Undeclared

    if row is None:
        return Undeclared(why="no request row in the export for this order line")
    shape = str(row.get("shape", "") or "").strip().lower().replace("-", "_")
    fields, filters = row.get("fields") or {}, row.get("filters") or {}
    query, text = row.get("query") or "", row.get("text") or ""

    if shape in ("structured", "protocol", "acp", "ap2", "mcp", "tool_call") or (
            not shape and fields and not query and not filters):
        return Structured(protocol=str(row.get("protocol") or shape or "unnamed"),
                          fields=fields, signed_mandate=bool(row.get("signed_mandate")))
    if shape in ("search", "onsite_search", "site_search") or (
            not shape and (filters or query)):
        return Search(query=query, filters=filters)
    if shape in ("free_text", "freetext", "declared_intent", "message") or (
            not shape and text):
        return FreeText(text=text)
    if shape in ("undeclared", "none", "direct"):
        return Undeclared()
    if shape:
        return Undeclared(why="request shape `%s` is not one Approv knows; recorded as "
                              "no stated request rather than guessed at" % shape)
    return Undeclared(why="the request row named no shape and populated no field")


def _order_line(row: imp.Row):
    from approv.types.core import Money, OrderLine

    return OrderLine(
        order_id=str(row.get("order_id")), line_id=row.get("line_id"),
        product_id=str(row.get("product_id")), sku=str(row.get("sku")),
        variant_id=row.get("variant_id"), quantity=int(row.get("quantity")),
        unit_price=Money(amount=row.get("unit_price"),
                         currency=str(row.get("currency")).upper()),
        availability=row.get("availability"),
        catalogue_version=row.get("catalogue_version"))


_KINDS = {"shipped": "shipped", "fulfilled": "shipped", "dispatched": "shipped",
          "delivered": "shipped", "returned": "returned", "return": "returned",
          "refunded": "refunded", "refund": "refunded", "disputed": "disputed",
          "dispute": "disputed", "chargeback": "disputed"}


def _outcome_events(export: Export, *, correlations: Mapping[tuple, str]):
    """Outcome rows as `OrderOutcome` events, with their kind mapped from the desk's word.

    The kind vocabulary is mapped and the *reason* code never is. They are not the same
    thing: `dispatched` and `shipped` are two names for one event and mapping them reads
    their file, whereas `RTN-SIZE` and `wrong_item` are two judgements and mapping those
    would be making one of them up. An unrecognised kind is refused with its line number
    rather than bucketed.
    """
    from approv.types.core import OrderOutcome, OutcomeKind

    events, problems = [], []
    for row in export.outcomes:
        word = str(row.get("kind", "")).strip().lower()
        kind = _KINDS.get(word)
        if kind is None:
            problems.append(Problem("outcomes", row.line, "kind", "unknown_event",
                                    "`%s` is not an event Approv knows. Accepted: %s"
                                    % (row.get("kind"), ", ".join(sorted(set(_KINDS))))))
            continue
        identity = row.get("correlation_id") or correlations.get(key_of(row.values))
        if identity is None:
            # Kept as an orphan rather than dropped: it is an order the desk saw and we
            # never did, and `join` counts exactly that.
            identity = "unmatched-" + str(row.get("order_id"))
        window = row.get("return_window_days")
        if window is None and export.window_days is not None and row.get("ship_date"):
            window = export.window_days
        events.append(OrderOutcome(
            correlation_id=identity, kind=OutcomeKind(kind),
            occurred_at=row.get("occurred_at"),
            merchant_reason=row.get("merchant_reason"),
            reason_code=row.get("reason_code"),
            complained_attribute=row.get("complained_attribute"),
            ship_date=row.get("ship_date"), return_window_days=window,
            return_window_closes_at=row.get("return_window_closes_at")))
    return events, problems


def run(export: Export, *, schemas, store, signing_key, extract: Callable | None = None,
        chunk: int = CHUNK, as_of: datetime | None = None, partner: str = "",
        period: str = "", unread_policy=None, ledger: str | None = None) -> Backtest:
    """Verify every order line in the export, store the receipts, and build the report.

    Batched on purpose. Per-order latency is irrelevant to a backtest and throughput is
    not: an export is thousands of rows, the store audits its history once per batch, and
    a per-row append would audit it once per row. Decisions are materialised before the
    writer lock is taken, which is the store's own contract.

    A row that cannot be verified is recorded as a problem with its line number and the
    run continues. One malformed order out of forty thousand must not cost the partner the
    other 39,999 - but it must not vanish either, so the count is on the report.
    """
    from approv.surface.verification import VerificationRequest, verify_order

    correlations = {key_of(row.values): export.correlation_for(row)
                    for row in export.orders}
    drafts, failures, unread_orders = [], [], 0
    started = time.monotonic()
    for row in export.orders:
        artifact = _artifact(export.requests.get(key_of(row.values)))
        if extract is None and getattr(artifact, "text", "") + getattr(
                artifact, "query", ""):
            unread_orders += 1
        try:
            kw = {} if unread_policy is None else {"unread_policy": unread_policy}
            result = verify_order(
                VerificationRequest(
                    merchant_id=export.merchant_id,
                    correlation_id=correlations[key_of(row.values)],
                    category_id=str(row.get("category_id")),
                    order=_order_line(row), artifact=artifact,
                    product_snapshot=export.catalogue[str(row.get("product_id"))]),
                schemas=schemas, extract=extract, **kw)
        except Exception as error:
            failures.append(Problem("orders", row.line, None, "not_verified",
                                    "%s: %s" % (type(error).__name__, error)))
            continue
        drafts.append(result.record)
    seconds_verifying = time.monotonic() - started

    started = time.monotonic()
    records, unsealable = [], []
    for index in range(0, len(drafts), chunk):
        batch = drafts[index:index + chunk]
        try:
            records += store.append_many(batch, signing_key)
        except TypeError as error:
            # SEAM: `verify_order` returns an `OrderEvidenceRecord` for cart-only traffic
            # and `ReceiptStore.append_many` accepts only a `ComparisonRecord`, so the one
            # receipt product built for orders with no stated request cannot be sealed at
            # all. Split the batch, seal what the store will take, and count the rest -
            # dropping them quietly would delete exactly the population DR 0020 wants
            # measured, and failing the whole run would lose the partner every other row.
            sealable = [d for d in batch if not _is_evidence(d)]
            unsealable += [d for d in batch if _is_evidence(d)]
            if len(sealable) == len(batch):
                raise
            del error
            records += store.append_many(sealable, signing_key)
    seconds_storing = time.monotonic() - started

    events, event_problems = _outcome_events(export, correlations=correlations)
    failures += event_problems
    feed = (from_order_outcomes(
        events, source=FeedSource.PARTNER, as_of=as_of,
        description="backtest of %s, %d outcome event(s)"
                    % (export.directory.name, len(events)))
            if events else empty_feed("the export carried no outcome file"))

    # What the caller knows and the records cannot show. A backtest run with no extractor
    # produces a provenance rate that is a fact about our configuration, so it goes in the
    # banner rather than in a covering email nobody forwards; the rest are standing limits
    # of a backtest and sit with the other standing limits.
    notices, caveats = [], [NOT_BACKDATED]
    if unsealable:
        failures.append(Problem(
            "receipts", None, None, "evidence_not_sealable",
            "%d order(s) with no stated request produced an order-evidence receipt, and "
            "ReceiptStore accepts only a ComparisonRecord. They were verified, they are "
            "in the report, and they are NOT in the ledger." % len(unsealable)))
        caveats.append(
            "%d order(s) arrived with no stated request and produced an order-evidence "
            "receipt rather than a verification. Those receipts could not be written to "
            "the ledger - the store does not accept that record type yet - so they are "
            "counted on this report and are not in the chain you can verify. Nothing "
            "about them is a verification and nothing about them is covered."
            % len(unsealable))
    if export.derived_ids:
        caveats.append(DERIVED_IDS)
    if failures:
        caveats.append(
            "%d order line(s) in the export could not be verified and are not in the "
            "ledger or in any number here. They are listed with their line numbers in "
            "the run output." % len(failures))
    if unread_orders:
        notices.append(EXTRACTION_OFF % (unread_orders, len(export.orders)))
    # The evidence receipts go to the report even though they are not in the ledger. They
    # are orders that happened, they belong in the volume table and in the provenance
    # denominator, and omitting them would make the provenance rate a rate over the orders
    # that had provenance.
    document = build(records + unsealable, feed,
                     partner=partner or export.merchant_id,
                     period=period or _period_of(export), ledger=ledger,
                     generated_at=as_of, notices=tuple(notices),
                     extra_caveats=tuple(caveats))
    notes = notices + caveats
    return Backtest(records=records, feed=feed, document=document,
                    verified=len(records) + len(unsealable),
                    evidence_only=tuple(unsealable),
                    failed=tuple(failures), seconds_verifying=seconds_verifying,
                    seconds_storing=seconds_storing, notes=tuple(notes))


def _period_of(export: Export) -> str:
    """The period read off the export's own order dates, never off the run date.

    A backtest's receipts are stamped today and its *period* is historical, and confusing
    the two is how a partner ends up reading last March's traffic under this week's date.
    """
    dates = sorted(row.get("ordered_at") for row in export.orders
                   if row.get("ordered_at"))
    if not dates:
        return "the period"
    return "%s to %s (historical; backtested %s)" % (
        dates[0].date().isoformat(), dates[-1].date().isoformat(),
        datetime.now(timezone.utc).date().isoformat())
