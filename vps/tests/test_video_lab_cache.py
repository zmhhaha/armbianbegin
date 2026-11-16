"""Narrow browser-cache exception for measured developer preview assets."""
from pathlib import Path
import re
import unittest


class VideoLabCacheContracts(unittest.TestCase):
    def test_cache_exception_requires_exact_path_success_and_private_header(self):
        source = (Path(__file__).resolve().parents[1] / 'nginx/video-service.conf.template').read_text(encoding='utf8')
        pattern = re.search(r'"~(\^/dev/animations/assets/[^\n]+?)" "private, max-age=31536000, immutable";', source).group(1)
        key = '/dev/animations/assets/' + 'a' * 64 + '/NotoSansCJK-Regular.ttc|200|private, max-age=31536000, immutable'
        self.assertRegex(key, pattern)
        for invalid in (key.replace('|200|', '|302|'), key.replace('|200|', '|403|'),
                        key.replace('/assets/', '/api/'), key.replace('Regular.ttc', 'Regular.ttc/secret'),
                        key.replace('private,', 'public,'), key.replace('a' * 64, 'a' * 63)):
            self.assertIsNone(re.search(pattern, invalid))
        for directive in ('default "no-store";', 'proxy_cache off;', 'proxy_cache_bypass 1;',
                          'proxy_no_cache 1;', 'proxy_hide_header Cache-Control;',
                          'add_header Cache-Control $video_service_cache_control always;'):
            self.assertIn(directive, source)
        self.assertNotIn('proxy_ignore_headers', source)


if __name__ == '__main__':
    unittest.main()
