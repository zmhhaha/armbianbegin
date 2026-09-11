import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from chunking import split_knowledge  # noqa: E402

SAMPLE = """# 某学养底稿

开头说明段落，不属于任何小节。

## 一、史职与史源

- **记言与记事**（《汉书·艺文志》）——古有左史记言、右史记事之说。

## 二、辨料规矩

- 孤证不立：要紧事最好有两条独立材料互证。

## 三、使用守则（呼应 skill）

- 你在回答里不必句句报篇名。
"""


class SplitKnowledgeTests(unittest.TestCase):
    def test_splits_sections_and_skips_behaviour_ones(self):
        entries = split_knowledge(SAMPLE)
        topics = [topic for topic, _, _ in entries]
        self.assertEqual(topics, ["史职与史源", "辨料规矩"])

    def test_extracts_work_from_heading_or_body(self):
        entries = split_knowledge(SAMPLE)
        self.assertEqual(entries[0][1], "汉书·艺文志")
        self.assertIsNone(entries[1][1])

    def test_keeps_heading_in_content(self):
        entries = split_knowledge(SAMPLE)
        self.assertTrue(entries[0][2].startswith("# 一、史职与史源"))

    def test_empty_markdown_yields_nothing(self):
        self.assertEqual(split_knowledge(""), [])


if __name__ == "__main__":
    unittest.main()
