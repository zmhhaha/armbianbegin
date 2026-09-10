import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from fastapi.testclient import TestClient
from tokenizers import Tokenizer, models, pre_tokenizers


class FakeSession:
    def get_inputs(self):
        return [type("Input", (), {"name": name})() for name in ("input_ids", "attention_mask")]

    def run(self, _, feeds):
        return [np.ones((*feeds["input_ids"].shape, 512), dtype=np.float32)]


class EmbeddingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tokenizer = Tokenizer(models.WordLevel({"[UNK]": 0, "[PAD]": 1}, unk_token="[UNK]"))
        tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
        spec = importlib.util.spec_from_file_location("embedding_app", Path(__file__).parents[1] / "app.py")
        cls.module = importlib.util.module_from_spec(spec)
        with patch("tokenizers.Tokenizer.from_file", return_value=tokenizer), patch("onnxruntime.InferenceSession", return_value=FakeSession()):
            spec.loader.exec_module(cls.module)
        cls.client = TestClient(cls.module.app)

    def test_normalized_batch(self):
        response = self.client.post("/v1/embeddings", json={"input": ["hello", "hello world"]})
        self.assertEqual(response.status_code, 200)
        vectors = [item["embedding"] for item in response.json()["data"]]
        self.assertEqual(np.asarray(vectors).shape, (2, 512))
        np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-6)

    def test_invalid_requests(self):
        for body in ({"input": [" "]}, {"input": []}, {"input": ["x"] * 17}, {"input": ["x"], "model": "other"}):
            self.assertEqual(self.client.post("/v1/embeddings", json=body).status_code, 422)

    def test_busy(self):
        with self.module.inference_lock:
            response = self.client.post("/v1/embeddings", json={"input": ["hello"]})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "1")

    def test_query_instruction(self):
        with patch.object(self.module, "tokenizer", wraps=self.module.tokenizer) as tokenizer:
            self.client.post("/v1/embeddings", json={"input": ["hello"], "input_type": "query"})
            self.assertTrue(tokenizer.encode_batch.call_args.args[0][0].endswith("hello"))
            self.assertNotEqual(tokenizer.encode_batch.call_args.args[0][0], "hello")
