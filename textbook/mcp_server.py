#!/usr/bin/env python3
"""
MCP Server for Physics Textbook RAG Knowledge Base.

This server exposes a tool for querying the physics textbook knowledge base
using BGE-M3 embeddings and Weaviate vector search.

Usage:
    python3 mcp_server.py

Configuration in Cherry Studio:
    Add this as an MCP server with command: python3 /path/to/mcp_server.py
"""

import os
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import torch
from FlagEmbedding import BGEM3FlagModel
import weaviate
from weaviate.classes.init import AdditionalConfig

# MCP SDK 2.0 high-level API
from mcp.server.mcpserver import MCPServer


# Paths
MODEL_SOURCE = os.environ.get('RAG_MODEL_DIR', 'BAAI/bge-m3')
DATA_DIR = Path(os.environ.get('RAG_DATA_DIR', str(ROOT / 'textbook' / 'weaviate_data')))


class PhysicsKnowledgeBase:
    """Physics textbook RAG knowledge base."""

    def __init__(self):
        """Initialize model and Weaviate client."""
        if not DATA_DIR.is_dir():
            raise FileNotFoundError(
                f"Weaviate data directory not found: {DATA_DIR}. Set RAG_DATA_DIR "
                "or restore textbook/weaviate_data from the repository."
            )

        print("Loading BGE-M3 model...", file=sys.stderr)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = BGEM3FlagModel(
            MODEL_SOURCE,
            use_fp16=(device == "cuda"),
            devices=device,
        )
        print(f"Model loaded on {device}", file=sys.stderr)

        print("Connecting to Weaviate...", file=sys.stderr)
        self.client = weaviate.connect_to_embedded(
            persistence_data_path=str(DATA_DIR),
            additional_config=AdditionalConfig(timeout=(5, 30))
        )
        self.collection = self.client.collections.get("PhysicsChunks")
        print("Weaviate connected", file=sys.stderr)

    def embed_query(self, text: str) -> list:
        """Embed a query string."""
        output = self.model.encode(
            [text],
            max_length=512,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False
        )
        return output['dense_vecs'][0].tolist()

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        book: Optional[str] = None,
        content_type: Optional[str] = None
    ) -> list:
        """
        Query the knowledge base.

        Args:
            query_text: Search query (Chinese or English)
            top_k: Number of results to return
            book: Filter by book (em/mec/opt/thrm)
            content_type: Filter by type (content/example)

        Returns:
            List of matching chunks with metadata
        """
        query_vec = self.embed_query(query_text)

        # Build filters
        filters = None
        if book or content_type:
            from weaviate.classes.query import Filter
            filter_list = []
            if book:
                filter_list.append(Filter.by_property("book").equal(book))
            if content_type:
                filter_list.append(Filter.by_property("type").equal(content_type))

            if len(filter_list) == 1:
                filters = filter_list[0]
            else:
                filters = filter_list[0] & filter_list[1]

        # Query Weaviate
        results = self.collection.query.near_vector(
            near_vector=query_vec,
            limit=top_k,
            filters=filters,
            return_properties=[
                "book", "chapter", "section", "title",
                "content", "type", "chunkIndex", "totalChunks"
            ]
        )

        # Format results
        formatted = []
        for obj in results.objects:
            p = obj.properties
            formatted.append({
                "book": p['book'],
                "chapter": p['chapter'],
                "section": p['section'],
                "title": p['title'],
                "content": p['content'],
                "type": p['type'],
                "chunk_info": f"{p['chunkIndex']+1}/{p['totalChunks']}" if p['totalChunks'] > 1 else None,
            })

        return formatted

    def close(self):
        """Close Weaviate connection."""
        self.client.close()


# Initialize knowledge base
print("Initializing Physics Knowledge Base...", file=sys.stderr)
kb = PhysicsKnowledgeBase()
print("Ready!", file=sys.stderr)


# Create MCP server with high-level API
mcp = MCPServer("physics-knowledge-base")


@mcp.tool()
def query_physics_knowledge(
    query: str,
    top_k: int = 5,
    book: Optional[str] = None,
    content_type: Optional[str] = None
) -> str:
    """
    查询物理教科书知识库。搜索电磁学、力学、光学、热学教材中的概念、定律和例题。

    Args:
        query: 搜索查询（中文或英文），例如：'库仑定律'、'牛顿第二定律'、'电偶极子电场'
        top_k: 返回结果数量（默认 5）
        book: 按书籍过滤：em（电磁学）、mec（力学）、opt（光学）、thrm（热学）
        content_type: 按内容类型过滤：content（正文）、example（例题）
    """
    # Query knowledge base
    results = kb.query(query, top_k, book, content_type)

    # Format as text
    if not results:
        return "未找到相关内容。"

    output = [f"查询: \"{query}\"\n找到 {len(results)} 个结果:\n"]
    for i, r in enumerate(results, 1):
        chunk_info = f" ({r['chunk_info']})" if r['chunk_info'] else ""
        output.append(f"\n{'='*60}")
        output.append(f"[{i}] {r['title']}{chunk_info}")
        output.append(f"    类型: {r['type']} | 书籍: {r['book']} | 章节: {r['chapter']}")
        output.append(f"    内容:\n{r['content']}\n")

    return "\n".join(output)


if __name__ == "__main__":
    mcp.run(transport="stdio")
