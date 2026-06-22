"""Command-line interface for pdf-table-search.

Two subcommands share a single error boundary that maps domain errors to
stable exit codes and writes every diagnostic to stderr, so stdout is reserved
for data and never contains a traceback.

Exit codes (part of the public API, see ``build.md``):

* ``0``  - success
* ``2``  - input not found (missing path, or wrong filesystem type)
* ``3``  - corrupted / unreadable input
* ``70`` - unexpected internal error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from typing import Callable, Sequence

from .errors import (
    CorruptedInputError,
    InputNotFoundError,
    PdfTableSearchError,
)
from .extract import extract_tables
from .query import query_directory

EXIT_OK = 0
EXIT_NOT_FOUND = 2
EXIT_CORRUPTED = 3
EXIT_UNEXPECTED = 70

# A valid PDF starts with this byte signature. Used as a lightweight corruption
# guard at the CLI boundary before handing the file to pdfplumber; any parser
# failure on a signature-valid file is wrapped to CorruptedInputError by
# ``extract_tables`` so it still maps to exit 3 (not the catch-all exit 70).
_PDF_SIGNATURE = b"%PDF"


def cmd_extract(args: argparse.Namespace) -> int:
    """Handle ``pdf-table-search extract <file>``.

    Validates the input path, guards against non-PDF files, then delegates to
    :func:`pdf_table_search.extract.extract_tables` for table detection. A
    valid PDF with no tables yields an empty JSON array (``[]``).
    """
    path = args.file
    if not os.path.exists(path):
        raise InputNotFoundError(f"Input file not found: {path}")
    if not os.path.isfile(path):
        # Wrong filesystem type (e.g. a directory): still a "not found" input
        # from the caller's perspective. The message keeps the ``not found``
        # contract documented in errors.py / build.md G3.
        raise InputNotFoundError(f"Input file not found or not a regular file: {path}")
    try:
        with open(path, "rb") as handle:
            header = handle.read(len(_PDF_SIGNATURE))
    except OSError as exc:
        raise CorruptedInputError(f"Could not read input file: {path}") from exc
    if not header.startswith(_PDF_SIGNATURE):
        raise CorruptedInputError(f"Input is not a valid PDF (corrupted): {path}")
    # Detect and normalize tables; print a single JSON array to stdout.
    # extract_tables wraps pdfplumber parse failures as CorruptedInputError
    # (exit 3) and treats degenerate empty PDFs as a successful empty result.
    tables = extract_tables(path)
    sys.stdout.write(json.dumps(tables) + "\n")
    return EXIT_OK


def cmd_query(args: argparse.Namespace) -> int:
    """Handle ``pdf-table-search query <directory> <keyword>``.

    Validates the target directory, then searches every direct-child
    ``*.tables.json`` file for rows whose cells contain the keyword
    (case-insensitive substring). Each matching row is printed as one JSON
    object on its own line (JSONL) with ``source``/``page``/``row_index``/
    ``row`` fields. Zero matches -- including a directory with no extracted
    files -- yield empty stdout and exit 0 (not an error).
    """
    directory = args.directory
    if not os.path.exists(directory):
        raise InputNotFoundError(f"Query directory not found: {directory}")
    if not os.path.isdir(directory):
        # Wrong filesystem type (e.g. a file): still a "not found" input.
        raise InputNotFoundError(f"Query directory not found or not a directory: {directory}")
    # One JSON object per matching row, one per line (JSONL). An empty list
    # writes nothing, so zero-match / no-files cases keep stdout empty.
    for match in query_directory(directory, args.keyword):
        sys.stdout.write(json.dumps(match) + "\n")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser with both subcommands."""
    parser = argparse.ArgumentParser(
        prog="pdf-table-search",
        description="Extract tables from PDFs and search their cells by keyword.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser(
        "extract",
        help="Extract tables from a PDF as a JSON array.",
        description="Extract tables from a PDF and print a JSON array to stdout.",
    )
    extract_parser.add_argument("file", help="Path to the PDF file to extract.")
    extract_parser.set_defaults(func=cmd_extract)

    query_parser = subparsers.add_parser(
        "query",
        help="Search extracted tables for a keyword (JSONL output).",
        description="Search previously extracted tables for a keyword and print JSONL.",
    )
    query_parser.add_argument("directory", help="Directory of *.tables.json files.")
    query_parser.add_argument("keyword", help="Case-insensitive substring to match.")
    query_parser.set_defaults(func=cmd_query)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: parse args, run the chosen command, map errors to exits."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Callable[[argparse.Namespace], int] = args.func
    try:
        return handler(args)
    except InputNotFoundError as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_NOT_FOUND
    except CorruptedInputError as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_CORRUPTED
    except PdfTableSearchError as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_UNEXPECTED
    except Exception as exc:  # noqa: BLE001 - last-resort CLI boundary
        # Never leak a traceback to stdout; route it to stderr instead so the
        # data channel stays clean while still aiding diagnosis.
        sys.stderr.write(f"Unexpected error: {exc}\n")
        traceback.print_exc(file=sys.stderr)
        return EXIT_UNEXPECTED


if __name__ == "__main__":
    sys.exit(main())
