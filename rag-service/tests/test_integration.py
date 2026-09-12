"""rag-service 集成测试：隔离、幂等、替换、检索质量、状态查询、鉴权、删除。

需要连到**真实的** RAG（ES + embedding 都在），所以默认跳过；
用环境变量启用后在集群内运行：

    kubectl -n <agent-ns> exec -i deploy/api -c api -- \
      env RAG_URL=http://rag-service.data.svc.cluster.local:8080 \
          RAG_TOKEN="$(kubectl -n <agent-ns> get secret rag-token -o jsonpath='{.data.RAG_TOKEN}' | base64 -d)" \
      python - < rag-service/tests/test_integration.py

注意：会往该调用者自己的 collection **写一篇测试文档**，用例结束时会删除它。
"""
import json
import os
import unittest
import urllib.error
import urllib.request
import uuid

RAG_URL = os.getenv("RAG_URL", "").rstrip("/")
RAG_TOKEN = os.getenv("RAG_TOKEN", "")
OTHER_COLLECTION = os.getenv("RAG_OTHER_AGENT", "definitely-not-my-collection")
ENABLED = bool(RAG_URL and RAG_TOKEN)

DOC_ID = f"selftest-{uuid.uuid4().hex[:8]}"
ORIGINAL = "自检文档：祆教在唐代被称为火祆教，长安曾有祆祠。"
UPDATED = "自检文档（改版）：摩尼教在唐代传入中土，武宗灭佛时一并遭禁。"


def call(path, data=None, token=RAG_TOKEN, method="POST", timeout=120):
    request = urllib.request.Request(
        RAG_URL + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        try:
            return error.code, json.loads(body)
        except ValueError:
            return error.code, {"detail": body[:200]}


@unittest.skipUnless(ENABLED, "需要 RAG_URL 与 RAG_TOKEN 才能跑集成测试")
class RagIntegrationTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        call(f"/v1/ingest/{DOC_ID}", method="DELETE")

    def test_01_requires_credential(self):
        self.assertEqual(call("/v1/query", {"question": "x"}, token="")[0], 401)
        self.assertEqual(call("/v1/query", {"question": "x"}, token="not-a-token")[0], 401)

    def test_02_isolation_blocks_other_collection(self):
        status, _ = call("/v1/query", {"question": "自检", "agent": OTHER_COLLECTION, "mode": "context"})
        self.assertEqual(status, 404, "越权访问别的 collection 必须按不存在处理")

    def test_03_ingest_then_query(self):
        status, body = call("/v1/ingest", {"source_id": DOC_ID, "content": ORIGINAL})
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ready")
        self.assertGreaterEqual(body["chunk_count"], 1)

        status, body = call("/v1/query", {"question": "唐代的火祆教", "mode": "context", "top_k": 5})
        self.assertEqual(status, 200)
        self.assertIsNone(body["answer"], "context 模式不应生成答案")
        self.assertIn("火祆教", body["context"])
        self.assertTrue(any(s["source_id"] == DOC_ID for s in body["sources"]))

    def test_04_status_endpoint(self):
        status, body = call(f"/v1/ingest/{DOC_ID}", method="GET")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ready")
        self.assertGreaterEqual(body["chunk_count"], 1)

    def test_05_idempotent_reingest(self):
        first = call("/v1/ingest", {"source_id": DOC_ID, "content": ORIGINAL})[1]
        second = call("/v1/ingest", {"source_id": DOC_ID, "content": ORIGINAL})[1]
        self.assertEqual(first["chunk_count"], second["chunk_count"], "内容未变应幂等")
        _, body = call("/v1/query", {"question": "唐代的火祆教", "mode": "context", "top_k": 10})
        self.assertEqual(sum(1 for s in body["sources"] if s["source_id"] == DOC_ID), 1,
                         "同一文档不应出现重复 chunk")

    def test_06_replacement_swaps_content(self):
        call("/v1/ingest", {"source_id": DOC_ID, "content": UPDATED})
        _, body = call("/v1/query", {"question": "摩尼教 武宗灭佛", "mode": "context", "top_k": 10})
        self.assertIn("摩尼教", body["context"])
        _, body = call("/v1/query", {"question": "火祆教 祆祠", "mode": "context", "top_k": 10})
        self.assertNotIn("火祆教", body["context"], "旧内容必须被整体替换掉")

    def test_07_delete_removes_document(self):
        status, body = call(f"/v1/ingest/{DOC_ID}", method="DELETE")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(body["removed_chunks"], 1)
        status, _ = call(f"/v1/ingest/{DOC_ID}", method="GET")
        self.assertEqual(status, 404, "删除后不应再查到摄入记录")


if __name__ == "__main__":
    unittest.main(verbosity=2)
