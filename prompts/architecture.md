# Architecture

## 执行顺序

```
Orchestrator
  │
  ├─→ 预创建空文件：plan.md, solution.md, review.md
  │
  ├─→ spawn Planner
  │     读 problem.md → 写/改 {workspace}/plan.md
  │
  ├─→ spawn Builder
  │     读 problem.md + plan.md → 写/改 {workspace}/solution.md
  │     (可用 Bash 运行 Python 辅助计算)
  │
  ├─→ spawn Evaluator
  │     读 problem.md + solution.md → 写 {workspace}/review.md
  │     (可用 Bash 运行 Python 独立验证)
  │
  └─→ 检查 review.md
        PASS → 写 {workspace}/final_summary.md，结束
        REVISE → 迭代（见反馈规则）
```

## 反馈规则

- 若 review.md 第一行为 `REVISE`：
  1. Orchestrator 重新 spawn Builder，task 中附带审查意见原文
  2. Builder 修正后写 `{workspace}/solution.md`
  3. Orchestrator spawn Evaluator 重新审查
  4. 最多迭代 **2** 次
- 第二次迭代仍 REVISE → 将当前最佳方案和未解决问题列表写入 `{workspace}/final_summary.md`，结束
