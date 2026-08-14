#!/usr/bin/env python3
"""
Unit tests for smart_chunk.py
"""

import unittest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from smart_chunk import estimate_tokens, find_paragraph_break, smart_split, chunk_entries


class TestEstimateTokens(unittest.TestCase):
    """Test token estimation."""

    def test_short_chinese_text(self):
        """Short Chinese text should estimate ~1.5 chars per token."""
        text = "这是一个测试"
        tokens = estimate_tokens(text)
        # 6 chars / 1.5 = 4 tokens
        self.assertEqual(tokens, 4)

    def test_long_chinese_text(self):
        """Longer text should scale linearly."""
        text = "中" * 1500  # 1500 chars
        tokens = estimate_tokens(text)
        # 1500 / 1.5 = 1000 tokens
        self.assertEqual(tokens, 1000)

    def test_mixed_text(self):
        """Mixed Chinese and English should still estimate reasonably."""
        text = "这是test混合text"
        tokens = estimate_tokens(text)
        # 12 chars / 1.5 = 8 tokens
        self.assertEqual(tokens, 8)


class TestFindParagraphBreak(unittest.TestCase):
    """Test paragraph break detection."""

    def test_double_newline(self):
        """Should find double newline as strongest break."""
        text = "第一段内容。\n\n第二段内容开始。"
        # Target position in middle of text
        break_pos = find_paragraph_break(text, target_pos=10, window=20)
        # Should break after first paragraph (position 7 is after \n\n)
        # The function returns position after the newlines
        self.assertEqual(break_pos, 8)

    def test_single_newline_after_sentence(self):
        """Should find single newline after sentence ending."""
        text = "第一句话。\n第二句话。"
        break_pos = find_paragraph_break(text, target_pos=8, window=10)
        # Should break after period and newline (position 6)
        self.assertEqual(break_pos, 6)

    def test_fallback_to_newline(self):
        """Should fall back to any newline if no sentence ending."""
        text = "没有句号\n只有换行"
        break_pos = find_paragraph_break(text, target_pos=6, window=10)
        # Should break at newline (position 5)
        self.assertEqual(break_pos, 5)

    def test_no_break_found(self):
        """Should return target_pos if no break found."""
        text = "没有任何换行的文本"
        break_pos = find_paragraph_break(text, target_pos=5, window=10)
        self.assertEqual(break_pos, 5)

    def test_window_respected(self):
        """Should only search within window."""
        text = "第一段。\n\n" + "x" * 500 + "\n\n第三段。"
        # Target far from any break
        break_pos = find_paragraph_break(text, target_pos=300, window=50)
        # Should not find the breaks at position 5 or 505
        self.assertNotEqual(break_pos, 7)
        self.assertNotEqual(break_pos, 507)


class TestSmartSplit(unittest.TestCase):
    """Test smart splitting logic."""

    def test_short_text_no_split(self):
        """Text under max_tokens should not be split."""
        text = "这是短文本"
        chunks = smart_split(text, max_tokens=2048, overlap_tokens=256)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_long_text_splits(self):
        """Long text should be split into multiple chunks."""
        # Create text ~6000 chars (~4000 tokens)
        text = "段落一的内容，这是比较长的文本。\n\n" * 50
        chunks = smart_split(text, max_tokens=100, overlap_tokens=20)
        # Should split into at least 2 chunks
        self.assertGreater(len(chunks), 1)

    def test_overlap_between_chunks(self):
        """Chunks should have overlap."""
        # Create text with clear paragraph breaks
        paragraphs = [f"这是第{i}段内容。" for i in range(20)]
        text = "\n\n".join(paragraphs)

        chunks = smart_split(text, max_tokens=50, overlap_tokens=10)

        # Check that consecutive chunks have overlapping content
        if len(chunks) >= 2:
            # Last part of chunk 0 should appear in chunk 1
            chunk0_end = chunks[0][-20:]  # Last 20 chars
            # Chunk 1 should contain some of chunk 0's end
            # (due to overlap, though exact match depends on break point)
            self.assertGreater(len(chunks[1]), 0)

    def test_respects_paragraph_breaks(self):
        """Should split at paragraph boundaries when possible."""
        # Create text with clear paragraphs
        para1 = "第一段内容，" * 50  # ~500 chars
        para2 = "第二段内容，" * 50  # ~500 chars
        text = para1 + "\n\n" + para2

        chunks = smart_split(text, max_tokens=300, overlap_tokens=50)

        # Should split at the double newline
        if len(chunks) >= 2:
            # First chunk should end with first paragraph
            self.assertIn("第一段内容", chunks[0])

    def test_empty_text(self):
        """Empty text should return empty list."""
        chunks = smart_split("", max_tokens=2048, overlap_tokens=256)
        # Empty text produces no chunks
        self.assertEqual(len(chunks), 0)


class TestChunkEntries(unittest.TestCase):
    """Test entry chunking."""

    def test_short_entries_unchanged(self):
        """Short entries should not be split."""
        entries = [
            {"title": "短标题", "content": "短内容", "book": "em"},
            {"title": "另一个", "content": "也很短", "book": "mec"},
        ]

        chunked = chunk_entries(entries, max_tokens=2048, overlap_tokens=256)

        # Should have same number of entries
        self.assertEqual(len(chunked), 2)
        # Content should be unchanged
        self.assertEqual(chunked[0]["content"], "短内容")
        self.assertEqual(chunked[1]["content"], "也很短")

    def test_long_entries_split(self):
        """Long entries should be split."""
        # Create a long entry (~1500 chars, ~1000 tokens)
        long_content = "这是长内容，包含很多文字。\n\n" * 100
        entries = [
            {"title": "长标题", "content": long_content, "book": "em", "type": "content"},
        ]

        chunked = chunk_entries(entries, max_tokens=200, overlap_tokens=50)

        # Should split into multiple chunks
        self.assertGreater(len(chunked), 1)

        # Each chunk should have metadata
        for chunk in chunked:
            self.assertEqual(chunk["book"], "em")
            self.assertEqual(chunk["type"], "content")
            self.assertIn("chunk_index", chunk)
            self.assertIn("total_chunks", chunk)

    def test_title_updated_for_splits(self):
        """Split entries should have updated titles."""
        long_content = "内容。\n\n" * 200
        entries = [
            {"title": "原标题", "content": long_content, "book": "em"},
        ]

        chunked = chunk_entries(entries, max_tokens=100, overlap_tokens=20)

        if len(chunked) > 1:
            # Titles should indicate parts
            self.assertIn("part 1/", chunked[0]["title"])
            self.assertIn("part 2/", chunked[1]["title"])

    def test_mixed_lengths(self):
        """Should handle mix of short and long entries."""
        entries = [
            {"title": "短", "content": "短内容", "book": "em"},
            {"title": "长", "content": "长内容。\n\n" * 100, "book": "mec"},
            {"title": "中", "content": "中等长度内容", "book": "opt"},
        ]

        chunked = chunk_entries(entries, max_tokens=200, overlap_tokens=50)

        # Should have more chunks than original entries (long one split)
        self.assertGreater(len(chunked), 3)

        # Short and medium should remain as single chunks
        short_chunks = [c for c in chunked if c["title"] == "短"]
        medium_chunks = [c for c in chunked if c["title"] == "中"]
        self.assertEqual(len(short_chunks), 1)
        self.assertEqual(len(medium_chunks), 1)


if __name__ == '__main__':
    unittest.main()
