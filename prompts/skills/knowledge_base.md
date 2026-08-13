# Skill: knowledge_base

物理教科书知识库检索（基于 4 本竞赛教科书：电磁学 em、力学 mec、光学 opt、热学 thrm）。

workspace 中已包含 `query_rag.py` 查询脚本，用 Bash 调用：
```
source {project_root}/textbook/rag_env/bin/activate && python3 {workspace}/query_rag.py "查询内容" --top_k 5
```
- `{project_root}` 是项目根目录（包含 prompts/ 的那一级）
- 支持中英文查询，返回教科书相关章节内容（含公式）
- `--top_k` 控制返回条数，默认 5，建议 3-5
- `--json` 可选，输出 JSON 格式便于解析

**何时使用：**
- 不确定某个物理定律的准确表述或适用条件时
- 需要查阅公式的标准形式、常数取值时
- 验证某个物理概念的定义或推导过程时

**使用约束：**
- 仅在确实需要时使用，不要对每道题都查询
- 查询结果作为参考，仍需自行判断其对当前题目的适用性
