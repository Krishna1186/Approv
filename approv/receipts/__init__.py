"""Signed, hash-chained comparison records.

The record is the product. UAP, AP2 and ACP all sign *who paid*; this signs *what was
asked for and why it was allowed*, which is a different object and the one nobody else
in the chain is producing.
"""

from approv.receipts.record import VERSION, build_record, completeness, floor_is_met

__all__ = ["VERSION", "build_record", "completeness", "floor_is_met"]
