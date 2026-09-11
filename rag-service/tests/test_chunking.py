import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from chunking import split_chunks


class ChunkingTests(unittest.TestCase):
    def test_paragraphs_are_split_with_bound(self):
        chunks = split_chunks("第一段。" * 300 + "\n\n第二段。" * 300)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1200 for chunk in chunks))

    def test_short_text_stays_one_chunk(self):
        self.assertEqual(split_chunks("简短知识"), ["简短知识"])

    def test_long_paragraph_has_overlap_and_multiple_chunks(self):
        chunks = split_chunks("左传。" * 500)
        self.assertGreater(len(chunks), 1)
        self.assertLessEqual(len(chunks[0]), 1200)
        self.assertTrue(set(chunks[0][-120:]) & set(chunks[1]))
