---
project: pdf-table-search
codex_model: gpt-5.5
max_retries: 3
scope_globs:
  - "src/**/*.py"
  - "tests/**/*.py"
forbidden_globs:
  - "src/contracts/**"
  - "tests/acceptance/**"
gates:
  - id: G1
    description: |
      CLI accepts a path to a PDF file and outputs a JSON array of detected tables.
      Each table has: page_number (int), bbox (list of 4 floats x0,y0,x1,y1),
      row_count (int), col_count (int), header_row (list of strings or null).
    must_have:
      - "CLI command: `pdf-table-search extract <file.pdf>` exits 0 on valid input"
      - "Output is valid JSON parseable by `json.loads`"
      - "Empty PDFs return `[]`, not an error"
  - id: G2
    description: |
      A second CLI subcommand searches across all extracted tables in a directory
      for cell values containing a keyword (case-insensitive substring match).
    must_have:
      - "CLI command: `pdf-table-search query <dir> <keyword>` exits 0"
      - "Output includes: source file, page, row index, full row contents (as a list)"
      - "Output is one JSON object per match, one per line (JSONL)"
      - "Zero matches exits 0 with empty output (NOT an error)"
  - id: G3
    description: |
      Both commands handle adversarial inputs without crashing.
    must_have:
      - "Non-existent file → exits 2 with a clear stderr message containing 'not found'"
      - "Corrupted PDF → exits 3 with a clear stderr message; does not stack-trace to stdout"
      - "PDF with no tables → exits 0 with output `[]`"
      - "Query directory with no extracted files → exits 0 with empty output"
  - id: G4
    description: |
      Test coverage with pytest, including the adversarial cases from G3.
    must_have:
      - "`pytest tests/ -v` exits 0"
      - "Tests cover happy path for G1, G2, and all four adversarial cases in G3"
      - "Tests run in under 30 seconds total"
---

# PDF Table Extraction + Keyword Search CLI

## Context

This is a sample build.md for the `lenovo-ekp` skill — a structurally realistic but generic spec used to exercise the Plan→Build→Review→Accept pipeline end to end. The actual logic (PDF table extraction) is intentionally small enough to fit in one MVP run but large enough to need ≥2 phases.

## Functional requirements

We need a Python CLI tool, `pdf-table-search`, with two subcommands:

### `extract <file.pdf>`
Detect and emit tables from a single PDF as a JSON array (see Gate G1 for exact shape). Use any reasonable library (e.g., `pdfplumber`, `camelot-py`, `tabula-py`). Library choice is left to the Plan phase.

### `query <directory> <keyword>`
Walk a directory of previously-extracted JSON files (assume they sit at `<directory>/<original_filename>.tables.json`) and emit one JSONL line per row that contains the keyword in any cell. Case-insensitive substring match.

## Non-functional requirements

- Python 3.10+
- Single `pyproject.toml` declaring dependencies
- Idiomatic CLI using `argparse` or `click` — either is fine
- No network access at runtime (the tool processes local PDFs only)
- Exit codes are part of the API: 0=success, 2=input not found, 3=corrupted input

## Out of scope

- No OCR (rasterized PDFs are out of scope for this gate set)
- No web UI, no API server
- No multi-page table reassembly (each detected table belongs to exactly one page)
- No fuzzy search or relevance ranking — exact case-insensitive substring is enough

## Gate verification hints (for the Plan phase)

- G1 can be tested by running `extract` on a small fixture PDF with known tables and asserting on the JSON output structure
- G2 can be tested by running `extract` then `query` and asserting expected matches
- G3 fixtures: `nonexistent.pdf` (don't create it), `corrupted.pdf` (create as a text file renamed `.pdf`), and an empty real PDF
- G4 is met when `pytest tests/ -v` returns exit code 0 with assertions covering all of the above

## Notes for the planner

This spec has 4 gates and is naturally a 2- or 3-phase plan:
- Likely Phase 1: project skeleton + `extract` subcommand + G1 + G3 (extract-side)
- Likely Phase 2: `query` subcommand + G2 + G3 (query-side)
- Optional Phase 3: integration tests + G4 (if not folded into earlier phases)

The Plan phase decides; this is just a hint to the planner.
