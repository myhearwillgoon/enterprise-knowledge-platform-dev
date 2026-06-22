"""Shared domain errors for the pdf-table-search CLI.

These error types are raised by command handlers and translated to stable
process exit codes by the CLI boundary in :mod:`pdf_table_search.cli`:

* :class:`InputNotFoundError`  -> exit code 2 (input file/directory missing)
* :class:`CorruptedInputError` -> exit code 3 (input exists but is unreadable)

Keeping the error hierarchy here (rather than inside ``cli.py``) lets later
phases raise the same errors from extraction/query code without importing the
CLI, and keeps the exit-code contract in exactly one place.
"""

from __future__ import annotations


class PdfTableSearchError(Exception):
    """Base class for all pdf-table-search domain errors."""


class InputNotFoundError(PdfTableSearchError):
    """A required input file or directory does not exist (or is the wrong type).

    Mapped to exit code 2. Per the CLI contract (build.md G3) the message is
    expected to contain the substring ``not found`` so callers and tests can
    rely on a stable diagnostic, regardless of whether the path is missing
    entirely or simply the wrong filesystem type (e.g. a directory passed to
    ``extract`` or a file passed to ``query``).
    """


class CorruptedInputError(PdfTableSearchError):
    """An input exists but cannot be parsed (for example a corrupted PDF).

    Mapped to exit code 3; diagnostics go to stderr only.
    """
