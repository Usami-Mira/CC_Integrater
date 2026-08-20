#!/usr/bin/env python3
"""
Query the physics textbook RAG knowledge base using BGE-M3.

Usage:
    python3 query_rag.py "库仑定律"
    python3 query_rag.py "电偶极子电场" --top_k 5
    python3 query_rag.py "Newton's second law" --top_k 3
"""

import argparse
import json
import os
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent
TEXTBOOK_DIR = SCRIPT_DIR.parent
MODEL_SOURCE = os.environ.get('RAG_MODEL_DIR', 'BAAI/bge-m3')
DATA_DIR = Path(os.environ.get('RAG_DATA_DIR', str(TEXTBOOK_DIR / 'weaviate_data')))


def load_model():
    """Load BGE-M3 from a local path or Hugging Face model identifier."""
    import torch
    from FlagEmbedding import BGEM3FlagModel

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = BGEM3FlagModel(
        MODEL_SOURCE,
        use_fp16=(device == "cuda"),
        devices=device,
    )
    return model


def embed_query(text, model):
    """Embed a query string using BGE-M3."""
    output = model.encode([text], max_length=512, return_dense=True,
                          return_sparse=False, return_colbert_vecs=False)
    return output['dense_vecs'][0].tolist()


def query_weaviate(query_text, top_k=5):
    """Query Weaviate and return top results."""
    if not DATA_DIR.is_dir():
        raise FileNotFoundError(
            f"Weaviate data directory not found: {DATA_DIR}. "
            "Clone the repository with its textbook/weaviate_data directory "
            "or set RAG_DATA_DIR."
        )

    import weaviate
    from weaviate.classes.init import AdditionalConfig

    model = load_model()
    query_vec = embed_query(query_text, model)

    client = weaviate.connect_to_embedded(
        persistence_data_path=str(DATA_DIR),
        additional_config=AdditionalConfig(timeout=(5, 30))
    )

    try:
        collection = client.collections.get("PhysicsChunks")
        results = collection.query.near_vector(
            near_vector=query_vec,
            limit=top_k,
            return_properties=["book", "chapter", "section", "title", "content"]
        )
        return results.objects
    finally:
        client.close()


def format_results(query, objects):
    """Format query results as readable text."""
    lines = [f"RAG Query: \"{query}\"", f"Results: {len(objects)}", "=" * 60]

    for i, obj in enumerate(objects):
        p = obj.properties
        lines.append(f"\n[{i+1}] {p.get('title', '')}")
        lines.append(
            f"    Book: {p.get('book', '')} | Chapter: {p.get('chapter', '')} "
            f"| Section: {p.get('section', '')}"
        )

        content = p.get('content', '')
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"    Content: {content}")

        lines.append("-" * 40)

    return "\n".join(lines)


def results_as_dicts(objects):
    """Convert Weaviate result objects to the public JSON representation."""
    return [
        {
            "book": obj.properties.get('book', ''),
            "chapter": obj.properties.get('chapter', ''),
            "section": obj.properties.get('section', ''),
            "title": obj.properties.get('title', ''),
            "content": obj.properties.get('content', ''),
        }
        for obj in objects
    ]


def main():
    parser = argparse.ArgumentParser(description="Query physics textbook RAG knowledge base")
    parser.add_argument("query", help="Search query (Chinese or English)")
    parser.add_argument("--top_k", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    objects = query_weaviate(args.query, args.top_k)

    if args.json:
        print(json.dumps(results_as_dicts(objects), ensure_ascii=False, indent=2))
    else:
        print(format_results(args.query, objects))


if __name__ == '__main__':
    main()
