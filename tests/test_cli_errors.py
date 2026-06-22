"""CLI error-boundary tests for pdf-table-search (phase P1).

Exercises the installed ``pdf-table-search`` console script via subprocess to
verify exit codes, stderr messages, and that stdout never contains a traceback.

These tests back the four G3 must_haves:

* non-existent file       -> exit 2, stderr contains ``not found``
* corrupted PDF           -> exit 3, stdout clean (no traceback)
* PDF with no tables      -> exit 0, stdout is ``[]``
* query dir, no extracts  -> exit 0, empty stdout

plus the adjacent wrong-type input branches (directory to ``extract``, file to
``query``) which share the same exit-2 / ``not found`` contract.
"""

from __future__ import annotations

import subprocess

COMMAND = ["pdf-table-search"]


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(COMMAND + args, capture_output=True, text=True)


def test_help_lists_subcommands() -> None:
    result = _run(["--help"])
    assert result.returncode == 0
    assert "extract" in result.stdout
    assert "query" in result.stdout


def test_extract_nonexistent_file_exits_2() -> None:
    result = _run(["extract", "/nonexistent/path/missing.pdf"])
    assert result.returncode == 2
    assert "not found" in result.stderr
    assert "Traceback" not in result.stdout


def test_extract_nonexistent_file_keeps_stdout_clean(tmp_path) -> None:
    result = _run(["extract", str(tmp_path / "does_not_exist.pdf")])
    assert result.returncode == 2
    assert result.stdout == ""
    assert "not found" in result.stderr


def test_extract_directory_target_exits_2(tmp_path) -> None:
    # An existing directory passed to extract is the wrong type of input and
    # must be rejected with exit 2 and a `not found` diagnostic.
    result = _run(["extract", str(tmp_path)])
    assert result.returncode == 2
    assert "not found" in result.stderr
    assert result.stdout == ""
    assert "Traceback" not in result.stdout


def test_query_nonexistent_directory_exits_2() -> None:
    result = _run(["query", "/nonexistent/path/empty_dir", "keyword"])
    assert result.returncode == 2
    assert "not found" in result.stderr
    assert "Traceback" not in result.stdout


def test_query_file_target_exits_2(tmp_path) -> None:
    # An existing file passed to query is the wrong type of input and must be
    # rejected with exit 2 and a `not found` diagnostic.
    target = tmp_path / "not_a_directory.txt"
    target.write_text("hello", encoding="utf-8")
    result = _run(["query", str(target), "keyword"])
    assert result.returncode == 2
    assert "not found" in result.stderr
    assert result.stdout == ""
    assert "Traceback" not in result.stdout


def test_extract_corrupted_file_exits_3(tmp_path) -> None:
    corrupted = tmp_path / "corrupted.pdf"
    corrupted.write_text("this is not a pdf", encoding="utf-8")
    result = _run(["extract", str(corrupted)])
    assert result.returncode == 3
    assert result.stdout == ""
    assert "Traceback" not in result.stdout


def test_extract_valid_pdf_outputs_empty_list(tmp_path) -> None:
    # G3 must_have: a PDF with no tables exits 0 with stdout `[]`. A minimal
    # valid PDF (correct signature, no tables) exercises this.
    pdf = tmp_path / "empty.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    result = _run(["extract", str(pdf)])
    assert result.returncode == 0
    assert result.stdout == "[]\n"
    assert result.stderr == ""
    assert "Traceback" not in result.stdout


def test_query_empty_directory_outputs_nothing(tmp_path) -> None:
    # G3 must_have: a query directory with no extracted files exits 0 with
    # empty stdout (not an error).
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    result = _run(["query", str(empty_dir), "keyword"])
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert "Traceback" not in result.stdout
