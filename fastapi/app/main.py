"""
CrewAI Agent — FastAPI 接口
启动: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import sys, os

# 让 crewai 模块可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crewai"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="CrewAI Agent API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ResearchRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500, description="调研主题")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/research")
def research(req: ResearchRequest):
    """执行一次多 Agent 协作调研"""
    try:
        from crew import create_research_crew
        crew = create_research_crew()
        result = crew.kickoff(inputs={"topic": req.topic})
        return {"success": True, "topic": req.topic, "report": str(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
