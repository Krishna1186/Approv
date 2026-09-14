"""Reading a partner's historical export, as it actually arrives.

The first pilot is a backtest: the partner sends files, we run them offline, we touch
nothing of theirs. **This module is their first experience of Approv**, and the thing it
must never do is the convenient thing. A silently coerced date, a quietly dropped row, a
column guessed at because the name was close - each of those turns a number on the report
into a number about a dataset nobody has seen. So:

**Reject loudly, with a line number.** Every problem carries the file, the line, the
column and a code. A fatal problem stops the import and names every fatal problem found,
not just the first, because a partner who fixes one and resubmits to find another is a
partner who stops resubmitting.

**Never coerce silently.** `03/04/2026` is not a date, it is two dates, and this module
refuses it unless the export says which convention it uses. `1,234` is not a number when
a comma might be a decimal point. Where a reading *is* forced - a naive timestamp read as
UTC - it is recorded as a problem of its own and counted on the import report, so the
partner is told rather than trusted to guess.

**Read what an export looks like, not what we wish it did.** Columns named differently,
several date formats in one file, a UTF-8 BOM, cp1252 bytes in a customer's free text,
the same order line exported twice. Those are the normal case and each has a rule here.

What this module does *not* do: decide anything, call a model, or touch the engine. It
turns files into typed rows and a list of problems. `approv.report.backtest` runs them.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

VERSION = "report-importing-v1"


class Severity(str, Enum):
    """How much a problem costs.

    FATAL stops the import. NOTE does not, and is still printed and counted - a reading
    that had to be forced is not an error but it is not nothing either, and the only way
    a partner learns that 47 of their timestamps had no timezone is if somebody says so.
    """

    FATAL = "fatal"
    NOTE = "note"


@dataclass(frozen=True)
class Problem:
    """One thing wrong with one place in one file.

    The line number is not decoration. A partner told "the date format is wrong" has to
    search a 40,000-row file; a partner told "orders.csv:12841, column `shipped`" fixes it
    in a minute. Every fatal problem raised by this module carries one.
    """

    file: str
    line: int | None
    column: str | None
    code: str
    detail: str
    severity: Severity = Severity.FATAL

    def __str__(self) -> str:
        where = self.file
        if self.line is not None:
            where += ":%d" % self.line
        if self.column:
            where += " column `%s`" % self.column
        return "%s: [%s] %s" % (where, self.code, self.detail)


class ExportRejected(Exception):
    """The export cannot be read. Carries every fatal problem, never only the first."""

    def __init__(self, problems: Sequence[Problem]):
        self.problems = tuple(problems)
        super().__init__("%d problem(s) in the export:\n%s"
                         % (len(self.problems),
                            "\n".join("  " + str(p) for p in self.problems)))


# --------------------------------------------------------------------------------------
# Encoding
# --------------------------------------------------------------------------------------

# Tried in order. utf-8-sig first so a BOM is consumed rather than becoming part of the
# first column name - which is the single most common reason a required column "goes
# missing" from a file exported out of a spreadsheet on Windows.
ENCODINGS = ("utf-8-sig", "utf-8", "cp1252")


def decode(path: Path) -> tuple[str, str, list[Problem]]:
    """The file's text, the encoding that worked, and what it cost to read it.

    cp1252 is the last resort and never a silent one: falling back to it means the file
    was not valid UTF-8, which usually means a customer's free text carries a smart quote
    from a Windows desk, and the partner should know that is what happened rather than
    find a mojibake apostrophe quoted back at them on a dispute artifact months later.
    """
    raw = path.read_bytes()
    problems: list[Problem] = []
    for encoding in ENCODINGS:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError as error:
            if encoding == "utf-8":
                line = raw[:error.start].count(b"\n") + 1
                problems.append(Problem(
                    path.name, line, None, "not_utf8",
                    "byte 0x%02x at offset %d is not valid UTF-8; read as cp1252 "
                    "instead. If that is wrong, re-export as UTF-8."
                    % (raw[error.start], error.start), Severity.NOTE))
            continue
        if encoding == "utf-8-sig" and raw.startswith(b"\xef\xbb\xbf"):
            problems.append(Problem(path.name, 1, None, "byte_order_mark",
                                    "the file begins with a UTF-8 byte order mark, which "
                                    "was stripped before reading the header.",
                                    Severity.NOTE))
        return text, encoding, problems
    raise ExportRejected([Problem(path.name, None, None, "undecodable",
                                  "the file could not be decoded as any of: %s"
                                  % ", ".join(ENCODINGS))])


# --------------------------------------------------------------------------------------
# Columns
# --------------------------------------------------------------------------------------

def normalise(name: str) -> str:
    """`Order Ref.` and `order_ref` are the same column; `orders` and `order` are not.

    Case, spaces, hyphens, dots and underscores are formatting. Nothing else is collapsed:
    a fuzzy match that turned `ship_date` into `shipped_date` would be exactly the kind of
    helpful guess that puts the wrong column behind a number.
    """
    return re.sub(r"[\s\-_.]+", "", name.strip().lower())


@dataclass(frozen=True)
class Column:
    """One column we need, the names a partner might have called it, and how to read it."""

    name: str
    aliases: tuple[str, ...] = ()
    required: bool = False
    parse: Callable[..., Any] | None = None
    # What this column buys. Printed by the dry run against any column that is absent, so
    # a partner deciding whether to add it can see what it is for.
    buys: str = ""

    def names(self) -> tuple[str, ...]:
        """The spellings as a partner would write them. Printed when a column is missing.

        Normalised forms are for matching and are unreadable as advice: a partner told
        Approv looked for `orderref` cannot tell whether `order_ref` would work.
        """
        return (self.name,) + self.aliases

    def matches(self) -> set[str]:
        return {normalise(n) for n in self.names()}


@dataclass
class Mapped:
    """A header row, resolved against a column spec, and how much of the file followed it.

    `rows_seen` against `rows_read` is the pair that matters on a survey. A file of 40,000
    rows of which 300 parsed is a file with a problem, and reporting only the 300 would
    describe the partner's business as a fortieth of its size.
    """

    by_column: dict[str, str] = field(default_factory=dict)     # our name -> their header
    unmatched_headers: tuple[str, ...] = ()
    missing_required: tuple[str, ...] = ()
    missing_optional: tuple[str, ...] = ()
    rows_seen: int = 0
    rows_read: int = 0


def map_header(headers: Sequence[str], columns: Sequence[Column]) -> Mapped:
    """Resolve their header row against what we need.

    An unmatched header of theirs is reported and ignored rather than being an error: a
    real export carries their internal columns and refusing the file over a `warehouse_id`
    would be refusing every real export. A required column of ours that is unmatched is
    fatal, and the message lists every alias that was tried - a partner whose column is
    called `dispatch_date` needs to know we looked for `ship_date`, not that something
    went wrong.
    """
    seen = {normalise(h): h for h in headers if h is not None}
    mapped = Mapped()
    claimed: set[str] = set()
    for column in columns:
        hit = next((seen[key] for key in column.matches() if key in seen), None)
        if hit is not None:
            mapped.by_column[column.name] = hit
            claimed.add(normalise(hit))
        elif column.required:
            mapped.missing_required += (column.name,)
        else:
            mapped.missing_optional += (column.name,)
    mapped.unmatched_headers = tuple(h for h in headers
                                     if h and normalise(h) not in claimed)
    return mapped


# --------------------------------------------------------------------------------------
# Values, none of them coerced quietly
# --------------------------------------------------------------------------------------

_ISO = "%Y-%m-%d"
_SLASHED = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$")
_EPOCH = re.compile(r"^\d{9,13}$")


class Ambiguous(ValueError):
    """A value that has more than one reading. Never resolved by picking one."""


def parse_timestamp(text: str, *, day_first: bool | None = None) -> tuple[datetime, str | None]:
    """A timestamp, and the note it cost to read it.

    Accepts what exports actually contain: ISO 8601 with or without a time and offset,
    `YYYY-MM-DD`, `DD/MM/YYYY` and `MM/DD/YYYY`, and epoch seconds or milliseconds.

    **`03/04/2026` is refused.** It is the third of April and it is the fourth of March,
    and an importer that picks one has invented a fact about a return window. It is read
    only when `day_first` has been declared for the export, or when one of the two numbers
    is above twelve and settles it by itself.

    A timestamp with no timezone is read as UTC and **says so**, because a partner whose
    warehouse exports local time needs to know that a window close moved by a few hours,
    and because "we assumed UTC" is a sentence somebody has to have written down.
    """
    value = text.strip()
    if not value:
        raise ValueError("empty")
    if _EPOCH.match(value):
        number = int(value)
        seconds = number / 1000 if len(value) > 10 else number
        return datetime.fromtimestamp(seconds, tz=timezone.utc), None

    slashed = _SLASHED.match(value)
    if slashed:
        first, second, year = (int(g) for g in slashed.groups())
        if first > 12 and second > 12:
            raise ValueError("neither %d nor %d can be a month" % (first, second))
        if first > 12:
            day, month = first, second
        elif second > 12:
            day, month = second, first
        elif first == second:
            # `04/04/2026` reads the same either way. Refusing it would be refusing a
            # value that has exactly one meaning, for looking like a class that does not.
            day, month = first, second
        elif day_first is None:
            raise Ambiguous(
                "`%s` is both %d/%d and %d/%d. Declare the export's convention "
                "(day-first or month-first) and re-run; Approv will not pick one."
                % (value, first, second, second, first))
        else:
            day, month = (first, second) if day_first else (second, first)
        return datetime(year, month, day, tzinfo=timezone.utc), "read as a date with no time of day"

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("not a timestamp Approv can read. Accepted: ISO 8601, "
                         "YYYY-MM-DD, DD/MM/YYYY or MM/DD/YYYY with the export's "
                         "convention declared, or epoch seconds")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc), "no timezone; read as UTC"
    return parsed, None


_THOUSANDS = re.compile(r"^\d{1,3}(,\d{3})+$")


def parse_money(text: str) -> Decimal:
    """An amount, or a refusal. Never a guess about which separator is the decimal point.

    `1.234,56` and `1,234.56` are both readable: whichever separator comes last is the
    decimal one. `1,234` is readable as a thousands group. `1,23` is not readable at all -
    it is one and twenty-three hundredths in half of Europe and one hundred and
    twenty-three in the other half, and a unit price is what a refund is denominated in.
    """
    value = text.strip().replace(" ", "").replace(" ", "")
    if not value:
        raise ValueError("empty")
    value = re.sub(r"^[^\d\-+.,]+|[^\d.,]+$", "", value)     # currency symbols and codes
    if "," in value and "." in value:
        decimal_point = "," if value.rindex(",") > value.rindex(".") else "."
        value = (value.replace(".", "").replace(",", ".") if decimal_point == ","
                 else value.replace(",", ""))
    elif "," in value:
        if _THOUSANDS.match(value):
            value = value.replace(",", "")
        else:
            raise Ambiguous(
                "`%s` uses a comma that is either a decimal point or a thousands "
                "separator. Export amounts with a full stop as the decimal point."
                % text.strip())
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError("not an amount")


_TRUE = {"true", "t", "yes", "y", "1"}
_FALSE = {"false", "f", "no", "n", "0", ""}


def parse_bool(text: str) -> bool | None:
    value = text.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return None if value == "" else False
    raise ValueError("not a yes/no value")


def parse_int(text: str) -> int:
    value = text.strip().replace(",", "")
    if not value:
        raise ValueError("empty")
    if not re.fullmatch(r"-?\d+", value):
        raise ValueError("not a whole number")
    return int(value)


def parse_mapping(text: str) -> dict:
    """A JSON object in a cell, or `a=1;b=2`, which is what spreadsheets produce."""
    value = text.strip()
    if not value:
        return {}
    if value.startswith("{"):
        loaded = json.loads(value)
        if not isinstance(loaded, dict):
            raise ValueError("a JSON value that is not an object")
        return loaded
    pairs = {}
    for part in re.split(r"[;|]", value):
        if not part.strip():
            continue
        split = re.split(r"[=:]", part, maxsplit=1)
        if len(split) != 2:
            raise ValueError("not a JSON object and not `key=value` pairs")
        pairs[split[0].strip()] = split[1].strip()
    return pairs


# --------------------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    """One line of one file, with where it came from still attached.

    The line number travels with the data rather than being discarded at the parse
    boundary, because the problems that matter most - a duplicate that disagrees with
    itself, an order with no matching request - are found later, and a message about them
    is worth very little without it.
    """

    line: int
    values: Mapping[str, Any]

    def get(self, name: str, default=None):
        return self.values.get(name, default)


def read_rows(path: Path, columns: Sequence[Column], *, day_first: bool | None = None
              ) -> tuple[list[Row], Mapped, list[Problem]]:
    """One delimited file, read into typed rows and a list of everything wrong with it.

    The delimiter is sniffed across comma, semicolon and tab, because a European export
    out of Excel is semicolon-delimited and refusing it would be refusing the file for
    being from Germany. A file whose header row does not resolve is fatal immediately:
    parsing 40,000 rows against a mapping that is already wrong produces 40,000 problems
    about one mistake.
    """
    text, _, problems = decode(path)
    if not text.strip():
        return [], Mapped(), problems + [Problem(path.name, None, None, "empty_file",
                                                 "the file has no content")]
    sample = "\n".join(text.splitlines()[:20])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(text.splitlines(), dialect=dialect)
    mapped = map_header(reader.fieldnames or [], columns)
    if mapped.missing_required:
        for name in mapped.missing_required:
            column = next(c for c in columns if c.name == name)
            problems.append(Problem(
                path.name, 1, name, "missing_column",
                "required column not found. Approv looked for: %s. Your header row is: %s"
                % (", ".join(column.names()),
                   ", ".join(reader.fieldnames or ["(none)"]))))
        return [], mapped, problems
    if mapped.unmatched_headers:
        problems.append(Problem(
            path.name, 1, None, "extra_columns",
            "columns Approv does not read, kept out of the import: %s"
            % ", ".join(mapped.unmatched_headers), Severity.NOTE))

    spec = {c.name: c for c in columns}
    rows: list[Row] = []
    notes_seen: dict[str, int] = {}
    line = 1
    for line, raw in enumerate(reader, start=2):
        values: dict[str, Any] = {}
        bad = False
        for name, header in mapped.by_column.items():
            cell = raw.get(header)
            cell = "" if cell is None else str(cell)
            column = spec[name]
            if not cell.strip():
                if column.required:
                    problems.append(Problem(path.name, line, name, "missing_value",
                                            "required value is empty"))
                    bad = True
                continue
            if column.parse is None:
                values[name] = cell.strip()
                continue
            try:
                parsed = (column.parse(cell, day_first=day_first)
                          if column.parse is parse_timestamp else column.parse(cell))
            except Ambiguous as error:
                problems.append(Problem(path.name, line, name, "ambiguous", str(error)))
                bad = True
                continue
            except (ValueError, json.JSONDecodeError) as error:
                problems.append(Problem(path.name, line, name, "unreadable",
                                        "`%s` is %s" % (cell.strip(), error)))
                bad = True
                continue
            if isinstance(parsed, tuple) and column.parse is parse_timestamp:
                parsed, note = parsed
                if note:
                    notes_seen[note] = notes_seen.get(note, 0) + 1
            values[name] = parsed
        if not bad:
            rows.append(Row(line, values))
    for note, count in sorted(notes_seen.items()):
        problems.append(Problem(path.name, None, None, "timestamp_note",
                                "%d timestamp(s) %s" % (count, note), Severity.NOTE))
    mapped.rows_seen = max(line - 1, 0)
    mapped.rows_read = len(rows)
    if mapped.rows_seen and mapped.rows_read < mapped.rows_seen:
        problems.append(Problem(
            path.name, None, None, "rows_dropped",
            "%d of %d data rows could not be read and are listed above. Nothing was "
            "guessed at and nothing was dropped quietly."
            % (mapped.rows_seen - mapped.rows_read, mapped.rows_seen), Severity.NOTE))
    return rows, mapped, problems


def deduplicate(rows: Sequence[Row], key: Callable[[Row], tuple], *, file: str
                ) -> tuple[list[Row], list[Problem]]:
    """Collapse identical repeats; refuse repeats that disagree.

    The two are not the same event and must not share a rule. An export run twice and
    concatenated produces identical rows, and dropping the repeat loses nothing. Two rows
    with one key and different values mean somebody has two answers for one order line,
    and picking either is inventing the answer - so it is fatal and both line numbers are
    printed, because the fix needs both.
    """
    first: dict[tuple, Row] = {}
    out: list[Row] = []
    problems: list[Problem] = []
    duplicates = 0
    for row in rows:
        identity = key(row)
        previous = first.get(identity)
        if previous is None:
            first[identity] = row
            out.append(row)
        elif previous.values == row.values:
            duplicates += 1
        else:
            differing = sorted(k for k in set(previous.values) | set(row.values)
                               if previous.values.get(k) != row.values.get(k))
            problems.append(Problem(
                file, row.line, None, "conflicting_duplicate",
                "the same key as line %d, with different values for: %s. Approv will not "
                "choose between them." % (previous.line, ", ".join(differing))))
    if duplicates:
        problems.append(Problem(file, None, None, "duplicate_rows",
                                "%d row(s) repeated an earlier row exactly and were "
                                "counted once" % duplicates, Severity.NOTE))
    return out, problems


def expand_dotted(values: Mapping[str, Any]) -> dict:
    """`variant.size` in a flat CSV becomes a nested snapshot.

    A catalogue is nested and a spreadsheet is not, so a CSV catalogue export writes the
    path into the column name. Reading it back is the only way a partner who has no JSON
    export can supply a snapshot at all.
    """
    out: dict = {}
    for key, value in values.items():
        target = out
        parts = key.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
            if not isinstance(target, dict):
                raise ValueError("`%s` is both a value and a container" % part)
        target[parts[-1]] = value
    return out


def read_json_rows(path: Path) -> tuple[list[Row], list[Problem]]:
    """A JSON array, a JSON object keyed by id, or JSONL. All three turn up.

    Line numbers are real for JSONL and are the index within the document otherwise,
    which is the closest honest thing a JSON array has to one.
    """
    text, _, problems = decode(path)
    stripped = text.strip()
    if not stripped:
        return [], problems + [Problem(path.name, None, None, "empty_file",
                                       "the file has no content")]
    if stripped[0] in "[{":
        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError as error:
            return [], problems + [Problem(path.name, error.lineno, None, "unreadable",
                                           "invalid JSON: %s" % error.msg)]
        if isinstance(loaded, dict):
            return ([Row(index, dict(value, **{"_key": key}) if isinstance(value, dict)
                         else {"_key": key, "value": value})
                     for index, (key, value) in enumerate(loaded.items(), start=1)],
                    problems)
        return [Row(index, item) for index, item in enumerate(loaded, start=1)], problems

    rows = []
    for line, raw in enumerate(stripped.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            rows.append(Row(line, json.loads(raw)))
        except json.JSONDecodeError as error:
            problems.append(Problem(path.name, line, None, "unreadable",
                                    "invalid JSON: %s" % error.msg))
    return rows, problems


def fatal(problems: Sequence[Problem]) -> list[Problem]:
    return [p for p in problems if p.severity is Severity.FATAL]


def raise_if_fatal(problems: Sequence[Problem]) -> None:
    bad = fatal(problems)
    if bad:
        raise ExportRejected(bad)


def iter_files(directory: Path, stem: str) -> Iterator[Path]:
    """Every file in the export whose name starts with a known stem.

    A partner who exports `orders-2026-09.csv` and `orders-2026-10.csv` has sent one
    orders table in two files, and asking them to concatenate it first is asking them to
    do work that this can do correctly.
    """
    for path in sorted(directory.iterdir()):
        if path.is_file() and normalise(path.stem).startswith(normalise(stem)):
            yield path
