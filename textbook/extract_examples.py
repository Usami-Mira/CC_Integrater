#!/usr/bin/env python3
"""
Extract example problems (例题) from textbook markdown files.
Examples demonstrate problem-solving methods and should be included in RAG knowledge base.
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any


def extract_examples(md_path: Path, book_name: str) -> List[Dict[str, Any]]:
    """
    Extract all example problems from a markdown file.

    Pattern: "例题 N" followed by problem statement and solution.
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by lines for easier processing
    lines = content.split('\n')

    examples = []
    current_example = None
    current_chapter = None

    for i, line in enumerate(lines):
        # Track chapter context
        if match := re.match(r'^## .*?第([一二三四五六七八九十\d]+)章\s+(.+)', line):
            current_chapter = match.group(1)

        # Detect example start: "例题 N" or "例题N"
        if match := re.match(r'^例题\s*(\d+)[.、\s]', line):
            # Save previous example if exists
            if current_example and current_example['content']:
                examples.append(current_example)

            # Start new example
            example_num = match.group(1)
            current_example = {
                'book': book_name,
                'chapter': current_chapter,
                'example_num': example_num,
                'title': line.strip(),
                'content': '',
                'type': 'example',
            }

        # Accumulate content for current example
        elif current_example is not None:
            # Stop if we hit next section header or next example
            if re.match(r'^## |^例题\s*\d+', line):
                # Save current example
                if current_example['content']:
                    examples.append(current_example)
                current_example = None

                # Check if this line starts a new example
                if match := re.match(r'^例题\s*(\d+)[.、\s]', line):
                    example_num = match.group(1)
                    current_example = {
                        'book': book_name,
                        'chapter': current_chapter,
                        'example_num': example_num,
                        'title': line.strip(),
                        'content': '',
                        'type': 'example',
                    }
            else:
                # Add line to current example content
                if current_example['content']:
                    current_example['content'] += '\n' + line
                else:
                    current_example['content'] = line

    # Don't forget the last example
    if current_example and current_example['content']:
        examples.append(current_example)

    return examples


def main():
    base_dir = Path('/home/usamimira/PHY-LLM/CC_Integrater/textbook/merged')

    books = {
        'em': 'em.md',
        'mec': 'mec.md',
        'opt': 'opt.md',
        'thrm': 'thrm.md',
    }

    all_examples = []

    for book_name, filename in books.items():
        md_path = base_dir / filename
        print(f"Processing {book_name}...")

        examples = extract_examples(md_path, book_name)
        print(f"  Found {len(examples)} examples")

        all_examples.extend(examples)

    print(f"\nTotal examples: {len(all_examples)}")

    # Save to JSON
    output_path = base_dir / 'examples.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_examples, f, ensure_ascii=False, indent=2)

    print(f"Saved to {output_path}")

    # Show stats
    print("\nExample statistics:")
    sizes = [len(e['content']) for e in all_examples]
    print(f"  Min size: {min(sizes)} chars")
    print(f"  Max size: {max(sizes)} chars")
    print(f"  Avg size: {sum(sizes) / len(sizes):.0f} chars")

    # Show first 3 examples
    print("\nFirst 3 examples:")
    for i, example in enumerate(all_examples[:3]):
        print(f"\n{i+1}. [{example['book']}] {example['title']}")
        print(f"   Chapter: {example['chapter']}")
        print(f"   Size: {len(example['content'])} chars")
        print(f"   Preview: {example['content'][:200]}...")


if __name__ == '__main__':
    main()
