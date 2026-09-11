import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

import auth  # noqa: E402


class IdentityTests(unittest.TestCase):
    def test_token_maps_to_own_collection(self):
        with patch.dict(os.environ, {"RAG_TOKEN_DAOFAZIRAN": "tok-a"}, clear=False):
            identity = auth.resolve("tok-a")
        self.assertIsNotNone(identity)
        self.assertEqual(identity.caller, "daofaziran")
        self.assertEqual(identity.role, "writer")
        # 默认只能读写自己的 collection
        self.assertTrue(identity.allowed("read", "agent-daofaziran"))
        self.assertTrue(identity.allowed("write", "agent-daofaziran"))
        self.assertFalse(identity.allowed("read", "agent-fofawubian"))
        self.assertFalse(identity.allowed("write", "agent-fofawubian"))

    def test_unknown_or_missing_token_is_rejected(self):
        self.assertIsNone(auth.resolve("not-a-token"))
        self.assertIsNone(auth.resolve(""))

    def test_operator_wildcard_comes_from_server_config(self):
        env = {
            "RAG_TOKEN_RAG_OPERATOR": "tok-op",
            "CALLER_PERMISSIONS": '{"rag-operator": {"read": ["*"], "write": ["*"]}}',
        }
        with patch.dict(os.environ, env, clear=False):
            identity = auth.resolve("tok-op")
        self.assertEqual(identity.role, "operator")
        self.assertTrue(identity.allowed("read", "agent-anything"))
        self.assertTrue(identity.allowed("write", "agent-anything"))

    def test_permission_override_can_narrow_to_read_only(self):
        env = {
            "RAG_TOKEN_XIAOTANRENJIAN": "tok-x",
            "CALLER_PERMISSIONS": '{"xiaotanrenjian": {"read": ["agent-xiaotanrenjian"], "write": []}}',
        }
        with patch.dict(os.environ, env, clear=False):
            identity = auth.resolve("tok-x")
        self.assertEqual(identity.role, "reader")
        self.assertTrue(identity.allowed("read", "agent-xiaotanrenjian"))
        self.assertFalse(identity.allowed("write", "agent-xiaotanrenjian"))

    def test_caller_name_derived_from_env_key_only(self):
        # 令牌相同但来自不同环境变量时，命中的是环境变量名对应的调用者
        env = {"RAG_TOKEN_BINGBICHUNQIU": "shared"}
        with patch.dict(os.environ, env, clear=False):
            identity = auth.resolve("shared")
        self.assertEqual(identity.caller, "bingbichunqiu")


if __name__ == "__main__":
    unittest.main()
