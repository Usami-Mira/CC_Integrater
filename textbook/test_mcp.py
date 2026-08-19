#!/usr/bin/env python3
"""
Test script for MCP server.
Sends a test query to verify the knowledge base works.
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from mcp_server import PhysicsKnowledgeBase


def main():
    """Test the knowledge base."""
    print("Initializing knowledge base...")
    kb = PhysicsKnowledgeBase()

    print("\n" + "="*60)
    print("Test 1: Query '库仑定律'")
    print("="*60)
    results = kb.query("库仑定律", top_k=3)
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] {r['title']}")
        print(f"    类型: {r['type']} | 书籍: {r['book']}")
        print(f"    {r['content'][:150]}...")

    print("\n" + "="*60)
    print("Test 2: Query '电偶极子' with book filter")
    print("="*60)
    results = kb.query("电偶极子", top_k=2, book="em")
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] {r['title']}")
        print(f"    类型: {r['type']} | 书籍: {r['book']}")
        print(f"    {r['content'][:150]}...")

    print("\n" + "="*60)
    print("Test 3: Query example type only")
    print("="*60)
    results = kb.query("牛顿第二定律", top_k=2, content_type="example")
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] {r['title']}")
        print(f"    类型: {r['type']} | 书籍: {r['book']}")
        print(f"    {r['content'][:150]}...")

    kb.close()
    print("\n✅ All tests passed!")


if __name__ == "__main__":
    main()
