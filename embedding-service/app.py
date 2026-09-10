import os
from threading import Lock
from typing import Annotated, Literal
from pathlib import Path
import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from tokenizers import Tokenizer

MODEL_DIR = Path(os.getenv("MODEL_DIR", "/models/fast-bge-small-zh-v1.5"))
tokenizer = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
tokenizer.enable_truncation(max_length=int(os.getenv("MAX_LENGTH", "512")))
tokenizer.enable_padding()
options = ort.SessionOptions()
options.intra_op_num_threads = int(os.getenv("ORT_INTRA_OP_THREADS", "4"))
session = ort.InferenceSession(str(MODEL_DIR / "model_optimized.onnx"), sess_options=options, providers=["CPUExecutionProvider"])
app = FastAPI(title="embedding-service")
inference_lock = Lock()

class EmbeddingRequest(BaseModel):
    input: list[Annotated[str, Field(min_length=1, max_length=8192)]] = Field(min_length=1, max_length=16)
    input_type: Literal["passage", "query"] = "passage"
    model: Literal["bge-small-zh-v1.5"] = "bge-small-zh-v1.5"

@app.get("/health/live")
def live():
    return {"status": "ok"}

@app.get("/health/ready")
def ready():
    return {"status": "ready", "model": "bge-small-zh-v1.5", "dims": 512}

@app.post("/v1/embeddings")
def embeddings(request: EmbeddingRequest):
    if any(not item.strip() for item in request.input):
        raise HTTPException(422, "input must contain non-empty text")
    if not inference_lock.acquire(blocking=False):
        raise HTTPException(429, "Embedding worker is busy", headers={"Retry-After": "1"})
    try:
        return encode(request)
    finally:
        inference_lock.release()

def encode(request):
    texts = request.input
    if request.input_type == "query":
        texts = ["为这个句子生成表示以用于检索相关文章：" + text for text in texts]
    batch = tokenizer.encode_batch(texts)
    feeds = {name: np.asarray([getattr(item, attr) for item in batch], dtype=np.int64) for name, attr in (("input_ids", "ids"), ("attention_mask", "attention_mask"), ("token_type_ids", "type_ids"))}
    feeds = {item.name: feeds[item.name] for item in session.get_inputs()}
    vectors = session.run(None, feeds)[0][:, 0, :].copy()
    if vectors.shape != (len(texts), 512) or not np.isfinite(vectors).all():
        raise HTTPException(503, "Invalid model output")
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
    return {"object": "list", "model": "bge-small-zh-v1.5", "data": [{"object": "embedding", "index": i, "embedding": v.tolist()} for i, v in enumerate(vectors)]}
