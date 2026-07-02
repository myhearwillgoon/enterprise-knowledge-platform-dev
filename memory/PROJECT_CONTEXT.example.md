# Project Context - Persistent Memory (TEMPLATE, public)

> Copy this file to `PROJECT_CONTEXT.md` (same directory) and fill in real
> absolute paths. **`PROJECT_CONTEXT.md` is gitignored** - it stays on the
> operator's machine because it points at internal assets. Never commit the
> filled-in copy to a public repo.

## Why this exists

The lenovo-ekp pipeline runs in phases (Plan -> Build -> Review -> Accept) across
**separate model contexts** - each phase is a fresh agent that does not inherit
the prior phase's working memory. Without a persistent anchor, every phase
re-derives project standing context (which file is the authoritative spec,
where the autonomous prompt lives, where the test corpus is) - or worse,
assumes and gets it wrong.

This file is the **project-level standing context** that every phase reads at
the start. It is subordinate to explicit phase instructions and to the
`build.md` gates, but it **overrides an agent's own assumptions**.

## How it is loaded

`workflow.js` resolves `memory/PROJECT_CONTEXT.md` under the skill root (or the
path passed as `args.projectMemoryPath`) and injects a "read this file"
directive into all four phase prompts. If the file is missing, phases proceed
without it (non-fatal) and note the absence in their output.

## Fill these in

### requirement_doc
- **path:** `/absolute/path/to/<build-id>-BUILD.md`
- **role:** The authoritative requirement specification. `build.md` passed to
  the skill is a derivative/snapshot. If the two ever conflict on a gate or
  scope boundary, `requirement_doc` wins - flag the delta in Plan and Accept.

### autonomous_prompt
- **path:** `/absolute/path/to/AUTONOMOUS-BUILD-<id>-PROMPT.md`
- **role:** Standing build directives that apply across **all** phases, not
  just one (e.g. "default feature flags off", "advance-on-red forbidden",
  "do not modify already-completed phases"). Read once; honor throughout.

### test_assets
- **path:** `/absolute/path/to/test-decks.zip`
- **role:** Corpus for verification gates that require real-document
  round-tripping (PPTX/DOCX/PDF flowchart extraction). Extract to a temp dir
  on demand; note the extraction location if reproducibility matters.

### project_root (optional)
- **path:** `/absolute/path/to/ekp/repo/working/tree`
- **role:** The EKP source tree the pipeline mutates. Passed to codex via
  `-C` where relevant; recorded here so every phase agrees on the same tree.

### owner / metadata (optional)
- **owner:** `<redact before any public exposure>`
- **notes:** Any other standing context the operator wants every phase to see.

## Maintenance

- Update paths when a new build-id lands (new requirement doc / prompt / decks).
- Keep this file machine-readable: one `### <key>` block per asset, `path:` line
  first. Agents parse it loosely, but a consistent shape helps.
- If an asset is not yet available, set its `path:` to `(none)` and add a note
  rather than deleting the block - explicit absence beats silent omission.
