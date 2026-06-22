"""PDF table extraction and normalization for pdf-table-search.

This module is the only place that talks to ``pdfplumber``. It exposes a single
function, :func:`extract_tables`, which reads a local PDF and returns a list of
JSON-serializable table records. The CLI boundary in :mod:`pdf_table_search.cli`
calls this function and prints its result; the query subcommand (added in a
later phase) consumes the persisted JSON.

Each returned table record contains the Gate-G1 required fields plus an
implementation-extension ``rows`` field that downstream keyword search needs
(G1 defines metadata only; G2 must search row contents):

* ``page_number`` -- 1-indexed page that owns the table (int)
* ``bbox``        -- ``[x0, top, x1, bottom]`` as four floats
* ``row_count``   -- number of extracted rows (int)
* ``col_count``   -- number of columns, derived from the widest row (int)
* ``header_row``  -- first non-empty row (list of str), or ``None`` if the
  table has no non-empty row (deterministic MVP rule; semantic header
  inference is intentionally out of scope)
* ``rows``        -- every extracted row as a list of lists of str

Corruption handling follows the CLI exit-code contract: any ``pdfplumber`` /
``pdfminer`` parse failure is wrapped in :class:`~pdf_table_search.errors.CorruptedInputError`
(exit 3) so library exceptions never escape to the CLI's catch-all (which would
exit 70). The single deliberate exception is a *degenerate empty PDF* -- a file
whose only content is a ``%PDF`` header and a ``%%EOF`` marker (no objects, no
pages, no tables). Such a file carries no tables, so it is treated as a
successful empty result (``[]``) rather than corrupt. This keeps the
"valid PDF with no tables -> ``[]``" contract (G3) intact for signature-bearing
degenerate PDFs while still mapping genuinely truncated/malformed PDFs to
exit 3, as required by the P1 review fix_hint.
"""

from __future__ import annotations

import re
from typing import Any

import pdfplumber

from .errors import CorruptedInputError

# A PDF header line, e.g. ``%PDF-1.4``. Used by the degenerate-empty check.
_PDF_HEADER_RE = re.compile(rb"%PDF-\d+\.\d+")
# The end-of-file marker that terminates a PDF stream.
_PDF_EOF_MARKER = b"%%EOF"


def _normalize_cell(cell: Any) -> str:
    """Normalize a single extracted cell to a stripped string.

    ``pdfplumber`` returns ``None`` for empty cells; we coerce those to ``""``
    so every cell in the output JSON is a string (stable, typed schema).
    """
    if cell is None:
        return ""
    return str(cell).strip()


def _normalize_rows(raw_rows: list[list[Any]]) -> list[list[str]]:
    """Normalize a 2-D matrix of raw cells into lists of stripped strings."""
    return [[_normalize_cell(cell) for cell in row] for row in raw_rows]


def _first_non_empty_row(rows: list[list[str]]) -> list[str] | None:
    """Return the first row containing at least one non-empty cell, else None.

    This is the deterministic MVP header rule agreed in the plan: the first
    non-empty extracted row is treated as ``header_row``. Semantic header
    detection is deliberately out of scope (and underspecified by G1).
    """
    for row in rows:
        if any(cell for cell in row):
            return list(row)
    return None


def _is_degenerate_empty_pdf(path: str) -> bool:
    """True if ``path`` is a signature-bearing but object-less PDF.

    A file that starts with ``%PDF`` and, after stripping the header line and
    any ``%%EOF`` markers, contains only whitespace, has no PDF objects, pages,
    or tables. Such a degenerate document is treated as a valid empty PDF
    (``[]``) rather than corrupt. Any remaining non-whitespace content means
    the file has a malformed body and is genuinely truncated/corrupt.

    The check is defensive: read failures or non-``%PDF`` files return
    ``False`` so the caller falls through to the corrupted-input path.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        return False
    if not raw.startswith(b"%PDF"):
        return False
    stripped = _PDF_HEADER_RE.sub(b"", raw, count=1)
    stripped = stripped.replace(_PDF_EOF_MARKER, b"")
    return stripped.strip() == b""


def _extract_from_pdf(pdf: pdfplumber.PDF, path: str) -> list[dict[str, Any]]:
    """Walk every page of an open PDF and collect normalized table records."""
    tables: list[dict[str, Any]] = []
    for page_index, page in enumerate(pdf.pages, start=1):
        try:
            found = page.find_tables()
        except Exception as exc:  # per-page table detection failure
            raise CorruptedInputError(
                f"Could not parse tables on page {page_index} of PDF: {path}"
            ) from exc
        for table in found:
            raw_rows = table.extract() or []
            rows = _normalize_rows(raw_rows)
            header_row = _first_non_empty_row(rows)
            bbox = [float(value) for value in table.bbox]
            tables.append(
                {
                    "page_number": page_index,
                    "bbox": bbox,
                    "row_count": len(rows),
                    "col_count": max((len(row) for row in rows), default=0),
                    "header_row": header_row,
                    "rows": rows,
                }
            )
    return tables


def extract_tables(path: str) -> list[dict[str, Any]]:
    """Read a PDF file and return its tables as JSON-serializable records.

    Parameters
    ----------
    path:
        Path to a local PDF file. The caller (CLI) is expected to have already
        verified the path exists and is a regular file.

    Returns
    -------
    list[dict]
        One record per detected table; empty list for a valid PDF with no
        tables (including degenerate header-only PDFs).

    Raises
    ------
    CorruptedInputError
        If the file cannot be parsed as a PDF (exit 3 at the CLI boundary).
    """
    try:
        with pdfplumber.open(path) as pdf:
            return _extract_from_pdf(pdf, path)
    except CorruptedInputError:
        raise
    except Exception as exc:
        # pdfplumber/pdfminer could not parse the file. A degenerate empty
        # PDF (header + EOF only) is a successful empty result, not corrupt;
        # everything else is a corrupted/unreadable PDF -> exit 3.
        if _is_degenerate_empty_pdf(path):
            return []
        raise CorruptedInputError(f"Input is not a valid PDF (corrupted): {path}") from exc


__all__ = ["extract_tables"]
