# CC_Integrater — 多 Agent 协作物理解题系统

## 简介

本项目通过 Claude Code CLI 编排三个 Agent（Planner / Builder / Evaluator）自动解决物理题目。Planner 分析题目并制定解题计划，Builder 执行完整推导求解，Evaluator 审查结果并反馈。若审查未通过，系统自动将 Builder 的结果送回修正，最多迭代 2 次。每道题支持断点续传，中断后可自动从上次进度继续。

## 环境安装

### 安装 Claude Code

本项目依赖 [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview) CLI 工具：

```bash
npm install -g @anthropic-ai/claude-code
```

### 配置 API Key（按量计费模式）

如果使用第三方兼容 API（如硅基流动等），设置环境变量：

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
export ANTHROPIC_BASE_URL="https://your-api-endpoint.example.com/v1"
```

将上述两行加入 `~/.bashrc` 或 `~/.zshrc` 以持久化。

### 放置题目

在 `problems/` 目录下为每道题创建一个子文件夹，放入 `problem.md`（如果不改名称，直接拖入任意md文件亦可，但是不建议）：

```
problems/
  example_single/
    problem.md
  example_multiple/
    1/
      problem.md
    2/
      problem.md
    3/
      problem.md
```

多题只需指定父目录，系统会自动识别并依次处理。

## 配置

编辑项目根目录的 `config.json`：

```json
{
  "model": "qwen3.6-plus",
  "timeout_seconds": 86400,
  "max_concurrent_problems": 3
}
```

| 字段 | 说明 |
|------|------|
| `model` | 使用的模型名，由 Claude Code CLI 的 `--model` 参数传递 |
| `timeout_seconds` | 单次调用的最大超时时间（秒），默认 86400（24 小时） |
| `max_concurrent_problems` | 多题场景下同时并行处理的最大题目数，默认 3。设为 1 则串行处理 |

## 运行

```bash
# 处理单道题
python3 run.py problems/example_single

# 处理一批题（自动识别多题模式）
python3 run.py problems/example_multiple
```

## 查看结果

每道题的子文件夹中，用户需要关注的文件：

| 文件 | 说明 |
|------|------|
| `plan.md` | 解题计划（物理情景、适用定律、解题路线） |
| `solution.md` | 完整求解过程与最终答案 |
| `review.md` | 审查结果，首行为 `PASS` 或 `REVISE` |
| `final_summary.md` | 最终汇总：执行统计 + 完整答案（**主要阅读文件**） |

多题场景下，父目录还会生成 `batch_summary.md`，汇总所有子题的状态和答案摘要。

以下以 `.` 开头的文件是系统内部使用的状态和缓存文件，一般不需要手动查看：

| 文件 | 说明 |
|------|------|
| `.state` | 断点续传状态文件，记录下一个应执行的 Agent |
| `.{role}.result` | 对应 Agent 的原始输出 |
| `.{role}.metrics` | 对应 Agent 的调用指标（用时、Token 消耗等） |

## 注意事项

- **不要手动删除 `.state` 文件**：如果需要重做某道题，删除该题子文件夹下所有生成的文件（保留 `problem.md`）即可重置。
- **超时设置**：复杂题目可能耗时较长，`timeout_seconds` 建议设大一些。如果中途中断，下次运行会自动从断点续传。
- **模型选择**：推荐使用推理能力较强的模型，弱模型在物理推导上可能出错。
- **题目格式**：`problem.md` 建议使用纯文本或 Markdown，包含题目描述、已知条件和待求量。如果题目含图片，可在 Markdown 中用文字描述图片内容。

## 项目结构

```
.
├── outline.md          # 工作流定义：Orchestrator 指令、各 Agent prompt、文件格式规范、Skills
├── config.json         # 项目配置（模型名、超时时间）
├── run.py              # 入口脚本：创建 Orchestrator Agent 并启动
├── spawn.py            # 子进程辅助脚本：由 Orchestrator 调用，创建 Planner/Builder/Evaluator
├── problems/           # 题目目录
│   └── <exam>/
│       ├── <n>/
│       │   ├── problem.md      # 输入：题目
│       │   ├── plan.md         # Planner 输出
│       │   ├── solution.md     # Builder 输出
│       │   ├── review.md       # Evaluator 输出
│       │   ├── final_summary.md # 最终汇总
│       │   ├── .state          # 断点状态
│       │   └── .*.result / .*metrics  # 内部缓存
│       └── ...
└── README.md
```

## 技术细节

### 架构

系统通过 Claude Code CLI 的 `--agents` 功能创建独立的 Agent 进程：

```
Orchestrator
  │
  ├── 滑动窗口并行（最多 max_concurrent_problems 题同时运行）
  │   初始启动 3 题，任一题完成后立即从队列补入下一题
  │   例：1,2,3 同时跑 → 1 完成 → 4 补入 → 2,3,4 同时跑 → 3 完成 → 5 补入 → 2,4,5 同时跑 → ...
  │
  └── 全部完成后生成 batch_summary.md
```

单道题内的阶段顺序：

```
题目 X
  ├── spawn Planner   → plan.md
  ├── spawn Builder   → solution.md
  ├── spawn Evaluator → review.md
  └── 检查 review.md
        PASS  → final_summary.md
        REVISE → 重新 spawn Builder（附带审查意见），最多 2 次
```

每个 Agent 是一个独立的 Claude Code 进程，通过 `spawn.py` 封装创建。Agent 之间不直接通信，而是通过文件系统中的 Markdown 文件传递结果。

### 断点续传

每道题目录维护一个 `.state` 文件，内容为一个单词：`planner` / `builder` / `evaluator` / `done`，表示下一个应执行的 Agent。启动时读取该文件，从记录的阶段继续执行。Agent 成功后才更新状态，失败不更新，因此可以随时中断并安全恢复。

### Agent 定义

所有 Agent 的 system prompt 和文件格式规范统一定义在 `outline.md` 中。新增角色或修改解题逻辑只需编辑该文件。新增 Skill（如数值计算、量纲检查）在文件末尾的 `## Skills` 部分添加定义即可。
