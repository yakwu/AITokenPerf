---
name: issue-workflow
description: Issue → 分支 → 实现 → PR 完整工作流。实现阶段根据复杂度自动选择直接编码或 superpowers（brainstorming → plan → subagent-driven）
---

# Issue Workflow（融合 Superpowers）

标准化开发流程：Issue 关联 → 工作树 → 实现 → PR → 等待审核。

实现阶段分为两档：
- **简单改动**（拼写、单行修复、纯配置）→ 直接编码
- **需设计/规划的改动**（新功能、重构、多文件）→ superpowers 流程

## 流程

```
gh issue list / create
      ↓
创建 worktree + 分支: {type}/issue-{N}-{slug}
      ↓
┌─ 简单改动 → 直接实现
└─ 复杂改动 → brainstorming → plan → subagent-driven
      ↓
提交: type(scope): 描述 (#N)
      ↓
推送 + gh pr create（含 Closes #N）
```

## 1. Issue 关联（任何代码改动前必须执行）

```bash
gh issue list --state open --limit 30
```

- 有相关未关闭 issue → 使用它
- 有相关已关闭 issue，且是后续修复 → 评论说明后决定 reopen 还是新建
- 无相关 issue → 创建：

```bash
gh issue create --title "简短描述" --body "详细说明"
```

## 2. 创建 Worktree + 分支

```bash
git checkout main && git pull
git worktree add -b {type}/issue-{N}-{slug} ../worktrees/issue-{N}
```

- **type**: fix / feat / refactor / docs / chore
- **slug**: 标题英文关键词，3-5 词，kebab-case
- 示例: `fix/issue-142-diagnostic-card-layout`、`feat/issue-97-model-discovery-api`

## 3. 实现

### 复杂度判断

满足以下**任一条件**即为复杂改动，**必须使用 superpowers**：

- 新功能或新组件
- 涉及 3 个及以上文件
- 需要设计决策（架构选型、布局重构、API 变更）
- 用户说 "帮我设计" / "重新设计" / "优化一下" 等模糊需求

简单改动（单文件、拼写修复、配置变更）可直接编码。

### 复杂改动 — 必须使用 superpowers

**强规则：先 Invoke brainstorming skill，再 Invoke writing-plans，最后用 subagent-driven-development 执行。**

```bash
# 第一步：设计方案
Skill(skill="superpowers:brainstorming")

# 第二步：写实施计划
Skill(skill="superpowers:writing-plans")

# 第三步：TDD 实现
Skill(skill="superpowers:subagent-driven-development")
```

```
每个 subagent 任务完成后自动做 spec review + code review。实现完毕用 `finishing-a-development-branch` 收尾。

## 4. 提交

格式：`type(scope): 中文描述 (#N)`

```bash
git add {files}
git commit -m "fix(frontend): 修复诊断卡片布局溢出 (#142)"
```

- **不要** Co-Authored-By Claude
- scope 可选：frontend / backend / api / db 等

## 5. 推送 + PR

```bash
git push -u origin {branch}
gh pr create --base main --title "type: 描述 (#N)" --body "$(cat <<'EOF'
## Summary
- 变更 1
- 变更 2

Closes #{N}

## Test Plan
- [ ] 测试 1
- [ ] 测试 2
EOF
)"
```

- PR body 必须含 `Closes #N`，合并后自动关闭 issue
- 推送后不要合并，等待人工审核

## 6. 合并后

```bash
gh issue close {N}
gh issue view {N} --json state
git worktree remove ../worktrees/issue-{N}
```

## 异常处理

| 场景 | 处理 |
|------|------|
| Issue 需要讨论 | 先在 issue 下评论，确认方案后再动手 |
| 实现中发现 scope 超出 | 停下来，拆分新 issue |
| PR 检查失败 | 修复后追加提交，不要 force push |
| 关联多个 issue | PR body 写 `Closes #A, Closes #B` |
