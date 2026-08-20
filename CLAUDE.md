# Project Configuration

## CRITICAL: Directory Structure and Working Directory

**Project Root**: the directory containing this file

**Bash tool default working directory**: the project root

RAG scripts resolve paths relative to their own location and can run from the project root:
```bash
python3 textbook/rag_build/query_rag.py "库仑定律"
```

### Directory Layout
```
CC_Integrater/                             ← Project root (Bash default cwd)
├── run.py, spawn.py, stream_parser.py     ← Agent orchestration scripts
├── config.json                            ← Agent configuration
├── prompts/                               ← Agent system prompts
│   ├── orchestrator.md, planner.md, builder.md, evaluator.md
│   ├── architecture.md
│   └── skills/                            ← Skill definitions
├── problems/                              ← Problem workspaces (e.g., CPhO42j/)
└── textbook/                              ← RAG knowledge base (SEPARATE WORKING DIR)
    ├── rag_build/                         ← RAG scripts
    │   ├── embed_bge.py                   ← Embedding generation
    │   └── query_rag.py                   ← RAG query tool
    ├── weaviate_data/                     ← Weaviate vector database
    ├── merged/                            ← Optional local rebuild inputs (not shipped)
    └── *_output/                          ← OCR output directories
```

## Key Paths

- **Model**: `BAAI/bge-m3` from Hugging Face by default (1024-dim, multilingual)
- **Weaviate data**: `textbook/weaviate_data`
- **RAG scripts**: `textbook/rag_build/`
  - `embed_bge.py` — Generate embeddings and store in Weaviate
  - `query_rag.py` — Query the physics textbook knowledge base
- **Rebuild input**: set `RAG_CHUNKS_FILE` to a local `chunks_final.json` (not shipped)

## Environment Variables

These variables are optional; `run.py` supplies portable defaults:
```bash
export RAG_MODEL_DIR=/path/to/local/bge-m3
export RAG_DATA_DIR=/path/to/weaviate_data
export RAG_CHUNKS_FILE=/path/to/chunks_final.json
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

1. **Dependencies**: create a local virtual environment and install `requirements.txt`
2. **Rebuild data**: `chunks_final.json` is intentionally not shipped; set `RAG_CHUNKS_FILE`
3. **BGEM3FlagModel parameter**: `devices=` not `device=`
4. **Template variables**: Use `.replace()` not `.format()` to preserve runtime placeholders like `{workspace}`
5. **HuggingFace downloads**: users in China can set `HF_ENDPOINT` and `HF_HUB_DISABLE_XET=1`
