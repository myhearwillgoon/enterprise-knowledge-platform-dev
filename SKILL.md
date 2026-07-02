---
name: lenovo-ekp
description: "Lenovo EKP knowledge-base development pipeline. Plan→Build→Review→Accept with cross-vendor model diversity (Codex GPT-5.5 for plan+accept, Claude for build+review). 3-strike escalation, worktree isolation, machine-checkable gates. Triggers: 'lenovo-ekp', '/lenovo-ekp', 'ekp pipeline', 'run ekp build'."
argument-hint: "<path-to-build.md> [--continue]"
user-invocable: true
---

# Lenovo EKP Development Pipeline

Orchestrate end-to-end development of a Lenovo EKP feature from a `build.md` specification through Plan, Build (with red-team Review and 3-strike retry), and final Accept. Cross-vendor by design: **Codex (GPT-5.5)** does adversarial planning and acceptance; **Claude Code** (the native CLI, powered by the Claude model) does code execution and adversarial review. Models bring different priors — that's the safety margin — but only when paired with the right host process (see below).

> **"Claude" means the native Claude Code CLI, not merely the Claude model API.**
> The Build and Review phases MUST execute as worktree-isolated subagents spawned by Claude Code's Workflow tool, running inside a `claude` process. Calling the Claude model API from another host (e.g. a Codex session that shims `agent()` to the Anthropic API) does **not** satisfy this — it silently breaks three things this skill relies on:
> 1. **Provenance**: no `~/.claude/projects/<slug>/*.jsonl` session log, no `~/.claude/file-history/` snapshots. Build code lands in the working tree with zero traceable origin (you only find out when a search for the session comes back empty).
> 2. **Worktree isolation**: `isolation: 'worktree'` only materializes a real git worktree under `.claude/worktrees/` when the host is native Claude Code. On a shim host the propagation step (`workflow.js` apply-the-patch-to-main-tree) operates on an undefined isolation primitive and can corrupt the main tree.
> 3. **Reviewer independence**: the red-team Reviewer must be a distinct process/context from the orchestrator. A Codex session invoking the Claude model inline keeps Build, Review, and orchestration in one process — the "different priors" safety margin collapses to a single context.
>
> The cross-vendor safety margin is a property of **both** the model family AND the host process — not the model alone. If a run produces code but leaves no `~/.claude/` session trace, the host was wrong; the code may be usable but it has not passed this pipeline's provenance/isolation guarantees.

> **MANDATORY first action when this skill is invoked**: say "Loaded lenovo-ekp skill. I will treat the provided build.md as the source of truth and run the pipeline accordingly." Do not improvise the pipeline — follow this document exactly.

## When to use

- The user provides a `build.md` file (typically from their supervisor) and asks to develop against it
- The user explicitly invokes `/lenovo-ekp <path>` or `/lenovo-ekp --continue`
- A previous `lenovo-ekp` run is paused at the Plan Gate and the user wants to resume

## When NOT to use

- For one-off code changes without a structured spec → use a normal Claude session
- When the user only wants planning (no implementation) → use `/hyperplan-native` directly
- When the user only wants review of existing code → use `/review` or `/code-review`

## Required environment

Run this preflight before starting (one Bash call, gather everything):

```bash
codex --version          # must succeed; need codex-cli ≥0.134.0
which codex              # must be on PATH
test -d ~/.claude/skills/lenovo-ekp && echo skill_ok
git rev-parse --show-toplevel   # MUST succeed — the session cwd must be inside a git repo
# Host-identity probe (only meaningful in mode='continue', but verify now):
#   the session cwd must resolve to a ~/.claude/projects/<slug>/ directory —
#   i.e. this `claude` process was launched from inside the project git repo.
#   If you are reading this from inside a Codex/other-LLM session, STOP:
#   you are not the intended host. See the "Claude" definition above.
```

If `codex` is missing, STOP and tell the user to install codex-cli (`npm i -g @openai/codex-cli` or per their org policy). Do not silently fall back to all-Claude — that defeats the cross-vendor design.

If `git rev-parse --show-toplevel` fails, **STOP and do not launch the workflow.** The workflow's per-phase Build/Review agents run in isolated git worktrees, and worktree creation resolves HEAD against the **session cwd**, not the path inside the agent prompt. If the session cwd is not inside a git repo (e.g. the user's home `~`, or an empty directory), agents will crash mid-run with `Failed to resolve HEAD` — sometimes only after 30–40 minutes of work. Tell the user verbatim:

> The current working directory is not a git repository. Worktree-isolated agents need a git repo at the session cwd. Please `cd` into the project git repository (or `~/work/ekp-validation-smoke` for the smoke test), restart `claude`, and re-invoke `/lenovo-ekp`. This cannot be fixed mid-session — the session cwd is fixed at launch.

This check is the difference between a 2-second failure and a 40-minute crash.

## Argument parsing

The user invocation looks like one of:
- `/lenovo-ekp /path/to/build.md` — start a new pipeline run
- `/lenovo-ekp --continue` — resume after human reviewed the plan
- `/lenovo-ekp /path/to/build.md --continue` — equivalent, the path is for verification

Parse `$ARGUMENTS` into:
- `BUILD_MD_PATH` — the first non-flag absolute path. **Required for new runs.** For `--continue`, you may infer it from `.ekp/00-build.md` snapshot.
- `MODE` — `plan` if no `--continue` flag, else `continue`

For WSL2 Windows paths (e.g. `E:\Lenovo\...`), translate to `/mnt/e/Lenovo/...` automatically. Spaces in path are common — quote properly when shelling out.

## Workflow location

`EKP_DIR = $(pwd)/.ekp` by default. All state files (build.md snapshot, plan, phase artifacts, verdicts) live here. If the user is in `/home/lenovo` (their home), prefer `/home/lenovo/work/<derived-name>/.ekp/` instead to avoid polluting home; ask once if unclear.

## Execution

**Preferred — Workflow orchestration.** If the **Workflow tool** is available in this session, use it (this skill invocation is your authorization to fan out subagents and run codex):

```
Workflow({
  scriptPath: "/home/lenovo/.claude/skills/lenovo-ekp/workflow.js",
  args: {
    buildMdPath: "<absolute path to build.md>",
    ekpDir: "<absolute path to .ekp/ state dir>",
    skillRoot: "/home/lenovo/.claude/skills/lenovo-ekp",
    mode: "plan",          // or "continue"
    maxRetries: 3,
    codexModel: "gpt-5.5"
  }
})
```

### Two-phase invocation pattern (this is the human gate)

**First call (mode='plan')** writes `.ekp/01-plan.json` and returns `{ status: 'awaiting_plan_review' }`. After that, you:

1. Read `.ekp/01-plan-summary.md` and surface it to the user
2. Ask the user to review `.ekp/01-plan.json` directly (it's editable — they may tweak phase scope or gate assignments)
3. Tell them exactly: "When ready to proceed, run `touch .ekp/.plan-approved` and ask me to continue"
4. Do NOT auto-continue. Stop and wait.

**Second call (mode='continue')** runs Build (with retries) and Accept. Returns one of:
- `{ status: 'delivered', verdict, artifactPath }` — ship it
- `{ status: 'rejected', verdict, ... }` — Codex Accept said no; surface blockers
- `{ status: 'escalated', phase, lastReview, humanActionRequired }` — 3-strike triggered or reviewer requested escalation

### Return-value handling

After Workflow returns, YOU (the calling session) write the human-facing summary:

| Return status | What you do |
|---|---|
| `awaiting_plan_review` | Show plan summary, instruct human to `touch .ekp/.plan-approved` and re-invoke with `--continue` |
| `delivered` | Show acceptance summary from `.ekp/99-acceptance.md`, list deliverable files, suggest commit/PR |
| `rejected` | Show blockers list, recommend re-invoking with `--continue` after addressing them |
| `escalated` | Show `humanActionRequired`, list artifacts in `.ekp/phase-<id>/`, ask user what to do next (refine plan, adjust build.md, implement manually) |
| `plan_failed` / `accept_failed` / `continue_blocked` | Show the failure message; this is usually a codex CLI issue or missing prerequisite |

The workflow agents are read/write within the `.ekp/` directory and project source; **you** are the one who eventually commits, opens PRs, or hands off.

**Fallback — direct subagents** (older Claude Code without the Workflow tool). Run sequentially via Bash and the `Agent` tool, mimicking workflow.js phase by phase:

1. `bash` step: `mkdir -p .ekp && cp <build.md> .ekp/00-build.md && codex exec --model gpt-5.5 --dangerously-bypass-approvals-and-sandbox --output-schema /home/lenovo/.claude/skills/lenovo-ekp/schemas/plan.schema.json -o .ekp/01-plan.json - < combined-prompt.txt` (combined-prompt.txt = codex-plan.md + separator + build.md)
2. Pause for human Gate (see two-phase pattern above)
3. For each phase: spawn `general-purpose` Agent with `claude-build.md` prompt → spawn another `general-purpose` Agent with `claude-review.md` prompt → loop ≤3 times
4. Final `bash` step: `codex exec` with the accept prompt

This fallback is sequential (no `parallel()` orchestration) and lacks worktree isolation — use only when Workflow is unavailable. The output contracts (JSON schemas) are identical.

## Telling the user before launching

The workflow fans out roughly **1 + (3 × N_phases) + 1 agents** where N_phases is the plan size — typically 6–15 agents total. It also makes 2 calls to `codex exec` (plan + accept). Tell the user this before launching so they can decide on cost/time tradeoffs. Mention:

- "Workflow will run for ~5–20 minutes depending on phase count and retry needs"
- "It will halt at the Plan Gate for your review of `.ekp/01-plan.json`"
- "Each Build agent runs in an isolated worktree — your main working tree won't be touched until a phase passes review"

## State directory contract

After a full run, `.ekp/` contains:

```
.ekp/
├── 00-build.md                      # Snapshot of input (do not modify)
├── 01-plan.json                     # Codex output (human-editable between Plan and Continue)
├── 01-plan-summary.md               # Human-readable plan TLDR
├── .plan-approved                   # Sentinel: human ack of plan
├── phase-P1/
│   ├── attempt-1/
│   │   ├── diff.patch
│   │   ├── build-report.md
│   │   └── review.json
│   └── attempt-N/...
├── phase-P2/...
├── 99-acceptance.json               # Codex Accept verdict (structured)
└── 99-acceptance.md                 # Human-readable verdict
```

If the user wants to start fresh: `rm -rf .ekp && /lenovo-ekp <build.md>`.

## Resume semantics

Workflow runs persist a `runId`. If the workflow is killed mid-Build (e.g. session crashed), the user can recover by:
1. Checking `.ekp/phase-*/attempt-*/` to see what's done
2. Re-invoking `/lenovo-ekp --continue` — completed phases will return cached results from Workflow's journal (when same runId is given via `resumeFromRunId`), or be re-detected as already-passed by checking the latest attempt's review.json

For simple recovery, re-invoking `--continue` will re-run from the last unfinished phase; phase-level idempotency is the user's safety net.

## Loop Engineering mapping (for users coming from /loop)

This skill uses the **Workflow tool**, not the `/loop` skill. The 6 Loop Engineering building blocks still apply:

| Block | Where it lives |
|---|---|
| Goal | build.md (frontmatter `gates:` + body) |
| State | `.ekp/` directory |
| Guardrails | `scope_globs` per phase, `maxRetries=3`, scope audit in review |
| Verification | `claude-review.md` red-team + `codex-accept.md` final audit |
| Handoff | JSON schemas (plan, review, accept) between agents |
| Memory | `.ekp/phase-N/attempt-M/review.json` accumulates lessons, injected into next attempt's build prompt |

If you need ongoing/periodic monitoring of EKP work (e.g. "watch a build.md folder, kick off a pipeline when a new file lands"), that's a `/loop` outer + `/lenovo-ekp` inner pattern — out of scope for this skill.
