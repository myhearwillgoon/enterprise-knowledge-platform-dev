"""Query tests for pdf-table-search (phase P3).

Subprocess-level coverage of the installed ``pdf-table-search query`` CLI,
backing gate G2 (keyword search over extracted tables) and the query-side of
G3:

* known match            -> one JSONL line with source/page/row_index/row
* case-insensitivity     -> uppercase keyword matches mixed-case cell
* every cell + multi-file -> a substring in a later column matches, across two
  files, with per-file ``page`` values
* zero matches           -> exit 0 with empty stdout
* no extracted files     -> exit 0 with empty stdout
* suffix filtering       -> non ``.tables.json`` files are ignored
* non-recursive scan     -> a ``.tables.json`` in a subdirectory is not read
* malformed file skip    -> an unreadable extracted file is skipped, not fatal

Per the phase risk_notes the contract is narrow: direct-child ``*.tables.json``
files, case-insensitive substring over cell values, JSONL output. These tests
pin that contract without exercising extraction (kept decoupled).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

COMMAND = ["pdf-table-search"]
FIXTURES = Path(__file__).parent / "fixtures" / "query"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(COMMAND + args, capture_output=True, text=True)


def _parse_jsonl(stdout: str) -> list[dict]:
    """Parse non-empty stdout lines as one JSON object per line (JSONL)."""
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def test_query_known_match_emits_valid_jsonl_with_required_fields() -> None:
    result = _run(["query", str(FIXTURES), "alice"])
    assert result.returncode == 0
    assert result.stderr == ""
    assert "Traceback" not in result.stdout

    matches = _parse_jsonl(result.stdout)
    assert len(matches) == 1

    match = matches[0]
    # G2 must_have: source, page, row index, full row contents (as a list).
    assert set(match.keys()) == {"source", "page", "row_index", "row"}
    assert match["source"] == "people.tables.json"
    assert match["page"] == 1
    assert match["row_index"] == 1
    assert match["row"] == ["Alice", "30", "Beijing"]


def test_query_is_case_insensitive() -> None:
    # An all-uppercase keyword must match a mixed-case cell value.
    result = _run(["query", str(FIXTURES), "ALICE"])
    assert result.returncode == 0

    matches = _parse_jsonl(result.stdout)
    assert len(matches) == 1
    assert matches[0]["row"] == ["Alice", "30", "Beijing"]


def test_query_matches_every_cell_across_multiple_files() -> None:
    # "sh" appears in a later column ("Shanghai", 3rd cell of the Bob row) in
    # people.tables.json and in "Shipped" in orders.tables.json. Matching a
    # 3rd-column cell proves every cell is searched, not just the first; two
    # files prove multi-file scanning; differing page values prove the page
    # field is reported per table. Files are scanned in sorted basename order
    # (orders before people), so match order is deterministic.
    result = _run(["query", str(FIXTURES), "sh"])
    assert result.returncode == 0
    assert "Traceback" not in result.stdout

    matches = _parse_jsonl(result.stdout)
    assert len(matches) == 2

    assert matches[0]["source"] == "orders.tables.json"
    assert matches[0]["page"] == 2
    assert matches[0]["row_index"] == 1
    assert matches[0]["row"] == ["ORD-001", "Shipped"]

    assert matches[1]["source"] == "people.tables.json"
    assert matches[1]["page"] == 1
    assert matches[1]["row_index"] == 2
    assert matches[1]["row"] == ["Bob", "25", "Shanghai"]


def test_query_zero_matches_exits_0_with_empty_stdout() -> None:
    # A keyword absent from every cell: exit 0, empty stdout (not an error).
    result = _run(["query", str(FIXTURES), "zzznomatch"])
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_query_directory_with_no_extracted_files_exits_0_empty_stdout(tmp_path: Path) -> None:
    # G3 must_have: a query directory with no extracted files exits 0 with
    # empty stdout.
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result = _run(["query", str(empty_dir), "anything"])
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_query_ignores_non_tables_json_files(tmp_path: Path) -> None:
    # Files that do not end in .tables.json are not scanned.
    (tmp_path / "notes.txt").write_text("alice alice", encoding="utf-8")
    (tmp_path / "readme.md").write_text("# alice", encoding="utf-8")
    result = _run(["query", str(tmp_path), "alice"])
    assert result.returncode == 0
    assert result.stdout == ""


def test_query_is_non_recursive(tmp_path: Path) -> None:
    # A .tables.json file nested in a subdirectory must NOT be read; only
    # direct children are scanned.
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "hidden.tables.json").write_text(
        json.dumps(
            [
                {
                    "page_number": 5,
                    "rows": [["secret", "value"]],
                }
            ]
        ),
        encoding="utf-8",
    )
    result = _run(["query", str(tmp_path), "secret"])
    assert result.returncode == 0
    assert result.stdout == ""
    assert "Traceback" not in result.stdout


def test_query_skips_malformed_tables_file_without_crashing(tmp_path: Path) -> None:
    # Per the plan's adversarial resolution, a malformed extracted file is
    # skipped defensively rather than crashing. A valid sibling file is still
    # searched, so its match appears and the bad file contributes nothing.
    (tmp_path / "bad.tables.json").write_text("{not valid json", encoding="utf-8")
    (tmp_path / "good.tables.json").write_text(
        json.dumps(
            [
                {
                    "page_number": 1,
                    "rows": [["Name", "City"], ["Alice", "Beijing"]],
                }
            ]
        ),
        encoding="utf-8",
    )
    result = _run(["query", str(tmp_path), "alice"])
    assert result.returncode == 0
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr

    matches = _parse_jsonl(result.stdout)
    assert len(matches) == 1
    assert matches[0]["source"] == "good.tables.json"
    assert matches[0]["row"] == ["Alice", "Beijing"]
