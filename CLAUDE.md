# AITokenPerf

## Git workflow

### Issue association（任何代码改动前必须执行）

1. `gh issue list --state open --limit 30`
2. 有相关 issue → 使用；无 → 创建
3. Issue 编号用于分支名、commit、PR

### Branch + PR flow

1. 分支命名：`fix/issue-<N>-<slug>` 或 `feat/issue-<N>-<slug>`
2. 使用 `git worktree` 隔离开发（参见 `issue-workflow` skill）
3. Commit（不含 Co-Authored-By），包含 issue 引用
4. Push 分支 + `gh pr create`（PR body 含 `Closes #N`）
5. 等待人工审核后合并

### 实现流程

满足任一条件即为复杂改动，**必须使用 superpowers**：
- 新功能/新组件
- 涉及 3+ 文件
- 需要设计决策（架构、布局、API）
- 模糊需求（"优化一下"/"重新设计"等）

简单改动（单文件修复、配置）可直接编码。

完整流程参见 `.claude/skills/issue-workflow/SKILL.md`

## 项目约定

- 中文回复
- 前端用 bun 不用 npm
- 不要自动发版，必须用户明确要求
- Git 提交不要添加 Claude 作者信息
- Pre-push hook 会跑 vitest + build 检查

## 部署

SSH 到 app.aitokenperf.com，docker compose 部署，注意更新 APP_VERSION。
