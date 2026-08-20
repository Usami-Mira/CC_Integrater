#!/usr/bin/env python3
"""Lightweight tests for the RAG query schema and output format."""

import importlib.util
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


QUERY_SCRIPT = Path(__file__).parent / "textbook" / "rag_build" / "query_rag.py"


def load_query_module():
    spec = importlib.util.spec_from_file_location("query_rag_for_test", QUERY_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestRagQuerySchema(unittest.TestCase):
    def test_default_model_can_download_from_hugging_face(self):
        with patch.dict(os.environ, {}, clear=True):
            module = load_query_module()
        self.assertEqual(module.MODEL_SOURCE, "BAAI/bge-m3")

    def test_results_use_only_collection_schema_fields(self):
        module = load_query_module()
        obj = SimpleNamespace(properties={
            "book": "mec",
            "chapter": "1",
            "section": "1.1",
            "title": "牛顿第二定律",
            "content": "物体的加速度与合外力成正比。",
        })

        result = module.results_as_dicts([obj])
        self.assertEqual(result[0]["title"], "牛顿第二定律")
        self.assertEqual(
            set(result[0]),
            {"book", "chapter", "section", "title", "content"},
        )
        self.assertNotIn("titleEn", module.format_results("牛顿", [obj]))

    def test_query_script_does_not_request_removed_english_fields(self):
        source = QUERY_SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("titleEn", source)
        self.assertNotIn("contentEn", source)


if __name__ == "__main__":
    unittest.main()
