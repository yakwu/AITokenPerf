---
name: issue-workflow
description: Issue → 分支 → 实现 → PR 完整工作流。实现阶段根据复杂度自动选择直接编码或 superpowers（brainstorming → plan → subagent-driven）
---

# Issue Workflow（融合 Superpowers）

标准化开发流程：Issue 关联 → 分支 → 实现 → PR → 等待审核。

实现阶段分为两档：
- **简单改动**（拼写、单行修复、纯配置）→ 直接编码
- **需设计/规划的改动**（新功能、重构、多文件）→ superpowers 流程

## 流程

```
gh issue list / create
      ↓
创建分支: {type}/issue-{N}-{slug}
      ↓
┌─ 简单改动 → 直接实现
└─ 复杂改动 → brainstorming → spec → [subagent 审 spec] → writing-plans → [subagent 开发]
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

## 2. 创建分支

在主仓库直接开分支，**不用 git worktree**（worktree 下 Edit/Write 易误写主仓库、且需单独 `bun install`，单人项目得不偿失）。

```bash
git checkout main && git pull
git checkout -b {type}/issue-{N}-{slug}
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

**强规则：brainstorming → 写 spec → subagent 审 spec → writing-plans → subagent 开发 → 收尾。**
**spec 与 plan 写完后改由 subagent 自动审查放行，无需等用户手动确认（覆盖 brainstorming
skill 的"用户审 spec"人工闸门——用户指令优先）。** 设计呈现阶段（写 spec 之前）的方案确认仍保留。

```bash
# 第一步：设计方案（仍需用户确认设计方案后才写 spec）
Skill(skill="superpowers:brainstorming")
```

**第二步：spec 写完后，自动 spawn subagent 审查 spec（不等用户手动审）**

```
Agent(subagent_type="general-purpose", description="审查 spec",
      prompt="审查设计文档 <spec 路径>：检查 1) 占位/TODO/未填项 2) 内部矛盾
              3) 歧义需求 4) 范围是否适合单个实现计划 5) 技术可实现性与对现有代码的影响。
              只读不改。输出 BLOCKER（必须改）/ NIT（建议）/ 通过 三档结论。")
```

- subagent 返回 **通过 / 仅 NIT** → 直接进入 writing-plans（不再等用户）。
- subagent 返回 **BLOCKER** → 修复 spec 后重审；反复修不掉或涉及产品取舍 → 回到用户。

```bash
# 第三步：写实施计划
Skill(skill="superpowers:writing-plans")
```

**第四步：plan 写完后，直接用 subagent-driven-development 执行（不等用户手动确认）**

```bash
Skill(skill="superpowers:subagent-driven-development")
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
git checkout main && git pull
git branch -d {type}/issue-{N}-{slug}
```

## 异常处理

| 场景 | 处理 |
|------|------|
| Issue 需要讨论 | 先在 issue 下评论，确认方案后再动手 |
| 实现中发现 scope 超出 | 停下来，拆分新 issue |
| PR 检查失败 | 修复后追加提交，不要 force push |
| 关联多个 issue | PR body 写 `Closes #A, Closes #B` |
