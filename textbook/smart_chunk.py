#!/usr/bin/env python3
"""
Smart chunking with paragraph-aware splitting and overlap.
Target: 2048 tokens (~3000 chars for Chinese), with 256 token overlap.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any


def estimate_tokens(text: str) -> int:
    """Estimate token count for Chinese text (roughly 1.5 chars per token)."""
    return int(len(text) / 1.5)


def find_paragraph_break(text: str, target_pos: int, window: int = 200) -> int:
    """
    Find the nearest paragraph break to target_pos.
    Paragraph breaks: double newlines, or single newline after period/question/exclamation.
    """
    # Search in window around target_pos
    start = max(0, target_pos - window)
    end = min(len(text), target_pos + window)
    search_region = text[start:end]

    # Look for double newlines first (strongest break)
    double_newline = search_region.rfind('\n\n', 0, target_pos - start)
    if double_newline != -1 and abs(start + double_newline - target_pos) < window:
        return start + double_newline + 2  # Skip the newlines

    # Look for single newline after sentence ending
    # Chinese sentence endings: 。！？；
    # English: . ! ? ;
    for i in range(target_pos - start, -1, -1):
        if i < len(search_region) and search_region[i] == '\n':
            # Check if previous char is sentence ending
            if i > 0 and search_region[i-1] in '。！？；.!?;':
                return start + i + 1  # Skip the newline

    # Fallback: look for any newline
    newline_pos = search_region.rfind('\n', 0, target_pos - start)
    if newline_pos != -1:
        return start + newline_pos + 1

    # Last resort: split at target_pos
    return target_pos


def smart_split(text: str, max_tokens: int = 2048, overlap_tokens: int = 256) -> List[str]:
    """
    Split text into chunks with paragraph-aware boundaries and overlap.

    Args:
        text: Input text
        max_tokens: Target max tokens per chunk (~3000 chars)
        overlap_tokens: Overlap between chunks (~375 chars)

    Returns:
        List of text chunks
    """
    max_chars = int(max_tokens * 1.5)  # Convert to chars
    overlap_chars = int(overlap_tokens * 1.5)

    chunks = []
    pos = 0

    while pos < len(text):
        # If remaining text fits in one chunk, take it all
        if len(text) - pos <= max_chars:
            chunks.append(text[pos:])
            break

        # Find a good break point near max_chars
        target_end = pos + max_chars
        break_point = find_paragraph_break(text, target_end, window=300)

        # Extract chunk
        chunk = text[pos:break_point].strip()
        chunks.append(chunk)

        # Move position with overlap
        pos = break_point - overlap_chars

        # Avoid infinite loop if overlap causes us to go backwards
        if pos < 0:
            pos = break_point

    return chunks


def chunk_entries(entries: List[Dict[str, Any]], max_tokens: int = 2048, overlap_tokens: int = 256) -> List[Dict[str, Any]]:
    """
    Chunk entries that exceed max_tokens, keep short ones as-is.
    """
    chunked = []

    for entry in entries:
        content = entry['content']
        tokens = estimate_tokens(content)

        if tokens <= max_tokens:
            # Keep as-is
            chunked.append(entry)
        else:
            # Split into chunks
            chunks = smart_split(content, max_tokens, overlap_tokens)

            for i, chunk_text in enumerate(chunks):
                chunk_entry = entry.copy()
                chunk_entry['content'] = chunk_text
                chunk_entry['chunk_index'] = i
                chunk_entry['total_chunks'] = len(chunks)
                chunk_entry['original_title'] = entry.get('title', '')

                # Update title to indicate it's a part
                if len(chunks) > 1:
                    chunk_entry['title'] = f"{entry.get('title', '')} (part {i+1}/{len(chunks)})"

                chunked.append(chunk_entry)

    return chunked


def main():
    base_dir = Path('/home/usamimira/PHY-LLM/CC_Integrater/textbook/merged')

    # Load files
    print("Loading files...")
    with open(base_dir / 'pure_content.json', 'r', encoding='utf-8') as f:
        pure_content = json.load(f)

    with open(base_dir / 'examples.json', 'r', encoding='utf-8') as f:
        examples = json.load(f)

    print(f"Pure content: {len(pure_content)} sections")
    print(f"Examples: {len(examples)} entries")

    # Chunk with smart splitting
    print("\nChunking pure content (max 2048 tokens, 256 token overlap)...")
    chunked_pure = chunk_entries(pure_content, max_tokens=2048, overlap_tokens=256)
    print(f"  Result: {len(chunked_pure)} chunks")

    print("\nChunking examples (max 2048 tokens, 256 token overlap)...")
    chunked_examples = chunk_entries(examples, max_tokens=2048, overlap_tokens=256)
    print(f"  Result: {len(chunked_examples)} chunks")

    # Combine for RAG
    all_chunks = chunked_pure + chunked_examples
    print(f"\nTotal chunks for RAG: {len(all_chunks)}")

    # Save chunked files
    with open(base_dir / 'chunked_pure_content.json', 'w', encoding='utf-8') as f:
        json.dump(chunked_pure, f, ensure_ascii=False, indent=2)

    with open(base_dir / 'chunked_examples.json', 'w', encoding='utf-8') as f:
        json.dump(chunked_examples, f, ensure_ascii=False, indent=2)

    with open(base_dir / 'chunks_final.json', 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    print(f"\nSaved:")
    print(f"  chunked_pure_content.json: {len(chunked_pure)} chunks")
    print(f"  chunked_examples.json: {len(chunked_examples)} chunks")
    print(f"  chunks_final.json: {len(all_chunks)} chunks")

    # Stats
    print("\nChunk size distribution:")
    sizes = [len(c['content']) for c in all_chunks]
    tokens = [estimate_tokens(c['content']) for c in all_chunks]
    print(f"  Min: {min(sizes)} chars ({min(tokens)} tokens)")
    print(f"  Max: {max(sizes)} chars ({max(tokens)} tokens)")
    print(f"  Avg: {sum(sizes)//len(sizes)} chars ({sum(tokens)//len(tokens)} tokens)")

    # Count split entries
    split_pure = sum(1 for c in chunked_pure if c.get('total_chunks', 1) > 1)
    split_examples = sum(1 for c in chunked_examples if c.get('total_chunks', 1) > 1)
    print(f"\nSplit entries:")
    print(f"  Pure content: {split_pure} sections split")
    print(f"  Examples: {split_examples} examples split")


if __name__ == '__main__':
    main()
