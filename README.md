# lenovo-ekp

> A Claude Code Skill that runs the Lenovo EKP knowledge-base development pipeline:
> **Plan → Build → Review → Accept**, with cross-vendor model diversity (Codex GPT-5.5 for Plan and Accept, Claude Code — the native CLI, not just the Claude model API — for Build and adversarial Review). 3-strike escalation, worktree isolation, machine-checkable Gates.

## Why this exists

Modern AI-assisted development with a single model is fast but **same-source biased**: a model that plans a feature and then reviews its own implementation tends to miss the same blind spots in both passes. Many teams (including the author's) have converged on an informal workflow:

1. Use one model family for **planning** with adversarial cross-critique (e.g. Codex + hyperplan)
2. Use a different model family for **execution** (e.g. Claude)
3. Use yet another instance (independent context) to **adversarially review** the executor's output
4. Loop ≤3 times, then escalate to a human
5. Have the original planner do **final acceptance** against the spec it owns

This skill **codifies that workflow** as a Claude Code Skill backed by a [Workflow tool](https://docs.claude.com/en/docs/claude-code/workflow-tool) script, so the orchestration is deterministic (a JS program decides retries and phase boundaries, not a model).

## Installation

```bash
# Clone into your Claude Code skills directory
git clone https://github.com/<your-org>/lenovo-ekp ~/.claude/skills/lenovo-ekp

# Verify the prerequisite (codex-cli ≥ 0.134.0)
codex --version
```

If you don't have `codex-cli`:
```bash
npm install -g @openai/codex-cli
# or follow https://github.com/openai/codex-cli
```

## Quickstart (3 minutes)

```bash
# Try the included sample spec
mkdir -p ~/work/ekp-demo && cd ~/work/ekp-demo
cp ~/.claude/skills/lenovo-ekp/examples/sample-build.md ./build.md

# In a Claude Code session:
/lenovo-ekp ./build.md
# → workflow runs Plan phase, halts at .ekp/01-plan.json for your review

# Review the plan
cat .ekp/01-plan-summary.md
$EDITOR .ekp/01-plan.json   # optional: tweak phase scope or gate assignments

# Approve and continue
touch .ekp/.plan-approved
/lenovo-ekp --continue
# → workflow runs Build (with retries) and Accept; halts on success or escalation
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         lenovo-ekp Skill                             │
│                                                                      │
│  SKILL.md  ───►  invokes Workflow({scriptPath: workflow.js, args})  │
│                                                                      │
│  ┌──────────────  workflow.js (deterministic JS) ──────────────┐    │
│  │                                                              │    │
│  │  Phase 1: Plan                                               │    │
│  │     └─► Claude agent (Bash) ──► codex exec --model gpt-5.5   │    │
│  │                                  with codex-plan.md prompt   │    │
│  │                                  → .ekp/01-plan.json         │    │
│  │                                                              │    │
│  │   [ HUMAN GATE: review .ekp/01-plan.json, then continue ]   │    │
│  │                                                              │    │
│  │  Phase 2: Build (for each plan.phase)                        │    │
│  │     └─► retry loop (≤3 attempts):                            │    │
│  │           Claude build agent (worktree-isolated)             │    │
│  │             ↓                                                │    │
│  │           Claude review agent (worktree-isolated, red team) │    │
│  │             ↓                                                │    │
│  │           if passed → next phase                             │    │
│  │           if 3 strikes → escalate to human                   │    │
│  │                                                              │    │
│  │  Phase 3: Accept                                             │    │
│  │     └─► Claude agent (Bash) ──► codex exec --model gpt-5.5   │    │
│  │                                  with codex-accept.md prompt │    │
│  │                                  → .ekp/99-acceptance.json   │    │
│  └──────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

## The `build.md` contract

Your spec must have YAML frontmatter declaring the Gates:

```yaml
---
project: my-feature
codex_model: gpt-5.5
max_retries: 3
gates:
  - id: G1
    description: |
      Multi-line description of what success looks like.
    must_have:
      - "Concrete bullet 1"
      - "Concrete bullet 2"
  - id: G2
    description: ...
---

# Feature: ...

## Context
... free-form body ...
```

See [`examples/sample-build.md`](examples/sample-build.md) for a fully worked example.

The Plan phase MUST cover every Gate in at least one phase's `gates_satisfied`. If it doesn't, the workflow surfaces this via `gate_coverage_check.uncovered_gates` and you should refine the plan before approving.

## The 6 Loop Engineering blocks

This skill is built on [Loop Engineering](https://github.com/cobusgreyling/loop-engineering) principles, but uses the **Workflow tool** as the substrate (not the `/loop` slash command — see the SKILL.md "Loop Engineering mapping" section for why).

| Block | Where it lives |
|---|---|
| Goal | `build.md` frontmatter `gates:` |
| State | `.ekp/` directory |
| Guardrails | `scope_globs` per phase, `maxRetries=3`, scope audit in review |
| Verification | `claude-review.md` red-team + `codex-accept.md` final audit |
| Handoff | JSON Schemas (`schemas/{plan,review,accept}.schema.json`) |
| Memory | `.ekp/phase-N/attempt-M/review.json` accumulates lessons, injected into next attempt's build prompt |

## Design decisions (and their tradeoffs)

### Why Codex for Plan+Accept, Claude for Build+Review?
The same model evaluating its own work has a measurable self-consistency bias. Different model families have different blind spots. The cross-vendor split provides a real (if modest) safety margin. Substitute any provider pair you trust — change `codex_model` and the codex CLI invocations.

**The split is a property of the host process, not just the model.** "Claude" here means the native **Claude Code CLI**, not merely the Claude model API. The Build and Review phases depend on three things only native Claude Code provides: real git worktree isolation under `.claude/worktrees/`, `~/.claude/` session provenance (so every line of build output is traceable to a session log + file-history snapshot), and a Reviewer that runs as a distinct subagent process from the orchestrator. A host that shims `agent()` to the Claude model API — e.g. a Codex session invoking Claude inline — satisfies the model requirement in name only: it produces code with no `~/.claude/` trace, undefined worktree isolation, and a Reviewer sharing the orchestrator's context (the "different priors" margin collapses to one context). The workflow enforces this with a host-identity probe (`host_mismatch` status) before any Build work begins. If a run leaves build artifacts in the working tree but no `~/.claude/` session trace, the host was wrong and the output has not passed this pipeline's provenance/isolation guarantees.

### Why single-shot adversarial prompt instead of fan-out for Plan?
`codex exec` is single-agent. Real fan-out (5 parallel reviewers) requires the host to have an Agent/Task primitive — which is exactly what Claude Code's Workflow tool gives, but Codex CLI doesn't. We encode the adversarial debate as a 5-role role-play within one prompt. We lose the strict independence of true parallel agents, but we keep the structural discipline (Skeptic / Validator / Architect / Researcher / Creative) and gain "one shell command" simplicity.

### Why a hard 3-strike retry limit?
Empirically, if a model can't pass review by the third attempt, the issue is usually structural (the plan is wrong, the gate is unmeasurable, a dependency is missing) — not "needs more iterations". Strict limits force escalation when escalation is the right answer.

### Why are build agents in worktree isolation?
If a build agent goes rogue and edits files outside `scope_globs`, you don't want that contaminating your main working tree. The worktree gets discarded if review fails; only successful phases merge changes back.

## Limitations / not yet implemented

- **`mode=continue` re-run idempotency** is approximate: passed phases are detected via the latest attempt's review.json, but if the working tree is significantly different from the snapshot, you may want to clean and re-run.
- **Codex `--output-schema` strictness** is enforced by Codex's runtime; if Codex returns malformed JSON despite the schema, the workflow logs a parse error rather than retrying automatically.
- **WSL2 Windows path handling** in arguments needs manual translation (`E:\` → `/mnt/e/`); the skill notes this but doesn't auto-convert.
- **Codex requires `--dangerously-bypass-approvals-and-sandbox`** for unattended use. Run this skill in directories you trust.

## Contributing

This is an MVP. Most valuable contributions:
1. **Sub-skill extraction** — split `lenovo-ekp` into `lenovo-ekp-plan`, `lenovo-ekp-build`, `lenovo-ekp-review`, `lenovo-ekp-accept` so users can start from any phase
2. **Provider abstraction** — make the Plan/Accept side pluggable (currently hardcoded to `codex exec`)
3. **Real fan-out for Plan** — when running under Workflow, use 5 parallel `agent()` calls instead of the in-prompt role-play
4. **Resume robustness** — leverage Workflow's `resumeFromRunId` more aggressively in `mode=continue`

## License

MIT (see LICENSE).

## Credits

- Workflow tool patterns adapted from Anthropic's [code-modernization plugin](https://github.com/anthropics/claude-code-plugins) (`harden-scan.js`, `portfolio-assess.js`)
- Adversarial role-play prompt structure inspired by [hyperplan-native](https://github.com/cobusgreyling/hyperplan)
- Loop Engineering 6-block framework: [Cobus Greyling](https://github.com/cobusgreyling/loop-engineering)
