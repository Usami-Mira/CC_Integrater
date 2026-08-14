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
import sys
import torch
from pathlib import Path
from FlagEmbedding import BGEM3FlagModel
import weaviate
from weaviate.classes.init import AdditionalConfig


SCRIPT_DIR = Path(__file__).parent
TEXTBOOK_DIR = SCRIPT_DIR.parent
MODEL_DIR = Path(os.environ.get('RAG_MODEL_DIR', str(TEXTBOOK_DIR / 'models' / 'bge-m3')))
DATA_DIR = Path(os.environ.get('RAG_DATA_DIR', str(TEXTBOOK_DIR / 'weaviate_data')))


def load_model():
    """Load BGE-M3 model for query embedding."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = BGEM3FlagModel(str(MODEL_DIR), use_fp16=True, devices=device)
    return model


def embed_query(text, model):
    """Embed a query string using BGE-M3."""
    output = model.encode([text], max_length=512, return_dense=True,
                          return_sparse=False, return_colbert_vecs=False)
    return output['dense_vecs'][0].tolist()


def query_weaviate(query_text, top_k=5):
    """Query Weaviate and return top results."""
    model = load_model()
    query_vec = embed_query(query_text, model)

    client = weaviate.connect_to_embedded(
        persistence_data_path=str(DATA_DIR),
        additional_config=AdditionalConfig(timeout=(5, 30))
    )

    collection = client.collections.get("PhysicsChunks")
    results = collection.query.near_vector(
        near_vector=query_vec,
        limit=top_k,
        return_properties=["book", "chapter", "section", "title", "titleEn", "content", "contentEn"]
    )

    client.close()
    return results.objects


def format_results(query, objects):
    """Format query results as readable text."""
    lines = [f"RAG Query: \"{query}\"", f"Results: {len(objects)}", "=" * 60]

    for i, obj in enumerate(objects):
        p = obj.properties
        lines.append(f"\n[{i+1}] {p['title']}")
        lines.append(f"    EN: {p['titleEn']}")
        lines.append(f"    Book: {p['book']} | Chapter: {p['chapter']} | Section: {p['section']}")

        content = p['content']
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"    Content: {content}")

        content_en = p.get('contentEn', '')
        if content_en and content_en != content:
            if len(content_en) > 300:
                content_en = content_en[:300] + "..."
            lines.append(f"    EN: {content_en}")

        lines.append("-" * 40)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Query physics textbook RAG knowledge base")
    parser.add_argument("query", help="Search query (Chinese or English)")
    parser.add_argument("--top_k", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    objects = query_weaviate(args.query, args.top_k)

    if args.json:
        results = []
        for obj in objects:
            p = obj.properties
            results.append({
                "book": p['book'],
                "chapter": p['chapter'],
                "section": p['section'],
                "title": p['title'],
                "title_en": p['titleEn'],
                "content": p['content'],
                "content_en": p.get('contentEn', ''),
            })
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(format_results(args.query, objects))


if __name__ == '__main__':
    main()
