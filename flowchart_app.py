"""
Gradio app for case-based prescription flowchart support.

Run:
    python flowchart_app.py

Then open:
    http://127.0.0.1:7861
"""

from __future__ import annotations

import os
import traceback

import gradio as gr

from flowchart_engine import FlowchartEngine, INTAKE_TEMPLATE


engine = FlowchartEngine()


CSS = """
:root{
  --paper:#fbf4e4;
  --paper-2:#fffaf0;
  --ink:#1d2a23;
  --muted:#66766c;
  --green:#285c47;
  --green-2:#749b6b;
  --red:#9d3b31;
  --gold:#c69b46;
  --line:#e3d6bd;
}
body,.gradio-container{
  background:
    radial-gradient(circle at 12% 10%, rgba(198,155,70,.18), transparent 28%),
    radial-gradient(circle at 88% 0%, rgba(40,92,71,.16), transparent 24%),
    linear-gradient(135deg,var(--paper),#f6ecd8 48%,#f3eadc);
  color:var(--ink)!important;
  font-family:'Malgun Gothic','Apple SD Gothic Neo','Segoe UI',sans-serif!important;
}
.wrap{
  border:1px solid rgba(40,92,71,.22);
  background:rgba(255,250,240,.78);
  box-shadow:0 18px 45px rgba(29,42,35,.12);
  border-radius:22px;
  padding:24px 28px;
  margin-bottom:18px;
}
.hero-title{
  font-family:'Batang','Gowun Batang','Noto Serif KR',serif;
  font-size:32px;
  line-height:1.2;
  letter-spacing:-.03em;
  color:var(--green);
  margin:0 0 8px;
}
.hero-sub{
  color:var(--muted);
  font-size:14px;
  line-height:1.7;
  margin:0;
}
.notice{
  background:linear-gradient(90deg,rgba(157,59,49,.10),rgba(198,155,70,.12));
  border-left:4px solid var(--red);
  border-radius:12px;
  padding:12px 14px;
  color:#5f332d;
  font-size:13px;
  line-height:1.6;
}
textarea,input[type="text"]{
  background:rgba(255,255,255,.86)!important;
  border:1px solid var(--line)!important;
  border-radius:14px!important;
  color:var(--ink)!important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.8)!important;
}
textarea:focus,input[type="text"]:focus{
  border-color:var(--green-2)!important;
  box-shadow:0 0 0 3px rgba(116,155,107,.16)!important;
}
button.primary{
  background:linear-gradient(135deg,var(--green),#173d30)!important;
  color:#fff!important;
  border:0!important;
  border-radius:999px!important;
  padding:10px 22px!important;
  font-weight:700!important;
  box-shadow:0 10px 24px rgba(40,92,71,.28)!important;
}
button.secondary{
  background:rgba(255,255,255,.75)!important;
  color:var(--green)!important;
  border:1px solid rgba(40,92,71,.32)!important;
  border-radius:999px!important;
}
.prose,.gr-markdown,.markdown-body{
  background:rgba(255,250,240,.88)!important;
  border:1px solid var(--line)!important;
  border-radius:18px!important;
  padding:20px 22px!important;
  line-height:1.78!important;
}
.gr-markdown h2,.gr-markdown h3{
  font-family:'Batang','Gowun Batang','Noto Serif KR',serif!important;
  color:var(--green)!important;
}
.gr-markdown code{
  background:#efe2c8!important;
  color:#6a3a2d!important;
  border-radius:6px!important;
  padding:1px 5px!important;
}
.gr-markdown table{
  font-size:13px!important;
}
footer{display:none!important;}
"""


HEADER = """
<div class="wrap">
  <h1 class="hero-title">치험례 기반 처방 플로우차트</h1>
  <p class="hero-sub">
    새 환자의 문진표를 입력하면 <b>이종대</b>와 <b>이윤호(98) since2002</b> 치험례에서
    반복되는 증상 판단 흐름을 기준으로 처방 후보를 좁혀갑니다.
    추천 이유는 변증축, 유사 치험례, 투약/경과 단서, 처방·약재 문헌의 관점으로 보여줍니다.
  </p>
</div>
<div class="notice">
  임상 의사결정 보조용 화면입니다. 처방 확정은 문진, 맥진/복진 등 진찰, 병력과 검사 정보를 함께 놓고 판단해 주세요.
</div>
"""


def analyze_handler(intake_text: str, top_k: int):
    try:
        return engine.format_recommendations(intake_text, top_k=int(top_k))
    except Exception as exc:  # pragma: no cover - UI guard
        detail = traceback.format_exc(limit=2)
        message = f"분석 중 오류가 났습니다: `{exc}`\n\n```text\n{detail}\n```"
        return message, "", "", "", ""


def compare_handler(intake_text: str, alternative: str, top_k: int):
    try:
        if not alternative:
            return "비교할 처방을 선택하거나 입력해 주세요."
        return engine.compare(intake_text, alternative, top_k=int(top_k))
    except Exception as exc:  # pragma: no cover - UI guard
        detail = traceback.format_exc(limit=2)
        return f"비교 중 오류가 났습니다: `{exc}`\n\n```text\n{detail}\n```"


def build_demo() -> gr.Blocks:
    prescription_names = engine.prescription_names

    with gr.Blocks(title="치험례 처방 플로우차트") as demo:
        gr.HTML(HEADER)
        top_state = gr.State("")

        with gr.Row():
            with gr.Column(scale=5, min_width=460):
                intake = gr.Textbox(
                    label="문진표",
                    value=INTAKE_TEMPLATE,
                    lines=34,
                    max_lines=48,
                )
            with gr.Column(scale=2, min_width=280):
                top_k = gr.Slider(3, 12, value=8, step=1, label="후보 처방 수")
                analyze_btn = gr.Button("분석하기", variant="primary")
                gr.Markdown(
                    "문진표를 채운 뒤 분석하면, 두 작성자의 치험례식 판단축과 다음 감별 질문이 정리됩니다."
                )
                alt = gr.Dropdown(
                    choices=prescription_names,
                    label="다른 처방과 비교",
                    allow_custom_value=True,
                    interactive=True,
                )
                compare_btn = gr.Button("선택 처방과 비교", variant="secondary")

        with gr.Tabs():
            with gr.Tab("추천 요약"):
                summary_out = gr.Markdown()
            with gr.Tab("세부 질문"):
                questions_out = gr.Markdown()
            with gr.Tab("유사 치험례"):
                evidence_out = gr.Markdown()
            with gr.Tab("처방 상세"):
                detail_out = gr.Markdown()
            with gr.Tab("처방 비교"):
                compare_out = gr.Markdown()

        analyze_btn.click(
            analyze_handler,
            inputs=[intake, top_k],
            outputs=[summary_out, questions_out, evidence_out, detail_out, top_state],
        )
        compare_btn.click(
            compare_handler,
            inputs=[intake, alt, top_k],
            outputs=[compare_out],
        )

    return demo


demo = build_demo()


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "7861"))
    demo.launch(server_name=host, server_port=port, inbrowser=False, css=CSS)
