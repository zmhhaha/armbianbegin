import hashlib
import os
from typing import Any
import httpx
from elasticsearch import Elasticsearch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ES_URL = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch.data.svc.cluster.local:9200")
ES_USER = os.getenv("ELASTICSEARCH_USERNAME", "elastic")
ES_PASSWORD = os.getenv("ELASTICSEARCH_PASSWORD", "")
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://embedding-service.data.svc.cluster.local:8080")
LLM_URL = os.getenv("LLM_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
ALLOWED = {x.strip() for x in os.getenv("ALLOWED_AGENTS", "zhougongjiemeng,zhongkuifumo,daofaziran,fofawubian,zhenzhuzhida,yimaneili,xiaotanrenjian,bingbichunqiu").split(",") if x.strip()}
es = Elasticsearch(ES_URL, basic_auth=(ES_USER, ES_PASSWORD) if ES_PASSWORD else None)
app = FastAPI(title="rag-service", version="1.0.0")

def collection(agent: str) -> str:
    if agent not in ALLOWED:
        raise HTTPException(404, "agent collection not found")
    return f"agent-{agent}"

def index_name(name: str) -> str:
    return f"rag-{name}-v1"

class IngestRequest(BaseModel):
    agent: str
    source_id: str = Field(min_length=1, max_length=512)
    checksum: str | None = None
    content: str = Field(min_length=1, max_length=2_000_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

class QueryRequest(BaseModel):
    agent: str
    question: str = Field(min_length=1, max_length=20000)
    top_k: int = Field(default=5, ge=1, le=20)

@app.get("/health/live")
def live(): return {"status": "ok"}

@app.get("/health/ready")
def ready():
    try:
        if not es.ping(): raise RuntimeError("elasticsearch unavailable")
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(503, str(exc)) from exc

@app.post("/v1/ingest")
async def ingest(req: IngestRequest):
    col = collection(req.agent)
    checksum = req.checksum or "sha256:" + hashlib.sha256(req.content.encode()).hexdigest()
    idx = index_name(col)
    doc_id = req.source_id
    existing = es.get(index=idx, id=doc_id, ignore=[404])
    if existing and existing.get("found") and existing["_source"].get("checksum") == checksum:
        return {"document_id": doc_id, "collection": col, "status": "ready", "chunk_count": existing["_source"].get("chunk_count", 1), "index_version": "v1"}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(f"{EMBEDDING_URL}/v1/embeddings", json={"input": [req.content], "input_type": "passage"})
        response.raise_for_status()
        vector = response.json()["data"][0]["embedding"]
    source = {**req.metadata, "agent": req.agent, "collection": col, "source_id": doc_id, "checksum": checksum, "content": req.content, "content_vector": vector, "chunk_seq": 0, "chunk_count": 1, "index_version": "v1"}
    es.index(index=idx, id=doc_id, document=source, refresh="wait_for")
    return {"document_id": doc_id, "collection": col, "status": "ready", "chunk_count": 1, "index_version": "v1"}

@app.post("/v1/query")
async def query(req: QueryRequest):
    col = collection(req.agent)
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(f"{EMBEDDING_URL}/v1/embeddings", json={"input": [req.question], "input_type": "query"})
        response.raise_for_status()
        vector = response.json()["data"][0]["embedding"]
    result = es.search(index=index_name(col), knn={"field": "content_vector", "query_vector": vector, "k": req.top_k, "num_candidates": max(20, req.top_k * 4), "filter": {"term": {"collection": col}}}, query={"bool": {"filter": [{"term": {"collection": col}}], "should": [{"match": {"content": {"query": req.question}}}]}}, size=req.top_k)
    sources = [{"content": hit["_source"]["content"], "score": hit["_score"], "source_id": hit["_source"]["source_id"], "work": hit["_source"].get("work"), "topic": hit["_source"].get("topic")} for hit in result["hits"]["hits"]]
    context = "\n\n".join(x["content"] for x in sources)
    answer = context or "索引知识不足，无法根据当前知识库回答。"
    if context and LLM_URL:
        async with httpx.AsyncClient(timeout=120) as client:
            llm = await client.post(LLM_URL, json={"model": LLM_MODEL, "messages": [{"role": "system", "content": "仅依据给定参考资料回答，不足时明确说明。"}, {"role": "user", "content": f"参考资料：\n{context}\n\n问题：{req.question}"}]})
            llm.raise_for_status()
            answer = llm.json()["choices"][0]["message"]["content"]
    return {"answer": answer, "collection": col, "sources": sources, "index_version": "v1"}
