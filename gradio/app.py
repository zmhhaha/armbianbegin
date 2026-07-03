"""
Gradio Web UI — 为 CrewAI Agent 提供聊天式网页界面。
启动: python app.py
访问: http://localhost:7860
"""
import os
import sys
import time
from pathlib import Path

# 🔧 确保能 import 到 crewai/ 目录下的模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "crewai"))
# 加载 .env（如果有）
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "crewai", ".env"))

import gradio as gr
from crew import create_research_crew

# ---- 主题 ----
THEME = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="gray",
    font=gr.themes.GoogleFont("Inter"),
)

# ---- 核心函数：调用 CrewAI Agent ----
def run_research(topic: str, progress=gr.Progress()) -> str:
    """接收调研主题，运行多 Agent 协作，返回 Markdown 报告。"""
    if not topic.strip():
        return "⚠️ 请输入调研主题。"
    try:
        progress(0.2, desc="初始化 Agent...")
        crew = create_research_crew()
        progress(0.5, desc="正在调研中（研究员→分析师→撰写）...")
        result = crew.kickoff(inputs={"topic": topic})
        progress(1.0, desc="完成！")
        return str(result)
    except Exception as e:
        return f"❌ 出错了: {e}"

# ---- 构建界面 ----
with gr.Blocks(title="Panghu Agent", theme=THEME, css="footer {display: none !important}") as demo:
    gr.Markdown(
        """# 🤖 Panghu Agent
        **多 Agent 协作研究助手** — 输入任意主题，研究员搜集信息、分析师提炼洞察、撰写者输出报告。
        """
    )
    with gr.Row():
        with gr.Column(scale=2):
            topic = gr.Textbox(
                label="调研主题",
                placeholder="例如：2026年AI Agent框架发展趋势",
                lines=3,
            )
            btn = gr.Button("🚀 开始调研", variant="primary", size="lg")
        with gr.Column(scale=3):
            output = gr.Markdown(label="调研报告", elem_id="report")

    btn.click(fn=run_research, inputs=[topic], outputs=output)

    gr.Markdown("---\n💡 提示：调研过程约需 1-3 分钟，请耐心等待。")

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=2).launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
    )
