# Project Configuration

## CRITICAL: Directory Structure and Working Directory

**Project Root**: `/home/usamimira/PHY-LLM/CC_Integrater`

**Bash tool default working directory**: `/home/usamimira/PHY-LLM/CC_Integrater`

**IMPORTANT**: RAG scripts MUST run from `textbook/` subdirectory. Always use subshell with `cd`:
```bash
(source rag_env/bin/activate && python3 rag_build/embed_bge.py)
```

### Directory Layout
```
/home/usamimira/PHY-LLM/CC_Integrater/     ← Project root (Bash default cwd)
├── run.py, spawn.py, stream_parser.py     ← Agent orchestration scripts
├── config.json                            ← Agent configuration
├── prompts/                               ← Agent system prompts
│   ├── orchestrator.md, planner.md, builder.md, evaluator.md
│   ├── architecture.md
│   └── skills/                            ← Skill definitions
├── problems/                              ← Problem workspaces (e.g., CPhO42j/)
└── textbook/                              ← RAG knowledge base (SEPARATE WORKING DIR)
    ├── rag_env/                           ← Python virtual environment
    │   └── bin/activate                   ← Activate script
    ├── rag_build/                         ← RAG scripts (run from textbook/)
    │   ├── embed_bge.py                   ← Embedding generation
    │   └── query_rag.py                   ← RAG query tool
    ├── models/bge-m3/                     ← BGE-M3 model files
    ├── weaviate_data/                     ← Weaviate vector database
    ├── merged/                            ← Processed textbook chunks
    └── *_output/                          ← OCR output directories
```

**Key Rule**: When running RAG scripts, the working directory MUST be `textbook/`. Use subshell:
```bash
(source rag_env/bin/activate && python3 rag_build/<script>.py)
```

## Key Paths

- **Models**: `/home/usamimira/PHY-LLM/CC_Integrater/textbook/models/bge-m3` (BGE-M3, 1024-dim, multilingual)
- **Weaviate data**: `/home/usamimira/PHY-LLM/CC_Integrater/textbook/weaviate_data`
- **RAG scripts**: `/home/usamimira/PHY-LLM/CC_Integrater/textbook/rag_build/`
  - `embed_bge.py` — Generate embeddings and store in Weaviate
  - `query_rag.py` — Query the physics textbook knowledge base
- **Merged chunks**: `/home/usamimira/PHY-LLM/CC_Integrater/textbook/merged/chunks_translated.json` (1139 chunks)

## Environment Variables

When running RAG scripts, set these (or `run.py` sets them automatically):
```bash
export RAG_MODEL_DIR=/home/usamimira/PHY-LLM/CC_Integrater/textbook/models/bge-m3
export RAG_DATA_DIR=/home/usamimira/PHY-LLM/CC_Integrater/textbook/weaviate_data
```

For HuggingFace downloads (user in China):
```bash
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DISABLE_XET=1
```

## BGE-M3 Model Notes

- **Dimensions**: 1024 (not 768 like BGE-base)
- **Multilingual**: Handles Chinese natively, no translation needed
- **Max tokens**: 8192
- **FlagEmbedding parameter**: Use `devices=` (plural), NOT `device=`
- **Load on GPU**: `BGEM3FlagModel(path, use_fp16=True, devices="cuda")`

## Agent Workflow

- **Orchestrator**: Main controller, spawns sub-agents via `spawn.py`
- **Planner**: Analyzes problem, writes solution plan to `plan.md`
- **Builder**: Implements solution, writes to `solution.md`
- **Evaluator**: Reviews solution, writes to `evaluation.md`
- **Max iterations**: 2 (Builder → Evaluator feedback loop)

## LaTeX Requirement

All physics formulas must use LaTeX inline math (`$...$`), not Unicode symbols:
- ✅ Correct: `$F = ma$`, `$E_k = \frac{1}{2}mv^2$`
- ❌ Wrong: `F = ma`, `Ek = ½mv²`

## Common Pitfalls

1. **Virtual environment path**: Always use absolute path `/home/usamimira/PHY-LLM/CC_Integrater/textbook/rag_env/bin/activate`
2. **Working directory**: RAG scripts expect to run from `textbook/` directory
3. **BGEM3FlagModel parameter**: `devices=` not `device=`
4. **Template variables**: Use `.replace()` not `.format()` to preserve runtime placeholders like `{workspace}`
5. **HuggingFace downloads**: Must set `HF_ENDPOINT` and `HF_HUB_DISABLE_XET=1` for China mirror
