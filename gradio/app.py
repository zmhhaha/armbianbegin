"""
Gradio 应用模板 — 替换为你自己的逻辑。
运行: python app.py
访问: http://localhost:7860
"""
import os
import gradio as gr


def my_function(user_input: str) -> str:
    """在这里写你的业务逻辑"""
    return f"你输入了: {user_input}"


# ---- 界面 ----
with gr.Blocks(title="My App") as demo:
    gr.Markdown("# 🤖 My Gradio App")
    inp = gr.Textbox(label="输入")
    out = gr.Textbox(label="输出")
    btn = gr.Button("运行")
    btn.click(fn=my_function, inputs=inp, outputs=out)


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
    )
