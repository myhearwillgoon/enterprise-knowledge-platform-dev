"""Query tests for pdf-table-search (phase P3, consolidated P4).

Subprocess-level coverage of the installed ``pdf-table-search query`` CLI
(invoked through the shared ``run_cli`` fixture in ``conftest.py``, which
resolves the real console script), backing gate G2 (keyword search over
extracted tables) and the query-side of G3:

* known match            -> one JSONL line with source/page/row_index/row
* case-insensitivity     -> uppercase keyword matches mixed-case cell
* every cell + multi-file -> a substring in a later column matches, across two
  files, with per-file ``page`` values
* zero matches           -> exit 0 with empty stdout
* no extracted files     -> exit 0 with empty stdout
* suffix filtering       -> non ``.tables.json`` files are ignored
* non-recursive scan     -> a ``.tables.json`` in a subdirectory is not read
* malformed file skip    -> an unreadable extracted file is skipped, not fatal

Plus a true end-to-end test (``test_end_to_end_extract_then_query_finds_keyword``)
that runs ``extract`` on a real fixture PDF, persists the JSON output as a
``*.tables.json`` artifact, then runs ``query`` over it -- proving the two
subcommands compose (G1's real output is consumable by G2), beyond the
hand-authored query fixtures used by the other cases.

Per the phase risk_notes the contract is narrow: direct-child ``*.tables.json``
files, case-insensitive substring over cell values, JSONL output. These tests
pin that contract without exercising extraction (kept decoupled) except for the
single end-to-end composition test.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "query"
EXTRACT_FIXTURES = Path(__file__).parent / "fixtures"


def _parse_jsonl(stdout: str) -> list[dict]:
    """Parse non-empty stdout lines as one JSON object per line (JSONL)."""
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def test_query_known_match_emits_valid_jsonl_with_required_fields(run_cli) -> None:
    result = run_cli("query", str(FIXTURES), "alice")
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


def test_query_is_case_insensitive(run_cli) -> None:
    # An all-uppercase keyword must match a mixed-case cell value.
    result = run_cli("query", str(FIXTURES), "ALICE")
    assert result.returncode == 0

    matches = _parse_jsonl(result.stdout)
    assert len(matches) == 1
    assert matches[0]["row"] == ["Alice", "30", "Beijing"]


def test_query_matches_every_cell_across_multiple_files(run_cli) -> None:
    # "sh" appears in a later column ("Shanghai", 3rd cell of the Bob row) in
    # people.tables.json and in "Shipped" in orders.tables.json. Matching a
    # 3rd-column cell proves every cell is searched, not just the first; two
    # files prove multi-file scanning; differing page values prove the page
    # field is reported per table. Files are scanned in sorted basename order
    # (orders before people), so match order is deterministic.
    result = run_cli("query", str(FIXTURES), "sh")
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


def test_query_zero_matches_exits_0_with_empty_stdout(run_cli) -> None:
    # A keyword absent from every cell: exit 0, empty stdout (not an error).
    result = run_cli("query", str(FIXTURES), "zzznomatch")
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_query_directory_with_no_extracted_files_exits_0_empty_stdout(
    run_cli, tmp_path: Path
) -> None:
    # G3 must_have: a query directory with no extracted files exits 0 with
    # empty stdout.
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result = run_cli("query", str(empty_dir), "anything")
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_query_ignores_non_tables_json_files(run_cli, tmp_path: Path) -> None:
    # Files that do not end in .tables.json are not scanned.
    (tmp_path / "notes.txt").write_text("alice alice", encoding="utf-8")
    (tmp_path / "readme.md").write_text("# alice", encoding="utf-8")
    result = run_cli("query", str(tmp_path), "alice")
    assert result.returncode == 0
    assert result.stdout == ""


def test_query_is_non_recursive(run_cli, tmp_path: Path) -> None:
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
    result = run_cli("query", str(tmp_path), "secret")
    assert result.returncode == 0
    assert result.stdout == ""
    assert "Traceback" not in result.stdout


def test_query_skips_malformed_tables_file_without_crashing(
    run_cli, tmp_path: Path
) -> None:
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
    result = run_cli("query", str(tmp_path), "alice")
    assert result.returncode == 0
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr

    matches = _parse_jsonl(result.stdout)
    assert len(matches) == 1
    assert matches[0]["source"] == "good.tables.json"
    assert matches[0]["row"] == ["Alice", "Beijing"]


def test_end_to_end_extract_then_query_finds_keyword(
    run_cli, tmp_path: Path
) -> None:
    # Phase P4 "End-To-End Gate Coverage": prove the two subcommands compose by
    # running the real installed `extract` CLI on a fixture PDF, persisting its
    # JSON output as a *.tables.json artifact (the on-disk contract query reads),
    # then running the real `query` CLI over that directory and asserting the
    # JSONL match shape. Unlike the hand-authored query fixtures above, the
    # artifact here is produced by `extract` itself, so G1's real output is
    # shown to be consumable by G2.
    extract_result = run_cli("extract", str(EXTRACT_FIXTURES / "table.pdf"))
    assert extract_result.returncode == 0
    assert "Traceback" not in extract_result.stdout

    tables = json.loads(extract_result.stdout)
    assert isinstance(tables, list)
    assert len(tables) == 1
    # The persisted artifact is exactly what `extract` printed.
    artifact = tmp_path / "table.tables.json"
    artifact.write_text(extract_result.stdout, encoding="utf-8")

    query_result = run_cli("query", str(tmp_path), "alice")
    assert query_result.returncode == 0
    assert query_result.stderr == ""
    assert "Traceback" not in query_result.stdout

    matches = _parse_jsonl(query_result.stdout)
    assert len(matches) == 1

    match = matches[0]
    assert set(match.keys()) == {"source", "page", "row_index", "row"}
    assert match["source"] == "table.tables.json"
    assert match["page"] == 1
    assert match["row_index"] == 1
    assert match["row"] == ["Alice", "30", "Beijing"]
