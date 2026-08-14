#!/usr/bin/env python3
"""
Chunk the merged markdown files into sections for RAG indexing.
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any


def parse_markdown_chunks(md_path: Path, book_name: str) -> List[Dict[str, Any]]:
    """
    Parse a markdown file and split into chunks by sections.

    Returns list of chunks with:
    - book: book name (em, mec, opt, thrm)
    - chapter: chapter number (if found)
    - section: section number (if found)
    - title: section title
    - content: text content
    - images: list of image paths
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by ## headers (sections)
    # Pattern: lines starting with ##
    sections = re.split(r'^## ', content, flags=re.MULTILINE)

    chunks = []
    current_chapter = None

    for i, section in enumerate(sections):
        if i == 0:
            # First part before any ## header (preamble)
            continue

        # Extract title (first line after ##)
        lines = section.strip().split('\n')
        title_line = lines[0].strip()
        content_lines = lines[1:]
        content_text = '\n'.join(content_lines).strip()

        # Skip empty sections
        if not content_text:
            continue

        # Extract chapter and section numbers from title
        chapter = None
        section_num = None

        # Match patterns like "1.1 两种电荷" or "§ 1. 静电的基本现象"
        if match := re.match(r'(\d+)\.(\d+)\s+(.+)', title_line):
            chapter = match.group(1)
            section_num = match.group(2)
            title = match.group(3)
        elif match := re.match(r'§\s*(\d+)\.\s+(.+)', title_line):
            chapter = match.group(1)
            title = match.group(2)
        elif match := re.match(r'第([一二三四五六七八九十\d]+)章\s+(.+)', title_line):
            chapter = match.group(1)
            title = match.group(2)
            current_chapter = chapter
        else:
            title = title_line

        # Update current chapter if we found one
        if chapter:
            current_chapter = chapter

        # Extract image references
        image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        images = re.findall(image_pattern, content_text)
        image_paths = [img[1] for img in images]  # Extract just the paths

        # Skip very small chunks (less than 100 chars) unless they have images
        if len(content_text) < 100 and not image_paths:
            continue

        # Skip preamble sections (序, 目录, etc.)
        if title in ['序', '目录', '第二版序', '第一版序']:
            continue

        chunks.append({
            'book': book_name,
            'chapter': current_chapter,
            'section': section_num,
            'title': title,
            'content': content_text,
            'images': image_paths,
            'full_title': title_line,
        })

    return chunks


def merge_small_chunks(chunks: List[Dict], min_size: int = 500, max_size: int = 3000) -> List[Dict]:
    """
    Merge small consecutive chunks from the same chapter to avoid too many tiny chunks.
    """
    if not chunks:
        return chunks

    merged = []
    current = chunks[0].copy()

    for chunk in chunks[1:]:
        # If same chapter and current is small, merge
        if (current['chapter'] == chunk['chapter'] and
            len(current['content']) < min_size):
            current['content'] += '\n\n' + chunk['content']
            current['images'].extend(chunk['images'])
            current['title'] += ' + ' + chunk['title']
        else:
            # Save current and start new
            merged.append(current)
            current = chunk.copy()

    merged.append(current)
    return merged


def main():
    base_dir = Path('/home/usamimira/PHY-LLM/CC_Integrater/textbook/merged')

    books = {
        'em': 'em.md',
        'mec': 'mec.md',
        'opt': 'opt.md',
        'thrm': 'thrm.md',
    }

    all_chunks = []

    for book_name, filename in books.items():
        md_path = base_dir / filename
        print(f"Processing {book_name}...")

        chunks = parse_markdown_chunks(md_path, book_name)
        print(f"  Raw chunks: {len(chunks)}")

        # Merge small chunks
        chunks = merge_small_chunks(chunks)
        print(f"  After merging: {len(chunks)}")

        all_chunks.extend(chunks)

    print(f"\nTotal chunks: {len(all_chunks)}")

    # Save to JSON
    output_path = base_dir / 'chunks.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    print(f"Saved to {output_path}")

    # Show some stats
    print("\nChunk statistics:")
    sizes = [len(c['content']) for c in all_chunks]
    print(f"  Min size: {min(sizes)} chars")
    print(f"  Max size: {max(sizes)} chars")
    print(f"  Avg size: {sum(sizes) / len(sizes):.0f} chars")

    images_count = sum(len(c['images']) for c in all_chunks)
    print(f"  Total images: {images_count}")

    # Show first 3 chunks
    print("\nFirst 3 chunks:")
    for i, chunk in enumerate(all_chunks[:3]):
        print(f"\n{i+1}. [{chunk['book']}] {chunk['title']}")
        print(f"   Chapter: {chunk['chapter']}, Section: {chunk['section']}")
        print(f"   Size: {len(chunk['content'])} chars")
        print(f"   Images: {len(chunk['images'])}")
        print(f"   Preview: {chunk['content'][:100]}...")


if __name__ == '__main__':
    main()
