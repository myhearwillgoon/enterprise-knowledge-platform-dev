"""Extraction tests for pdf-table-search (phase P2).

Subprocess-level coverage of the installed ``pdf-table-search extract`` CLI,
backing gates G1 (table extraction schema) and the extract-side of G3:

* valid table PDF        -> JSON array with required field types, four-float
  bbox, positive row/column counts, and stable fixture row content.
* valid no-table PDF     -> exactly ``[]`` and exit 0.
* corrupted PDF          -> exit 3 with a clear stderr message and clean stdout.
* truncated PDF          -> signature-valid but malformed body -> exit 3
  (addresses the P1 review fix_hint: parse failures must not reach the
  catch-all exit 70).
* degenerate empty PDF   -> header + EOF only -> ``[]`` and exit 0 (the G3
  "valid PDF with no tables" contract for a signature-bearing, object-less
  document).

Per the phase risk_notes, assertions target schema, stable fixture content,
positive counts, and four-float bbox shape -- not pixel-perfect table
detection quality or exact bbox coordinates.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

COMMAND = ["pdf-table-search"]
FIXTURES = Path(__file__).parent / "fixtures"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(COMMAND + args, capture_output=True, text=True)


def test_extract_table_pdf_returns_json_array_with_required_fields() -> None:
    result = _run(["extract", str(FIXTURES / "table.pdf")])
    assert result.returncode == 0
    assert "Traceback" not in result.stdout

    tables = json.loads(result.stdout)
    assert isinstance(tables, list)
    assert len(tables) == 1

    table = tables[0]
    # Required field types (G1 schema).
    assert isinstance(table["page_number"], int)
    assert isinstance(table["bbox"], list)
    assert len(table["bbox"]) == 4
    assert all(isinstance(value, float) for value in table["bbox"])
    assert isinstance(table["row_count"], int)
    assert isinstance(table["col_count"], int)
    assert isinstance(table["header_row"], list)
    assert all(isinstance(cell, str) for cell in table["header_row"])
    assert isinstance(table["rows"], list)
    assert all(isinstance(row, list) for row in table["rows"])
    assert all(isinstance(cell, str) for row in table["rows"] for cell in row)

    # Positive row/column counts (stable structural values for this fixture).
    assert table["row_count"] > 0
    assert table["col_count"] > 0
    assert table["row_count"] == len(table["rows"])
    assert table["col_count"] == max(len(row) for row in table["rows"])

    # Stable fixture row content (deterministic, not extraction fidelity).
    assert table["page_number"] == 1
    assert table["row_count"] == 4
    assert table["col_count"] == 3
    assert table["header_row"] == ["Name", "Age", "City"]
    assert table["rows"] == [
        ["Name", "Age", "City"],
        ["Alice", "30", "Beijing"],
        ["Bob", "25", "Shanghai"],
        ["Carol", "41", "Guangzhou"],
    ]


def test_extract_no_tables_pdf_prints_empty_list() -> None:
    result = _run(["extract", str(FIXTURES / "no_tables.pdf")])
    assert result.returncode == 0
    assert result.stdout == "[]\n"
    assert result.stderr == ""
    assert "Traceback" not in result.stdout


def test_extract_corrupted_pdf_exits_3() -> None:
    # Canonical G3 corrupted fixture: a text file renamed .pdf (no %PDF
    # signature), rejected by the CLI signature guard.
    result = _run(["extract", str(FIXTURES / "corrupted.pdf")])
    assert result.returncode == 3
    assert result.stdout == ""
    assert "Traceback" not in result.stdout
    assert "corrupted" in result.stderr.lower()


def test_extract_truncated_pdf_exits_3() -> None:
    # Signature-valid but malformed body: pdfplumber cannot parse it, so
    # extract_tables wraps the failure as CorruptedInputError (exit 3) rather
    # than letting the library exception escape to the catch-all (exit 70).
    # This is the case flagged by the P1 review fix_hint.
    result = _run(["extract", str(FIXTURES / "truncated.pdf")])
    assert result.returncode == 3
    assert result.stdout == ""
    assert "Traceback" not in result.stdout
    assert "corrupted" in result.stderr.lower()


def test_extract_degenerate_empty_pdf_prints_empty_list(tmp_path: Path) -> None:
    # A signature-bearing but object-less PDF (header + EOF only) has no pages
    # and no tables. It is treated as a successful empty result (``[]``) under
    # the G3 "valid PDF with no tables" contract, not as corrupted.
    pdf = tmp_path / "degenerate.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    result = _run(["extract", str(pdf)])
    assert result.returncode == 0
    assert result.stdout == "[]\n"
    assert "Traceback" not in result.stdout
