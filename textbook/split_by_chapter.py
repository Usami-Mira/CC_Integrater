#!/usr/bin/env python3
"""
Split textbook content and examples by chapter.

Chinese numerals (一, 二, 三, etc.) are section markers within chapters.
This script:
1. Builds a chapter context from pure_content.json
2. Uses that context to assign correct chapter numbers to examples
3. Outputs files organized by actual chapter numbers
"""

import json
from pathlib import Path
from collections import defaultdict


# Chinese numerals that represent sections within chapters
SECTION_MARKERS = {'一', '二', '三', '四', '五', '六', '七', '八', '九', '十'}


def is_section_marker(chapter):
    """Check if a chapter value is a section marker."""
    return chapter in SECTION_MARKERS


def build_chapter_mapping(content_items):
    """
    Build a mapping of (book, section_marker) -> chapter_number
    by tracking the chapter context in pure_content.json
    """
    mapping = {}
    current_chapter = {}  # per book

    for item in content_items:
        book = item.get("book")
        ch = item.get("chapter")

        if is_section_marker(ch):
            # This is a section within the current chapter
            if book in current_chapter and current_chapter[book]:
                mapping[(book, ch)] = current_chapter[book]
        elif ch and str(ch).isdigit():
            # This is a chapter number
            current_chapter[book] = ch

    return mapping


def assign_chapter_to_examples(examples, chapter_mapping):
    """
    Assign proper chapter numbers to examples based on the mapping.
    """
    result = []

    for item in examples:
        book = item.get("book")
        ch = item.get("chapter")

        if is_section_marker(ch):
            # Look up the actual chapter from mapping
            actual_chapter = chapter_mapping.get((book, ch))
            if actual_chapter:
                item_copy = item.copy()
                item_copy["chapter"] = actual_chapter
                item_copy["section_marker"] = ch
                result.append(item_copy)
            else:
                # No mapping found, keep as is
                result.append(item)
        else:
            result.append(item)

    return result


def assign_chapters_to_content(content_items):
    """
    Assign proper chapter numbers to content items.
    Chinese numerals are sections within the current chapter.
    """
    result = []
    current_chapter = None

    for item in content_items:
        book = item.get("book")
        ch = item.get("chapter")

        if is_section_marker(ch):
            # This is a section within the current chapter
            if current_chapter:
                item_copy = item.copy()
                item_copy["chapter"] = current_chapter
                item_copy["section_marker"] = ch
                result.append(item_copy)
            else:
                result.append(item)
        elif ch and str(ch).isdigit():
            current_chapter = ch
            result.append(item)
        else:
            result.append(item)

    return result


def split_by_chapter():
    """Split pure_content.json and examples.json by chapter."""
    merged_dir = Path(__file__).parent / "merged"
    output_dir = merged_dir / "by_chapter"

    # Load data
    print("Loading data...")
    with open(merged_dir / "pure_content.json") as f:
        content = json.load(f)
    print(f"  Loaded {len(content)} content items")

    with open(merged_dir / "examples.json") as f:
        examples = json.load(f)
    print(f"  Loaded {len(examples)} examples")

    # Build chapter mapping from content
    print("\nBuilding chapter mapping...")
    chapter_mapping = build_chapter_mapping(content)
    print(f"  Mapped {len(chapter_mapping)} section markers to chapters")

    # Assign chapters
    print("Assigning chapters...")
    content = assign_chapters_to_content(content)
    examples = assign_chapter_to_examples(examples, chapter_mapping)

    # Group by book and chapter
    chapters = defaultdict(lambda: {"content": [], "examples": []})

    for item in content:
        book = item.get("book", "unknown")
        chapter = item.get("chapter") or "frontmatter"
        key = (book, str(chapter))
        chapters[key]["content"].append(item)

    for item in examples:
        book = item.get("book", "unknown")
        chapter = item.get("chapter") or "frontmatter"
        key = (book, str(chapter))
        chapters[key]["examples"].append(item)

    # Create output directories and write files
    print(f"\nWriting to {output_dir}...")
    for (book, chapter), data in sorted(chapters.items()):
        book_dir = output_dir / book
        book_dir.mkdir(parents=True, exist_ok=True)

        # Create filename
        if chapter == "frontmatter":
            filename = "frontmatter.json"
        else:
            filename = f"chapter_{chapter}.json"

        output_path = book_dir / filename

        # Clean up internal markers before writing
        clean_content = []
        for item in data["content"]:
            clean_item = {k: v for k, v in item.items() if k != "section_marker"}
            clean_content.append(clean_item)

        clean_examples = []
        for item in data["examples"]:
            clean_item = {k: v for k, v in item.items() if k != "section_marker"}
            clean_examples.append(clean_item)

        # Write combined data
        combined = {
            "book": book,
            "chapter": chapter if chapter != "frontmatter" else None,
            "content": clean_content,
            "examples": clean_examples
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(combined, f, ensure_ascii=False, indent=2)

        print(f"  {book}/{filename}: {len(clean_content)} content, {len(clean_examples)} examples")

    print(f"\n✓ Done! Files written to {output_dir}")


if __name__ == "__main__":
    split_by_chapter()
