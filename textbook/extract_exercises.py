#!/usr/bin/env python3
"""
Extract exercises (习题) from textbook markdown files.
Exercises are numbered like "1-1.", "2-3." etc.
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any


def extract_exercises(md_path: Path, book_name: str) -> List[Dict[str, Any]]:
    """
    Extract all exercises from a markdown file.

    Pattern: "N-M." where N is chapter, M is exercise number.
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')

    exercises = []
    current_exercise = None
    current_chapter = None

    for i, line in enumerate(lines):
        # Track chapter context
        if match := re.match(r'^## .*?第([一二三四五六七八九十\d]+)章', line):
            current_chapter = match.group(1)

        # Detect exercise start: "N-M." pattern
        if match := re.match(r'^(\d+)-(\d+)\.\s+', line):
            # Save previous exercise if exists
            if current_exercise and current_exercise['content']:
                exercises.append(current_exercise)

            # Start new exercise
            chapter_num = match.group(1)
            exercise_num = match.group(2)
            current_exercise = {
                'book': book_name,
                'chapter': chapter_num,
                'exercise_num': exercise_num,
                'title': line.strip(),
                'content': '',
                'type': 'exercise',
            }

        # Accumulate content for current exercise
        elif current_exercise is not None:
            # Stop if we hit next exercise, section header, or chapter
            if re.match(r'^\d+-\d+\.\s+|^## |^习题答案', line):
                # Save current exercise
                if current_exercise['content']:
                    exercises.append(current_exercise)
                current_exercise = None

                # Check if this line starts a new exercise
                if match := re.match(r'^(\d+)-(\d+)\.\s+', line):
                    chapter_num = match.group(1)
                    exercise_num = match.group(2)
                    current_exercise = {
                        'book': book_name,
                        'chapter': chapter_num,
                        'exercise_num': exercise_num,
                        'title': line.strip(),
                        'content': '',
                        'type': 'exercise',
                    }
            else:
                # Add line to current exercise content
                if current_exercise['content']:
                    current_exercise['content'] += '\n' + line
                else:
                    current_exercise['content'] = line

    # Don't forget the last exercise
    if current_exercise and current_exercise['content']:
        exercises.append(current_exercise)

    return exercises


def main():
    base_dir = Path('/home/usamimira/PHY-LLM/CC_Integrater/textbook/merged')

    books = {
        'em': 'em.md',
        'mec': 'mec.md',
        'opt': 'opt.md',
        'thrm': 'thrm.md',
    }

    all_exercises = []

    for book_name, filename in books.items():
        md_path = base_dir / filename
        print(f"Processing {book_name}...")

        exercises = extract_exercises(md_path, book_name)
        print(f"  Found {len(exercises)} exercises")

        all_exercises.extend(exercises)

    print(f"\nTotal exercises: {len(all_exercises)}")

    # Save to JSON
    output_path = base_dir / 'exercises.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_exercises, f, ensure_ascii=False, indent=2)

    print(f"Saved to {output_path}")

    # Show stats
    print("\nExercise statistics:")
    sizes = [len(e['content']) for e in all_exercises]
    print(f"  Min size: {min(sizes)} chars")
    print(f"  Max size: {max(sizes)} chars")
    print(f"  Avg size: {sum(sizes) / len(sizes):.0f} chars")

    # Show first 3 exercises
    print("\nFirst 3 exercises:")
    for i, exercise in enumerate(all_exercises[:3]):
        print(f"\n{i+1}. [{exercise['book']}] {exercise['title']}")
        print(f"   Chapter: {exercise['chapter']}, Exercise: {exercise['exercise_num']}")
        print(f"   Size: {len(exercise['content'])} chars")
        print(f"   Preview: {exercise['content'][:200]}...")


if __name__ == '__main__':
    main()
