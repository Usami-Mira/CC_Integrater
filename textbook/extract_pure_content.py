#!/usr/bin/env python3
"""
Extract pure textbook content (without examples and exercises).
Removes lines matching example or exercise patterns.
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any


def extract_pure_content(md_path: Path, book_name: str) -> List[Dict[str, Any]]:
    """
    Extract pure content by removing examples and exercises.
    Keep only section content (split by ## headers).
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')

    # Split by ## headers (sections)
    sections = []
    current_section = None
    current_chapter = None

    for line in lines:
        # Track chapter context
        if match := re.match(r'^## .*?第([一二三四五六七八九十\d]+)章\s+(.+)', line):
            current_chapter = match.group(1)

        # Detect section start
        if line.startswith('## '):
            # Save previous section
            if current_section and current_section['content']:
                sections.append(current_section)

            # Start new section
            title = line[3:].strip()  # Remove "## "

            # Extract chapter and section numbers
            chapter = None
            section_num = None

            if match := re.match(r'(\d+)\.(\d+)\s+(.+)', title):
                chapter = match.group(1)
                section_num = match.group(2)
                title = match.group(3)
            elif match := re.match(r'§\s*(\d+)\.\s+(.+)', title):
                chapter = match.group(1)
                title = match.group(2)
            elif match := re.match(r'第([一二三四五六七八九十\d]+)章\s+(.+)', title):
                chapter = match.group(1)
                title = match.group(2)
                current_chapter = chapter

            current_section = {
                'book': book_name,
                'chapter': chapter or current_chapter,
                'section': section_num,
                'title': title,
                'content': '',
                'type': 'content',
            }

        # Accumulate content, but skip examples and exercises
        elif current_section is not None:
            # Skip example lines
            if re.match(r'^例题\s*\d+', line):
                continue

            # Skip exercise lines
            if re.match(r'^\d+-\d+\.\s+', line):
                continue

            # Add line to current section
            if current_section['content']:
                current_section['content'] += '\n' + line
            else:
                current_section['content'] = line

    # Don't forget the last section
    if current_section and current_section['content']:
        sections.append(current_section)

    # Filter out empty or very small sections
    sections = [s for s in sections if len(s['content'].strip()) > 100]

    return sections


def main():
    base_dir = Path('/home/usamimira/PHY-LLM/CC_Integrater/textbook/merged')

    books = {
        'em': 'em.md',
        'mec': 'mec.md',
        'opt': 'opt.md',
        'thrm': 'thrm.md',
    }

    all_sections = []

    for book_name, filename in books.items():
        md_path = base_dir / filename
        print(f"Processing {book_name}...")

        sections = extract_pure_content(md_path, book_name)
        print(f"  Found {len(sections)} sections")

        all_sections.extend(sections)

    print(f"\nTotal sections: {len(all_sections)}")

    # Save to JSON
    output_path = base_dir / 'pure_content.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_sections, f, ensure_ascii=False, indent=2)

    print(f"Saved to {output_path}")

    # Show stats
    print("\nContent statistics:")
    sizes = [len(s['content']) for s in all_sections]
    print(f"  Min size: {min(sizes)} chars")
    print(f"  Max size: {max(sizes)} chars")
    print(f"  Avg size: {sum(sizes) / len(sizes):.0f} chars")

    # Show first 3 sections
    print("\nFirst 3 sections:")
    for i, section in enumerate(all_sections[:3]):
        print(f"\n{i+1}. [{section['book']}] {section['title']}")
        print(f"   Chapter: {section['chapter']}, Section: {section['section']}")
        print(f"   Size: {len(section['content'])} chars")
        print(f"   Preview: {section['content'][:200]}...")


if __name__ == '__main__':
    main()
