"""Local filtering of already validated historical receipt projections."""
import re


def normalize_history_query(query):
    if type(query) is not str or len(query) > 256 or not query.isascii():
        raise ValueError("bounded hexadecimal history query required")
    query = query.strip(' ').lower()
    if query and re.fullmatch(r'[0-9a-f]{8,64}', query) is None:
        raise ValueError("enter 8 to 64 hexadecimal characters or leave blank")
    return query


def filter_history(rows, query):
    """Filter validated rows, retaining full-index lineage counts and order."""
    query = normalize_history_query(query)
    if type(rows) is not list or len(rows) > 64:
        raise ValueError("historical search batch exceeds budget")
    return [dict(row) for row in rows if not query or any(
        row[key].startswith(query) for key in
        ('receipt_sha256', 'scope_sha256', 'snapshot_sha256'))]
