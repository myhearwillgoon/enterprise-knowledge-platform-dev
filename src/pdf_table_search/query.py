"""Keyword search over previously extracted table JSON files.

This module is deliberately decoupled from PDF parsing: it consumes only the
``*.tables.json`` artifacts that ``pdf-table-search extract`` (or any
compatible producer) writes. Each such file is a JSON array of table records
carrying at least ``page_number`` (int) and ``rows`` (list of list of str), as
produced by :mod:`pdf_table_search.extract`.

The search contract (build.md G2) is intentionally narrow, per the phase
risk_notes (no indexing, ranking, regex, SQLite, or pandas):

* Scan only direct-child ``*.tables.json`` files in the given directory
  (non-recursive -- subdirectories are ignored).
* Case-insensitive substring match across every cell value in every row of
  every table.
* Emit one match dict per matching row with fields ``source`` (basename of the
  scanned file), ``page`` (the table's ``page_number``), ``row_index``
  (0-based position of the row within the table's ``rows`` list), and ``row``
  (the full row as a list of strings).
* Zero matches -- including a directory with no extracted files -- yield an
  empty result (the CLI prints nothing and exits 0).

Per the plan's adversarial resolution, malformed extracted files are skipped
defensively rather than crashing or mapping to an exit code: G2/G3 do not
specify malformed-file behavior, so it stays out of scope as a gate.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterator

# Suffix that identifies an extracted-tables artifact. The scan matches only
# direct children whose name ends with this suffix.
TABLES_SUFFIX = ".tables.json"


def _iter_table_files(directory: str) -> Iterator[str]:
    """Yield direct-child ``*.tables.json`` file paths in sorted order.

    Sorting makes match order deterministic across platforms and filesystems
    (which may list entries in different orders). The scan is non-recursive:
    only files immediately inside ``directory`` are considered, so a
    ``.tables.json`` file nested in a subdirectory is never read. A directory
    entry that happens to be named ``*.tables.json`` is also skipped, because
    ``os.path.isfile`` is false for directories.
    """
    try:
        entries = sorted(os.listdir(directory))
    except OSError:
        # Directory vanished or is unreadable between the CLI's isdir check
        # and the listdir; treat as "no files" rather than crashing.
        return
    for name in entries:
        if not name.endswith(TABLES_SUFFIX):
            continue
        full = os.path.join(directory, name)
        if os.path.isfile(full):
            yield full


def _matching_rows(
    source: str, tables: Any, keyword: str
) -> Iterator[dict[str, Any]]:
    """Yield one match dict per row containing the case-insensitive keyword.

    ``tables`` is the parsed contents of a single ``*.tables.json`` file: a
    list of table records. Records (or rows) that are not the expected shape
    are skipped defensively -- malformed-file behavior is not a gate (see the
    module docstring). ``row_index`` is the 0-based position of the row within
    its table's ``rows`` list, so ``rows[row_index]`` reconstructs ``row``.
    """
    keyword_lower = keyword.lower()
    if not isinstance(tables, list):
        return
    for table in tables:
        if not isinstance(table, dict):
            continue
        rows = table.get("rows")
        if not isinstance(rows, list):
            continue
        page = table.get("page_number")
        for row_index, row in enumerate(rows):
            if not isinstance(row, list):
                continue
            cells = [str(cell) for cell in row]
            if any(keyword_lower in cell.lower() for cell in cells):
                yield {
                    "source": source,
                    "page": page,
                    "row_index": row_index,
                    "row": cells,
                }


def query_directory(directory: str, keyword: str) -> list[dict[str, Any]]:
    """Search every direct-child ``*.tables.json`` file in ``directory``.

    Returns a list of match dicts (each with ``source``/``page``/
    ``row_index``/``row``) in stable order: sorted by source file, then table
    order, then row order. Malformed or unreadable files are skipped without
    raising. The caller (CLI) prints each match as one JSON line (JSONL).

    Parameters
    ----------
    directory:
        Path to a directory of extracted ``*.tables.json`` files. The caller
        (CLI) is expected to have already verified the path exists and is a
        directory.
    keyword:
        Case-insensitive substring to match against every cell value.
    """
    matches: list[dict[str, Any]] = []
    for path in _iter_table_files(directory):
        source = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                tables = json.load(handle)
        except (OSError, ValueError):
            # Malformed JSON or unreadable extracted file: skip defensively
            # per the plan's adversarial resolution (not a gate).
            continue
        matches.extend(_matching_rows(source, tables, keyword))
    return matches


__all__ = ["query_directory"]
