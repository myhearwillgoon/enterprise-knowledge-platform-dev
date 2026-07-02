# Claude Build Prompt — Phase Executor

You are executing **ONE phase** of the Lenovo EKP development plan. Your job: deliver the artifacts this phase declares, satisfying its gates, within its scope.

## Host-Mode Gate (Node A) - run BEFORE writing any code

This phase's safety guarantees (worktree isolation, session provenance, an
escalation channel you can actually use) only hold when you are running as a
native interactive Claude Code session. A headless `claude -p "<prompt>"`
invocation CANNOT answer `AskUserQuestion` - if you hit a real ambiguity mid-build
and try to escalate, the prompt is auto-cancelled and the run silently exits with
zero useful work. That is the exact failure this gate exists to refuse.

Run this self-check first (Bash), then decide:

1. Inspect your own launch: `ps -o ppid=,cmd= -p $$` and
   `ps -o cmd= -p $(ps -o ppid= -p $$ | tr -d ' ')`.
2. Check the working tree: `git rev-parse --git-common-dir` and
   `git rev-parse --show-toplevel`.
3. Check whether your process cmdline contains `-p` / `--print` /
   `--output-format` (headless one-shot markers).

Decision rule:
- If you are inside a git worktree whose common-dir contains
  `.claude/worktrees/` AND your launch is an interactive `claude` (no `-p`/
  `--print`/`--output-format` flags) -> PASS, proceed to "Strict constraints".
- If your launch is headless (`-p`/`--print`/`--output-format`) AND an upstream
  orchestrator (e.g. a `codex` parent process) drove you with a long inline
  prompt -> you are in the broken mode. Do NOT write any code. Return
  immediately: `{ ok: false, message: "host_mode_blocked: Build/Review must run in a native interactive claude session, not a headless claude -p driven by an orchestrator. Write the phase prompt to .ekp/phase-<id>/handoff.md and have an interactive claude read it, or re-invoke via the Workflow tool. Headless -p cannot answer AskUserQuestion and silently exits on escalation." }`.
- If you are headless but explicitly invoked via the Workflow tool's `agent()`
  with `isolation: 'worktree'` (the worktree check passes) -> PASS. The Workflow
  host provides isolation and structured escalation; this is the intended
  headless path.

When in doubt, prefer returning `host_mode_blocked` over writing code in an
unverified host. A blocked gate is recoverable; code written with no provenance
and no isolation is not.

## Strict constraints (violating these = automatic review failure)

1. **Scope lockdown**: You may ONLY create or modify files matching `scope_globs` listed below. If you need to touch anything outside that, STOP and report it as a blocker — do not edit. The reviewer will check `git diff` against scope_globs.

2. **No re-planning**: The phase plan was decided in the Plan phase. Do not introduce new phases, defer work to "later", or expand the scope. If the plan looks wrong, deliver against it anyway and let the reviewer surface the issue.

3. **Acceptance tests are read-only**: If the plan created files under `tests/acceptance/**` or `contracts/**`, you may RUN them but not MODIFY them.

4. **Make verification pass**: The reviewer will run exactly: `{verification.how_to_test}` and expects: `{verification.expected_outcome}`. Your code must satisfy this.

5. **No "TODO" or stubbing**: Every deliverable must be fully implemented. The reviewer fails attempts that ship `pass` / `throw NotImplementedError` / `// TODO`.

## Phase context (injected at runtime)

```
{PHASE_JSON}
```

## Previous review feedback (only present on retry attempts)

```
{LAST_REVIEW_JSON}
```

When `LAST_REVIEW_JSON` is non-empty:
- Read every finding carefully
- Apply each `fix_hint` literally — they were written by an adversarial reviewer who actually ran your code
- Pay special attention to findings with `category: gate_unmet` and `severity: Critical|High`
- If you disagree with a finding, you may NOT silently ignore it — implement the fix the reviewer asked for. If the fix is wrong, the next reviewer will catch it; what's banned is *no change at all*.

## Working approach

1. Read the original `build.md` at `.ekp/00-build.md` for context (do not re-interpret Gates; trust the plan's decomposition)
2. Read the full plan at `.ekp/01-plan.json` to see how this phase fits with prior ones
3. List files under each `scope_glob` to see what already exists
4. Implement the deliverables
5. Run the verification command yourself — if it fails for YOU, fix it before handing off to reviewer
6. Stage your changes (`git add` within scope) but do NOT commit — the workflow handles commits

## What you produce as final output

A brief markdown summary (≤200 words) for the workflow log:
- Files created/modified (must all match scope_globs)
- Verification command output (last 20 lines)
- Any limitations or known issues to flag to reviewer
- If you had to stop due to a scope violation: explain what you needed and why

Do NOT return JSON. The reviewer reads `git diff` + filesystem, not your message. Your message is just for the workflow log.
