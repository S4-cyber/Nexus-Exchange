"""Execute zero-cost local work on CSV files placed in Scout's dedicated inbox."""
import csv
from hashlib import sha256
import io
from itertools import islice
import os
from pathlib import Path
import re
import stat
from .digital_deliverable import (MAX_INPUT_BYTES, MAX_ROWS, MAX_COLUMNS, MAX_OUTPUT_BYTES, PROFILE_COLUMNS,
                                  DeliverableError, _cell, _permit, _profile_rows, _verify_profile, _serialize, _table)
from .deliverable_files import read_selected_csv, publish_new_csv

INBOX = "Scout Inbox"
OUTPUTS = "Scout Outputs"


def folder(directory, name):
    if name not in (INBOX, OUTPUTS):
        raise ValueError("Unknown work folder.")
    path = Path(directory).resolve() / name
    path.mkdir(exist_ok=True)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or path.is_symlink()
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError("Expected a local work directory.")
    return path


def profile_csv(raw, stopped):
    if not 0 < len(raw) <= MAX_INPUT_BYTES:
        raise DeliverableError("CSV_BYTE_LIMIT")
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    cols = next(reader, [])
    if (not 1 <= len(cols) <= MAX_COLUMNS or len(set(cols)) != len(cols)
            or not all(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", col) for col in cols)):
        raise DeliverableError("INVALID_COLUMN_SCHEMA")
    records = {}
    for index, row in enumerate(reader):
        _permit(False, stopped)
        if index >= MAX_ROWS or len(row) != len(cols):
            raise DeliverableError("CSV_ROW_LIMIT_OR_WIDTH")
        records[index] = tuple(_cell(cell) for cell in row)
    if not records:
        raise DeliverableError("CSV_NO_ROWS")
    spec = dict(columns=cols)
    output = _profile_rows(spec, records, False, stopped)
    schema = dict(columns=list(PROFILE_COLUMNS), key_column="column", expected_rows=len(cols))
    artifact = _serialize(schema, output, False, stopped)
    checked = _table(artifact, schema, maximum=MAX_OUTPUT_BYTES, ordered=True, halted=False, halt_check=stopped)
    _verify_profile(spec, records, checked, False, stopped)
    return artifact


def run_files(directory, stopped):
    inbox, out = folder(directory, INBOX), folder(directory, OUTPUTS)
    counts = dict(produced=0, existing=0, held=0, full=False)
    with os.scandir(inbox) as scan:
        entries = list(islice(scan, 129))
    if len(entries) > 128:
        counts["full"] = True
        return counts
    for entry in entries:
        _permit(False, stopped)
        path = Path(entry.path)
        if path.suffix.lower() != ".csv":
            continue
        try:
            raw = read_selected_csv(path, halted=False, halt_check=stopped)
            artifact = profile_csv(raw, stopped)
            prefix = re.sub(r"[^A-Za-z0-9_-]", "_", path.stem)[:32] or "file"
            dest = out / (prefix + "-quality-" + sha256(raw).hexdigest()[:16] + ".csv")
            if os.path.lexists(dest):
                if read_selected_csv(dest, halted=False, halt_check=stopped) != artifact:
                    raise DeliverableError("OUTPUT_CONTENT_CHANGED")
                counts["existing"] += 1
            else:
                publish_new_csv(dest, artifact, halted=False, halt_check=stopped)
                counts["produced"] += 1
        except (ValueError, csv.Error, OSError):
            _permit(False, stopped)
            counts["held"] += 1
    return counts
