# lenovo-ekp 验证续跑指南

> 本文件由上一个 Claude Code session 生成，用于在**新 session**里续跑 Build+Accept 验证。
> 原因：worktree 隔离锚定 session cwd，必须在 git 仓库目录里启动 claude 才能工作。

## 背景状态（已完成，无需重做）

- ✅ Skill 已实现在 `~/.claude/skills/lenovo-ekp/`
- ✅ Plan 阶段已跑通：`.ekp/01-plan.json`（4 phase / 4 gate 全覆盖）
- ✅ 人工 Gate 已通过：`.ekp/.plan-approved` 存在
- ✅ schema bug 已修复（3 个 schema 都加了 `additionalProperties:false`）
- ✅ worktree 配置已全局生效：`~/.claude/settings.json` 里 `worktree.baseRef = head`
- ⏳ 待跑：Build（4 phase × build+review × ≤3 retry）+ Accept（codex 终验）

## 续跑步骤

### 1. 在验证目录里启动新 Claude Code session

**关键**：必须 `cd` 到验证目录再启动 claude，这样 session cwd = git 仓库。

```bash
cd ~/work/ekp-validation-smoke
claude
```

> 如果你用的是 `!` 前缀在当前 session 跑命令，那不行——必须在验证目录里新开 session。
> 可以这样开新 session（在当前终端）：先退出当前 claude，或开新终端 tab。

### 2. 在新 session 里调用 Skill 续跑

进入新 session 后，直接对 Claude 说（或用斜杠命令）：

```
/lenovo-ekp --continue
```

或者自然语言：

```
继续跑 lenovo-ekp 的 Build 和 Accept 阶段，plan 已经在 .ekp/01-plan.json 批准了
```

Claude 会：
1. 读 `~/.claude/skills/lenovo-ekp/SKILL.md`
2. 检测到 `.ekp/.plan-approved` 存在 → mode=continue
3. 调 Workflow 工具跑 `workflow.js`（mode=continue）
4. 逐 phase：build agent（worktree 隔离）→ review agent（worktree 隔离，红队）→ ≤3 retry
5. 最后 codex exec 跑 Accept 终验

### 3. 预期耗时与产物

- **耗时**：10-25 分钟（4 phase，每 phase 1-3 次 attempt）
- **产物**：
  - `.ekp/phase-P1/attempt-1/{diff.patch, build-report.md, review.json}`
  - `.ekp/phase-P2/...`、`P3/...`、`P4/...`
  - `.ekp/99-acceptance.json`（codex 终验结构化结果）
  - `.ekp/99-acceptance.md`（人类可读终验报告）
  - 源码：`src/pdf_table_search/*.py`、`tests/*.py`、`pyproject.toml`

### 4. 成功标志

workflow 返回 `{ status: 'delivered', verdict: {...} }`，且：
- `.ekp/99-acceptance.json` 里 `delivered: true`
- `src/` 和 `tests/` 下有真实可跑的 Python 代码
- `pytest tests/ -v` 能通过（G4 验证）

### 5. 如果又失败

常见问题排查：
- **worktree 还是失败**：确认新 session 的 cwd 是 `~/work/ekp-validation-smoke`（在 claude 里问 "当前工作目录是什么"）
- **codex 认证失败**：跑 `codex --version` 和 `echo "test" | codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox -` 测试
- **某个 phase 3 次都不过**：看 `.ekp/phase-PN/attempt-3/review.json` 的 findings，可能是 plan 的 scope_globs 太严或 gate 描述有歧义

## 验证完成后

跑通后回到**原来的 session**（或任意 session）告诉我结果，我会：
1. 检查产出质量（review.json 的 findings 是否合理、acceptance 是否严谨）
2. 把验证结论写入 memory
3. 准备 GitHub 发布（git init skill 仓库 + 推送）

## 关键文件路径速查

| 用途 | 路径 |
|---|---|
| Skill 实现 | `~/.claude/skills/lenovo-ekp/` |
| workflow 脚本 | `~/.claude/skills/lenovo-ekp/workflow.js` |
| 验证目录 | `~/work/ekp-validation-smoke/` |
| 输入 build.md | `~/work/ekp-validation-smoke/build.md`（= sample-build.md 副本） |
| 已批准的 plan | `~/work/ekp-validation-smoke/.ekp/01-plan.json` |
| 全局 worktree 配置 | `~/.claude/settings.json` → `worktree.baseRef = head` |
