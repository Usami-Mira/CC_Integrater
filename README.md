# CC_Integrater — 多 Agent 协作物理解题系统

## 简介

本项目通过 Claude Code CLI 编排三个 Agent（Planner / Builder / Evaluator）自动解决物理题目。Planner 分析题目并制定解题计划，Builder 执行完整推导求解，Evaluator 审查结果并反馈。若审查未通过，系统自动将 Builder 的结果送回修正，最多迭代 2 次。每道题支持断点续传，中断后可自动从上次进度继续。系统使用 Git 自动追踪解题过程的完整演变，支持查看每个阶段的变更历史和版本对比。

## 环境安装

### 安装 Claude Code

本项目依赖 [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview) CLI 工具：

```bash
npm install -g @anthropic-ai/claude-code
```

### 安装 Git

系统使用 Git 进行版本控制和解题过程追踪：

```bash
# Ubuntu/Debian
sudo apt-get install git

# macOS
brew install git

# Windows
# 下载 Git for Windows: https://git-scm.com/download/win
```

验证安装：
```bash
git --version
```

**注意**：Git 用于追踪每道题的解题过程演变（plan → solution → review），支持自动提交和迭代历史查看。

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

## 运行测试

```bash
# 运行 Git 集成测试（权限配置、Git 初始化等）
python3 test_git_integration.py -v

# 运行文本处理管道测试（分块、token 估算等）
python3 textbook/run_tests.py

# 或运行单个测试文件
python3 textbook/test_smart_chunk.py -v
```

测试覆盖：
- Git 版本控制初始化和权限配置
- 文本处理管道的核心逻辑：智能分块、段落边界检测、token 估算
- MCP 服务器和知识库查询

## 查看结果

每道题的子文件夹中，用户需要关注的文件：

| 文件 | 说明 |
|------|------|
| `plan.md` | 解题计划（物理情景、适用定律、解题路线） |
| `solution.md` | 完整求解过程与最终答案 |
| `review.md` | 审查结果，首行为 `PASS` 或 `REVISE` |
| `final_summary.md` | 最终汇总：执行统计 + 完整答案（**主要阅读文件**） |

多题场景下，父目录还会生成 `batch_summary.md`，汇总所有子题的状态和答案摘要。

### 查看解题过程历史

每道题的工作目录都是一个 Git 仓库，可以查看解题过程的完整演变：

```bash
cd problems/example_single

# 查看提交历史
git log --oneline

# 典型输出：
# a1b2c3d final: summary
# e4f5g6h review: v2 revised
# i7j8k9l solution: v2 revised
# m0n1o2p review: v1 complete
# q3r4s5t solution: v1 complete
# t9u0v1w plan: v1 complete
# x2y3z4a init: create output files

# 查看 solution.md 的变更历史
git log -p solution.md

# 对比 v1 和 v2 的差异（如果有 REVISE）
git diff HEAD~2 solution.md
```

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
├── config.json              # 项目配置（模型名、超时时间、并行数）
├── run.py                   # 入口脚本：组装 Orchestrator prompt 并启动
├── spawn.py                 # 子进程辅助脚本：创建 Planner/Builder/Evaluator，含权限配置
├── CLAUDE.md                # Claude Code 项目配置
├── PROJECT_STRUCTURE.md     # 详细项目结构和开发指南
├── test_git_integration.py  # Git 集成单元测试
├── prompts/                 # Agent 定义和 Skill 定义
│   ├── orchestrator.md      # Orchestrator system prompt（含 Git 工作流）
│   ├── planner.md           # Planner system prompt
│   ├── builder.md           # Builder system prompt
│   ├── evaluator.md         # Evaluator system prompt
│   ├── architecture.md      # 执行顺序和反馈规则
│   └── skills/              # Skill 定义
│       ├── calculation.md
│       ├── dimension_check.md
│       └── knowledge_base.md
├── problems/                # 题目目录
│   └── <exam>/
│       ├── <n>/
│       │   ├── problem.md         # 输入：题目
│       │   ├── plan.md            # Planner 输出
│       │   ├── solution.md        # Builder 输出
│       │   ├── review.md          # Evaluator 输出
│       │   ├── final_summary.md   # 最终汇总
│       │   ├── .state             # 断点状态
│       │   ├── .git/              # Git 仓库（自动创建，追踪解题过程）
│       │   └── .*.result/metrics  # 内部缓存
│       └── ...
├── textbook/                # 教科书 RAG 知识库（详见下方）
│   ├── batch_parse.py               # 分卷合并
│   ├── fix_formulas.py              # OCR 公式修正
│   ├── extract_image_context.py     # 图片上下文提取
│   ├── mcp_server.py                # MCP 服务器（Cherry Studio 集成）
│   ├── split_by_chapter.py          # 按章节切分内容
│   ├── rag_build/                   # RAG 构建脚本
│   │   ├── chunk_markdown.py        # 文本分块
│   │   ├── translate_chunks.py      # 中文→英文翻译
│   │   └── embed_bge.py             # 向量嵌入 + Weaviate 存储
│   ├── by_chapter/                  # 按章节组织的知识库
│   └── weaviate_data/               # Weaviate 向量数据库
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

各 Agent 的 system prompt 分别定义在 `prompts/` 目录下的独立 `.md` 文件中。`run.py` 启动时读取所有文件并组装成完整的 Orchestrator prompt（含嵌入的 sub-Agent prompt 和 Skill 定义）。新增角色只需在 `prompts/` 下添加 `.md` 文件并更新 `run.py` 的组装逻辑。新增 Skill 只需在 `prompts/skills/` 下添加 `.md` 文件，并在对应 Agent prompt 中声明引用。

### Git 版本控制

每道题的工作目录在启动时自动初始化为 Git 仓库，用于追踪解题过程的完整演变。

**提交时机：**

Orchestrator 在以下节点自动提交：

| 时机 | 提交消息 |
|------|----------|
| 初始化后 | `init: workspace setup with problem files` |
| 预创建空文件后 | `init: create output files` |
| Planner 完成后 | `plan: v1 complete` |
| Builder 完成后 | `solution: v1 complete` 或 `solution: v2 revised` |
| Evaluator 完成后 | `review: v1 complete` 或 `review: v2 revised` |
| 写入汇总后 | `final: summary` |

**典型 Git 历史（一次通过）：**

```bash
$ git log --oneline
a1b2c3d final: summary
e4f5g6h review: v1 complete
i7j8k9l solution: v1 complete
m0n1o2p plan: v1 complete
q3r4s5t init: create output files
u6v7w8x init: workspace setup with problem files
```

**典型 Git 历史（经历 REVISE）：**

```bash
$ git log --oneline
a1b2c3d final: summary
e4f5g6h review: v2 revised
i7j8k9l solution: v2 revised
m0n1o2p review: v1 complete
q3r4s5t solution: v1 complete
t9u0v1w plan: v1 complete
x2y3z4a init: create output files
```

**Agent 的 Git 权限：**

Sub-Agent（Planner/Builder/Evaluator）可以使用只读 Git 命令查看历史，但不能修改仓库：
- ✅ 允许：`git status`、`git diff`、`git log`、`git add`
- ❌ 禁止：`git commit`、`git reset`、`git checkout`、`git push`

这样 Agent 可以查看文件变更历史（如 `git diff HEAD~1 solution.md` 查看 Builder 的修改），但提交由 Orchestrator 统一管理，确保提交历史的一致性和可追溯性。

### 权限控制

每个 Agent 的工具权限通过 `spawn.py` 中的 `AGENT_PROFILES` 字典精确控制，使用 Claude Code 的 `--allowed-tools` 参数实现命令级别的权限隔离。

**权限配置示例：**

```python
AGENT_PROFILES = {
    "Planner": (
        "Read,"                          # 读取文件
        "Write,"                         # 写入文件
        "Edit,"                          # 编辑文件
        "Bash(python3 *),"               # 运行 Python 脚本
        "Bash(source * && python3 *),"   # 激活虚拟环境后运行脚本
        "Bash(git status*),"             # Git 状态查询
        "Bash(git diff*),"               # Git 差异比较
        "Bash(git log*),"                # Git 历史查看
        "Bash(git add *)"                # Git 暂存文件
    ),
    # Builder 和 Evaluator 权限相同
}
```

**安全设计：**

1. **命令模式匹配**：`Bash(python3 *)` 只允许以 `python3` 开头的命令，阻止 `rm`、`curl` 等危险操作
2. **最小权限原则**：Agent 只能执行解题必需的命令，无法安装软件包或访问网络
3. **Git 写入隔离**：只有 Orchestrator 可以执行 `git commit`，Sub-Agent 只能读取
4. **工作目录限制**：Agent 被约束在 `{workspace}` 目录内，无法访问其他题目或项目文件

**权限覆盖：**

如果需要临时调整权限，可以通过 `spawn.py` 的 `--tools` 参数覆盖：

```bash
python3 spawn.py Planner problems/example --tools "Read,Write,Bash"
```

但通常不需要手动调整，默认配置已针对各 Agent 的职责优化。

---

## 教科书 RAG 知识库

`textbook/` 目录包含从 4 本高中物理竞赛教科书（电磁学、力学、光学、热学）PDF 扫描件构建的 RAG 知识库，为解题 Agent 提供物理知识检索能力。

### 构建流程

| 步骤 | 脚本 | 说明 |
|------|------|------|
| 1. OCR | MinerU Web API | PDF → 结构化 Markdown + 图片 |
| 2. 公式修正 | `fix_formulas.py` | LLM 纠正 OCR 公式错误 |
| 3. 图片上下文 | `extract_image_context.py` | 提取图文关联 |
| 4. 合并分卷 | `batch_parse.py` | 多 part → 单文件 Markdown |
| 5. 文本分块 | `rag_build/chunk_markdown.py` | 按章节切分为 1139 个语义块 |
| 6. 翻译 | `rag_build/translate_chunks.py` | Qwen 3.6 Flash 中英双语（20 并发） |
| 7. 向量嵌入 | `rag_build/embed_bge.py` | BGE-base-en-v1.5 → Weaviate |

### 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| OCR | MinerU Web API | 结构化输出，支持公式和图片 |
| 翻译 | Qwen 3.6 Flash | 快速、物理术语准确 |
| 嵌入模型 | BGE-base-en-v1.5 | 768维，语义检索效果好 |
| 向量数据库 | Weaviate Embedded | 无需 Docker，本地持久化 |

### 数据说明

原始 PDF、OCR 输出、合并后的 Markdown、图片和嵌入模型文件均通过 `.gitignore` 排除，不纳入版本管理。构建好的 Weaviate 数据库（`weaviate_data/`，61MB）直接包含在仓库中，clone 后即可使用。如需从头重建知识库，按上表步骤依次运行即可。
