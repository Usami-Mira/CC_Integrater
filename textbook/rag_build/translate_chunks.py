#!/usr/bin/env python3
"""
Translate Chinese physics textbook chunks to English using Qwen API.
Uses DashScope's OpenAI-compatible API.
"""

import json
import time
import os
import sys
import hashlib
from pathlib import Path
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# OpenAI SDK for DashScope
from openai import OpenAI

# Global lock for thread-safe printing
print_lock = Lock()

# Simple disk cache
class SimpleCache:
    def __init__(self, cache_dir):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    def get(self, key):
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            self.hits += 1
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)['value']
        self.misses += 1
        return None

    def set(self, key, value):
        path = self.cache_dir / f"{key}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'value': value}, f, ensure_ascii=False)

def make_cache_key(text, model):
    """Create cache key from text and model."""
    h = hashlib.sha256(f"{model}:{text}".encode()).hexdigest()[:16]
    return h

def translate_with_qwen(text: str, client: OpenAI, model: str, cache: SimpleCache) -> str:
    """
    Translate Chinese text to English using Qwen via DashScope.
    """
    # Check cache
    cache_key = make_cache_key(text, model)
    cached = cache.get(cache_key)
    if cached:
        return cached

    system_prompt = """You are a professional physics textbook translator. Translate from Chinese to English.
Requirements:
1. Maintain technical terminology accuracy (e.g., 库仑=Coulomb, 电场=electric field, 磁场=magnetic field, 力学=mechanics, 光学=optics, 热学=thermodynamics, 电磁学=electromagnetism)
2. Keep mathematical formulas and symbols exactly as-is (LaTeX format like $...$, $$...$$, \\frac{}{}, etc.)
3. Preserve the structure and formatting (headings, lists, paragraphs)
4. Use formal academic English appropriate for physics textbooks
5. Output ONLY the translation, no explanations or notes"""

    user_prompt = f"Translate the following physics textbook content:\n\n{text}"

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=8192,
            extra_body={"enable_thinking": False},
            timeout=600
        )
        translation = response.choices[0].message.content.strip()

        # Cache the result
        cache.set(cache_key, translation)

        return translation
    except Exception as e:
        with print_lock:
            print(f"Translation error: {e}")
        raise


def translate_chunk(chunk: Dict, idx: int, total: int, client: OpenAI, model: str, cache: SimpleCache) -> Dict:
    """Translate a single chunk from Chinese to English."""
    translated = chunk.copy()

    # Translate title
    title_en = translate_with_qwen(chunk['title'], client, model, cache)
    translated['title_en'] = title_en

    # Translate content
    content_en = translate_with_qwen(chunk['content'], client, model, cache)
    translated['content_en'] = content_en

    # Keep original Chinese for reference
    translated['title_zh'] = chunk['title']
    translated['content_zh'] = chunk['content']

    with print_lock:
        print(f"[{idx+1}/{total}] Translated: {chunk['title'][:40]}...")

    return translated


def main():
    # Load chunks
    base_dir = Path('/home/usamimira/PHY-LLM/CC_Integrater/textbook/merged')
    chunks_path = base_dir / 'chunks.json'
    print(f"Loading chunks from {chunks_path}...")

    with open(chunks_path, 'r', encoding='utf-8') as f:
        chunks = json.load(f)

    print(f"Loaded {len(chunks)} chunks")

    # Initialize OpenAI client for DashScope
    api_key = os.environ.get('ANTHROPIC_AUTH_TOKEN', '')
    if not api_key:
        print("ERROR: ANTHROPIC_AUTH_TOKEN not set. Please set the API key.")
        sys.exit(1)

    print(f"Initializing DashScope client...")
    client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    model = "qwen3.6-flash"  # Fast model for translation
    print(f"Model: {model}")

    # Initialize cache
    cache_dir = base_dir / 'translation_cache'
    cache = SimpleCache(cache_dir)
    print(f"Cache directory: {cache_dir}")

    # Translate chunks with parallel processing
    max_workers = 20  # High concurrency for speed
    print(f"\nTranslating {len(chunks)} chunks with {max_workers} workers...")

    translated_chunks = []
    failed_indices = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all translation tasks
        future_to_idx = {
            executor.submit(translate_chunk, chunk, i, len(chunks), client, model, cache): i
            for i, chunk in enumerate(chunks)
        }

        # Process completed tasks
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                translated = future.result()
                translated_chunks.append((idx, translated))
            except Exception as e:
                with print_lock:
                    print(f"[{idx+1}/{len(chunks)}] FAILED: {chunks[idx]['title'][:40]}... - {e}")
                # Keep original if translation fails
                chunk = chunks[idx]
                chunk['title_en'] = chunk['title']
                chunk['content_en'] = chunk['content']
                chunk['title_zh'] = chunk['title']
                chunk['content_zh'] = chunk['content']
                translated_chunks.append((idx, chunk))
                failed_indices.append(idx)

    # Sort by original index to maintain order
    translated_chunks.sort(key=lambda x: x[0])
    translated_chunks = [chunk for idx, chunk in translated_chunks]

    # Save translated chunks
    output_path = base_dir / 'chunks_translated.json'
    print(f"\nSaving translated chunks to {output_path}...")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(translated_chunks, f, ensure_ascii=False, indent=2)

    print(f"Done! Translated {len(translated_chunks)} chunks")
    if failed_indices:
        print(f"Failed: {len(failed_indices)} chunks (kept original Chinese)")
        print(f"Failed indices: {failed_indices[:10]}{'...' if len(failed_indices) > 10 else ''}")

    # Print cache stats
    print(f"\nCache Stats:")
    print(f"  Hits: {cache.hits}")
    print(f"  Misses: {cache.misses}")

    # Show sample
    print("\n=== Sample Translation ===")
    sample = translated_chunks[0]
    print(f"Title (ZH): {sample['title_zh']}")
    print(f"Title (EN): {sample['title_en']}")
    print(f"Content (ZH): {sample['content_zh'][:100]}...")
    print(f"Content (EN): {sample['content_en'][:100]}...")


if __name__ == '__main__':
    main()
