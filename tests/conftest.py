"""Shared pytest configuration for the pdf-table-search suite (phase P4).

Centralizes subprocess invocation of the installed CLI so every test in the
three modules exercises one resolved entry point through a single fixture,
instead of each module re-declaring its own ``COMMAND`` / ``_run`` helper.

Command resolution (phase P4 deliverable: subprocess tests must hit the real
installed CLI entry point):

1. Prefer the ``pdf-table-search`` console script -- the command end users
   actually invoke -- when it is on PATH *and* runnable.
2. Fall back to ``python -m pdf_table_search.cli`` (the module entry), which
   always works for an editable install of this tree even when the console
   script is not on PATH (e.g. a fresh checkout without scripts on PATH).
3. Fail loudly if neither runs, so a broken install surfaces as one clear
   session-level error rather than N cryptic subprocess failures.

The chosen command is validated once per session with ``--help`` and then
cached. ``run_cli`` is the per-test callable that prepends it to caller args.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Sequence

import pytest

# The console script declared under [project.scripts] in pyproject.toml. This
# is the preferred entry point: it is what the gates (build.md) and end users
# call as ``pdf-table-search ...``.
_CONSOLE_SCRIPT = "pdf-table-search"
# The module entry, used as a fallback when the console script is not on PATH.
# sys.executable pins the same interpreter that is running pytest, so an
# editable install of this tree is importable regardless of PATH state.
_MODULE_ENTRY: list[str] = [sys.executable, "-m", "pdf_table_search.cli"]


def _is_runnable(command: Sequence[str]) -> bool:
    """True if ``command --help`` exits 0 (the entry point actually works).

    A console script may be on PATH yet broken (stale, wrong interpreter, etc.);
    checking ``--help`` confirms the entry point is live before adopting it.
    """
    result = subprocess.run(
        list(command) + ["--help"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


@pytest.fixture(scope="session")
def cli_command() -> list[str]:
    """Resolve and validate the CLI command once per session.

    Returns the argv prefix (as a list) to prepend to subcommand args. Prefers
    the console script; falls back to the module entry; raises ``AssertionError``
    if neither is runnable so the install problem is obvious.
    """
    if shutil.which(_CONSOLE_SCRIPT) and _is_runnable([_CONSOLE_SCRIPT]):
        return [_CONSOLE_SCRIPT]
    if _is_runnable(_MODULE_ENTRY):
        return list(_MODULE_ENTRY)
    raise AssertionError(
        "pdf-table-search CLI is not runnable: neither the console script "
        f"{_CONSOLE_SCRIPT!r} nor the module entry {_MODULE_ENTRY!r} answered "
        "--help. Install the package with `pip install -e .`."
    )


@pytest.fixture
def run_cli(cli_command: list[str]):
    """Return a callable that runs the CLI with the given args, capturing I/O.

    Usage::

        def test_something(run_cli):
            result = run_cli("extract", str(pdf_path))
            assert result.returncode == 0

    Returns a :class:`subprocess.CompletedProcess` with ``stdout`` and
    ``stderr`` decoded as text, matching the shape the previous per-module
    ``_run`` helpers produced.
    """

    def _run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            cli_command + list(args),
            capture_output=True,
            text=True,
        )

    return _run
