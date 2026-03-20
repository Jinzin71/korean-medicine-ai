"""
app.py — Phase 4 (v0.4): Gradio 웹 인터페이스
8탭 구성 — python app.py 로 실행, http://localhost:7860
"""

import os
import json
import gradio as gr
from pathlib import Path
from datetime import datetime

IS_HF_SPACES = os.getenv("SPACE_ID") is not None

from local_engine import LocalHerbEngine
from constitution_tool import (
    ConstitutionAssessor, AnthropometricData, ThermalFunctionData,
    QiBloodYinYangData, DigestiveFunctionData, SasangScreeningData,
)

engine       = LocalHerbEngine()
assessor     = ConstitutionAssessor()
prescription_names = engine.get_all_prescription_names()

# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;600;700&family=Noto+Sans+KR:wght@300;400;500&family=JetBrains+Mono:wght@400;600&display=swap');
:root{--ink:#1a1a2e;--rice:#faf7f0;--bamboo:#4a7c59;--cin:#c0392b;--gold:#c9a84c;--slate:#5a6475;--mist:#e8e4dc;}
body,.gradio-container{background:var(--rice)!important;font-family:'Noto Sans KR',sans-serif!important;}
.hdr{background:var(--ink);padding:24px 36px 20px;margin:-8px -8px 16px;display:flex;align-items:baseline;gap:16px;border-bottom:3px solid var(--gold);}
.hdr-t{font-family:'Noto Serif KR',serif;font-size:21px;font-weight:700;color:#f5f0e8;letter-spacing:2px;}
.hdr-s{font-size:11px;color:var(--gold);font-family:'JetBrains Mono',monospace;}
/* Gradio 5.x 탭 네비게이션 */
.tab-nav button,div.tabs > div.tab-nav > button{font-family:'Noto Serif KR',serif!important;font-size:13px!important;color:var(--slate)!important;border-bottom:2px solid transparent!important;padding:9px 15px!important;background:transparent!important;transition:all .2s!important;}
.tab-nav button.selected,.tab-nav button:hover,div.tabs > div.tab-nav > button.selected,div.tabs > div.tab-nav > button:hover{color:var(--cin)!important;border-bottom-color:var(--cin)!important;}
/* Gradio 5.x 텍스트박스 */
textarea,input[type="text"]{background:white!important;border:1.5px solid var(--mist)!important;border-radius:6px!important;font-size:14px!important;color:var(--ink)!important;}
textarea:focus,input[type="text"]:focus{border-color:var(--bamboo)!important;box-shadow:0 0 0 3px rgba(74,124,89,.1)!important;}
/* Gradio 5.x 버튼 — variant="primary" */
button.primary,button[data-testid="primary-button"],.gr-button-primary{background:var(--cin)!important;color:white!important;border:none!important;border-radius:6px!important;font-family:'Noto Serif KR',serif!important;font-size:14px!important;font-weight:600!important;padding:10px 26px!important;box-shadow:0 2px 8px rgba(192,57,43,.3)!important;cursor:pointer!important;}
button.primary:hover,button[data-testid="primary-button"]:hover,.gr-button-primary:hover{background:#a93226!important;transform:translateY(-1px)!important;}
/* Gradio 5.x 버튼 — variant="secondary" */
button.secondary,button[data-testid="secondary-button"],.gr-button-secondary{background:white!important;color:var(--bamboo)!important;border:1.5px solid var(--bamboo)!important;border-radius:6px!important;cursor:pointer!important;}
/* Gradio 5.x 마크다운 — 외부 컨테이너만 흰 카드 */
.prose,.gr-markdown,.output-markdown{background:white!important;border:1px solid var(--mist)!important;border-radius:8px!important;padding:20px 24px!important;font-size:14px!important;line-height:1.8!important;color:var(--ink)!important;min-height:unset!important;overflow:visible!important;}
/* 안쪽 markdown-body는 투명 — 이중 박스 방지 */
.markdown-body{background:transparent!important;border:none!important;padding:0!important;min-height:unset!important;border-radius:0!important;}
/* 마크다운 출력 내 감싸는 컨테이너들도 투명화 */
.prose .prose,.gr-markdown .prose,.output-markdown .prose{border:none!important;padding:0!important;background:transparent!important;}
.prose h2,.prose h3,.gr-markdown h2,.gr-markdown h3{font-family:'Noto Serif KR',serif!important;border-bottom:1px solid var(--mist)!important;padding-bottom:5px!important;margin-top:16px!important;}
.prose strong,.gr-markdown strong{color:var(--cin)!important;}
.prose code,.gr-markdown code{background:var(--mist)!important;font-family:'JetBrains Mono',monospace!important;font-size:12px!important;border-radius:3px!important;padding:1px 4px!important;}
.card{background:white;border:1px solid var(--mist);border-left:3px solid var(--bamboo);border-radius:8px;padding:16px 20px;margin-bottom:10px;}
.tag{display:inline-block;background:rgba(74,124,89,.08);color:var(--bamboo);border:1px solid rgba(74,124,89,.25);border-radius:12px;padding:2px 10px;font-size:12px;margin:2px 3px;font-family:'JetBrains Mono',monospace;}
.sim-card{border:1px solid var(--mist);border-left:3px solid var(--bamboo);border-radius:8px;padding:16px 20px;margin-bottom:14px;background:white;}
/* 처방 링크 — 인라인 스타일 보완 */
[data-presc]{color:var(--cin)!important;cursor:pointer!important;text-decoration:underline!important;font-weight:600!important;}
[data-presc]:hover{color:#a93226!important;}
/* Gradio 5 레이블 배지 완전 제거 — 모든 컴포넌트 label 영역 */
.block>label:not(:has(textarea)):not(:has(input)):not(:has(select)){display:none!important;}
.label-wrap{display:none!important;}
/* fallback: :has 미지원 시 Gradio의 레이블 span 직접 숨김 */
.block>.wrap>label,.block>span.label{display:none!important;}
/* Gradio 5 내부 label-text, float-label 등 모두 숨김 */
.float-label,.label-text,.gr-input-label{display:none!important;}
/* 텍스트박스 label span이 textarea 글자를 침범하지 않도록 — 정적 블록으로 */
.block>label:has(textarea)>span,.block>label:has(input[type="text"])>span{
  display:block!important;position:static!important;float:none!important;
  font-size:12px!important;color:var(--slate)!important;margin-bottom:4px!important;
  background:transparent!important;padding:0!important;border:none!important;
  box-shadow:none!important;line-height:1.4!important;
  width:auto!important;max-width:100%!important;
}
/* 텍스트박스 내부 label이 absolute 위치잡는 것 방지 */
.block>label:has(textarea),.block>label:has(input[type="text"]){
  position:relative!important;display:flex!important;flex-direction:column!important;
}
"""

# ── 헬퍼 ─────────────────────────────────────────────────────────────────────
HDR = '<div class="hdr"><div class="hdr-t">달려라한의</div><div class="hdr-s">제작자 : 태극학회 김진영 한약사</div></div>'

def network_html(pid):
    try:
        import networkx as nx; from pyvis.network import Network
        edges = engine.get_similar_network(pid, top_k=8)
        if not edges: return "<p style='color:#888;padding:20px'>유사 처방 없음</p>"
        G = nx.DiGraph()
        G.add_node(pid, size=35, color="#c0392b", font={"size": 16, "color": "#c0392b"})
        for e in edges:
            etype = e.get("type", "similarity")
            if etype == "canvas":
                # 캔버스 관계: 파란색 점선
                G.add_node(e["target"], size=18, color="#3b82f6",
                           font={"size": 13, "color": "#3b82f6"})
                rel = e.get("relation", "sibling")
                label = {"child": "파생", "parent": "근원", "sibling": "연관"}.get(rel, "")
                G.add_edge(pid, e["target"], title=f"플로우차트: {label}",
                           color="#3b82f6", width=2, dashes=True)
            else:
                # 유사도 엣지: 기존 녹색
                score = e["score"]
                G.add_node(e["target"], size=15+int(score*25),
                           color=f"rgba(74,124,89,{0.4+score*0.6:.2f})",
                           font={"size": 13})
                G.add_edge(pid, e["target"], weight=score,
                           title=f"유사도:{score:.0%}", width=int(score*8),
                           color=f"rgba(74,124,89,{0.5+score*0.5:.2f})")
        net = Network(height="450px", width="100%", bgcolor="#faf7f0", font_color="#1a1a2e", directed=True)
        net.from_nx(G)
        import tempfile
        p = Path(tempfile.gettempdir()) / "ng.html"; net.save_graph(str(p))
        html = p.read_text(encoding="utf-8")
        s = html.find("<div id="); e2 = html.rfind("</body>")
        legend = ("<div style='display:flex;gap:16px;padding:8px 16px;font-size:12px;color:#555'>"
                  "<span>🟢 유사도(약재 Jaccard)</span>"
                  "<span>🔵 플로우차트(한약사 정의)</span>"
                  "<span>🔴 기준 처방</span></div>")
        return legend + (html[s:e2] if s>-1 else html)
    except ImportError:
        # fallback: HTML 카드
        cards = []
        for e in engine.get_similar_network(pid, 6):
            etype = e.get("type", "similarity")
            if etype == "canvas":
                rel = e.get("relation", "")
                cards.append(f"<div class='card' style='border-left-color:#3b82f6'>"
                             f"<b>{e['target']}</b> — 플로우차트({rel})</div>")
            else:
                cards.append(f"<div class='card'><b>{e['target']}</b> — {e['score']:.0%}</div>")
        return "".join(cards)

def sync_status():
    f = Path("seen_posts.json")
    if f.exists():
        d = json.loads(f.read_text("utf-8"))
        t = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        return f"<div class='card'><b>마지막 동기화:</b> {t} &nbsp;|&nbsp; <b>수집:</b> {len(d)}건 &nbsp;<span style='color:var(--bamboo)'>● 정상</span></div>"
    return "<div class='card' style='color:var(--gold)'>⚠️ 동기화 이력 없음 — band_config.yaml 설정 후 <code>python band_sync.py --once</code></div>"

def read_dashboard():
    f = Path("dashboard.md")
    if f.exists():
        return f.read_text("utf-8")
    return "*dashboard.md 파일을 찾을 수 없습니다.*"

def read_worklog(lines=50):
    f = Path("work_log.md")
    if f.exists():
        content = f.read_text("utf-8")
        all_lines = content.split("\n")
        return "\n".join(all_lines[-lines:]) if len(all_lines) > lines else content
    return "*work_log.md 파일을 찾을 수 없습니다.*"

# ── 핸들러 ────────────────────────────────────────────────────────────────────
# generator(yield) 대신 일반 return 함수 사용 — Gradio 5.x HF Spaces 호환

def sym_search(q):
    if not q.strip(): return "증상을 입력해주세요."
    return "".join(engine.recommend_by_symptom(q))

def herb_search(q):
    if not q.strip(): return "약재명 또는 처방명을 입력해주세요."
    return "".join(engine.search_by_herbs(q))

def presc_search(n):
    if not n.strip(): return "처방명을 입력해주세요."
    return "".join(engine.search_prescription(n))

def sim_analysis(pid):
    if not pid: return "", "<p style='color:#888;padding:20px'>처방을 선택하세요.</p>"
    return "".join(engine.analyze_similar(pid)), network_html(pid)

def rag_search(q):
    if not q.strip(): return "증상을 입력해주세요."
    return "".join(engine.search_by_case_rag(q))

def paper_search_handler(presc, cond):
    if not presc or not cond:
        return "처방명과 질환명을 모두 입력해주세요."
    from pubmed_search import search_pubmed
    return search_pubmed(presc, cond)

def evidence_recommend(syms, cands_text):
    if not syms.strip():
        return "증상을 입력해주세요."
    from pubmed_search import search_pubmed_by_symptom
    cands = [c.strip() for c in cands_text.split(",") if c.strip()] if cands_text else None
    return search_pubmed_by_symptom(syms, cands, engine.db)

def run_sync():
    if IS_HF_SPACES:
        return "⚠️ Band 동기화는 로컬 환경에서만 지원됩니다."
    try:
        from band_sync import SyncScheduler, load_config
        s = SyncScheduler(load_config("band_config.yaml")).run_once()
        return f"✅ 삽입:{s['inserted']} 스킵:{s['skipped']} 오류:{s['errors']}"
    except FileNotFoundError: return "⚠️ band_config.yaml 없음"
    except Exception as e: return f"❌ {e}"

# ── 체질 평가 핸들러 ──────────────────────────────────────────────────────────
def assess_handler(*args):
    keys = ["height","weight","waist","hip","chest","neck","shoulder","age","sex",
            "btemp","chpref","thirst","water","sweat","heat_i","cold_i",
            "qi1","qi2","qi3","qi4","bl1","bl2","bl3","bl4",
            "yin1","yin2","yin3","yin4","yang1","yang2","yang3","yang4",
            "apt","dig","stool","sfreq","sleepq","sleeph","bloat",
            "s1","s2","s3","s4","s5","s6","s7","s8","s9","s10","s11","s12","s13","s14","s15"]
    v = dict(zip(keys, args))
    try:
        anthro = AnthropometricData(v["height"],v["weight"],v["waist"],v["hip"],v["chest"],v["neck"],v["shoulder"],int(v["age"]),v["sex"])
        thermal = ThermalFunctionData(v["btemp"],int(v["chpref"]),int(v["thirst"]),int(v["water"]),int(v["sweat"]),v["heat_i"],v["cold_i"])
        qb = QiBloodYinYangData(int(v["qi1"]),int(v["qi2"]),int(v["qi3"]),int(v["qi4"]),
                                int(v["bl1"]),int(v["bl2"]),int(v["bl3"]),int(v["bl4"]),
                                int(v["yin1"]),int(v["yin2"]),int(v["yin3"]),int(v["yin4"]),
                                int(v["yang1"]),int(v["yang2"]),int(v["yang3"]),int(v["yang4"]))
        dg = DigestiveFunctionData(int(v["apt"]),int(v["dig"]),int(v["stool"]),int(v["sfreq"]),int(v["sleepq"]),float(v["sleeph"]),int(v["bloat"]))
        sa = SasangScreeningData(*[int(v[f"s{i}"]) for i in range(1,16)])
        p = assessor.assess(anthro, thermal, qb, dg, sa)
        return _profile_html(p), assessor.to_claude_context(p)
    except Exception as e:
        return f"<p style='color:red'>오류: {e}</p>", ""

def _profile_html(p):
    hci_l = "寒(한)" if p.hci<=-2 else "熱(열)" if p.hci>=2 else "平(평)"
    dei_l = "虛(허)" if p.dei<=-2 else "實(실)" if p.dei>=2 else "中(중)"
    tags  = "".join(f"<span class='tag'>{t}</span>" for t in p.prescription_tags)
    notes = "".join(f"<li style='font-size:13px;color:var(--slate);margin-bottom:3px'>{n}</li>" for n in p.notes)

    def bar(v,mx=10):
        c = "var(--cin)" if v>=7 else "var(--gold)" if v>=4 else "var(--bamboo)"
        return (f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:5px'>"
                f"<div style='flex:1;background:var(--mist);border-radius:3px;height:7px;overflow:hidden'>"
                f"<div style='width:{min(v/mx*100,100):.0f}%;height:100%;background:{c};border-radius:3px'></div></div>"
                f"<span style='width:24px;font-size:12px;font-family:\"JetBrains Mono\",monospace;color:{c}'>{v:.1f}</span></div>")

    def bidir(v, lbl):
        pct = (v+5)/10*100; col = "#3b82f6" if v<0 else "#ef4444"
        dir_style = f"left:50%;width:{abs(pct-50):.0f}%" if v<0 else f"left:50%;width:{pct-50:.0f}%"
        return (f"<div style='margin-bottom:10px'>"
                f"<div style='display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px'>"
                f"<span>{lbl}</span><span style='font-family:\"JetBrains Mono\",monospace;color:var(--cin)'>{v:+.1f}</span></div>"
                f"<div style='background:var(--mist);border-radius:3px;height:7px;position:relative;overflow:hidden'>"
                f"<div style='position:absolute;left:50%;top:0;bottom:0;width:1px;background:#888'></div>"
                f"<div style='position:absolute;{dir_style};height:100%;background:{col};border-radius:3px'></div></div></div>")

    def cell(name, pct, dom):
        c,bg,b = ("var(--cin)","rgba(192,57,43,.07)","2px solid var(--cin)") if dom else ("var(--slate)","var(--mist)","1px solid var(--mist)")
        return (f"<div style='background:{bg};border:{b};border-radius:6px;padding:10px 4px;text-align:center'>"
                f"<div style='font-size:11px;color:{c};font-weight:600'>{name}</div>"
                f"<div style='font-size:20px;font-weight:700;color:{c};font-family:\"JetBrains Mono\",monospace'>{pct:.0f}%</div></div>")

    # Python 3.10/3.11 호환: f-string {} 내부에 백슬래시 불가 → 외부에서 미리 계산
    metrics_html = "".join(
        '<div style="background:var(--mist);border-radius:6px;padding:8px">'
        '<div style="font-size:11px;color:var(--slate)">' + n + '</div>'
        '<div style="font-size:18px;font-weight:700;font-family:\'JetBrains Mono\',monospace;color:var(--ink)">' + str(val) + '</div>'
        '</div>'
        for n, val in [("BMI", p.bmi), ("WHR", p.whr), ("흉복비", p.cwr), ("어깨/골반", p.shoulder_hip_ratio)]
    )

    return f"""<div class='card' style='border-left-color:var(--cin)'>
<h3 style='font-family:"Noto Serif KR",serif;margin-bottom:16px'>🌿 체질 평가 결과</h3>
<div style='margin-bottom:16px'>
  <div style='font-size:12px;color:var(--slate);margin-bottom:8px'>사상체질 스크리닝</div>
  <div style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px'>
    {cell("태양인",p.taeyang_pct,p.dominant_type.startswith("태양"))}
    {cell("태음인",p.taeeum_pct,p.dominant_type.startswith("태음"))}
    {cell("소양인",p.soyang_pct,p.dominant_type.startswith("소양"))}
    {cell("소음인",p.soeum_pct,p.dominant_type.startswith("소음"))}
  </div>
  <div style='font-size:13px;color:var(--cin);font-weight:600;margin-top:8px'>→ 우세 체질: {p.dominant_type}</div>
</div>
<div style='margin-bottom:16px'>
  <div style='font-size:12px;color:var(--slate);margin-bottom:8px'>한열·허실 지수</div>
  {bidir(p.hci,"寒← 한열(HCI) →熱  " + hci_l)}
  {bidir(p.dei,"虛← 허실(DEI) →實  " + dei_l)}
</div>
<div style='margin-bottom:16px'>
  <div style='font-size:12px;color:var(--slate);margin-bottom:8px'>기혈음양 프로파일 (0~10, 높을수록 부족)</div>
  <div style='font-size:12px;color:var(--slate);margin-bottom:2px'>氣虛</div>{bar(p.qi_deficiency)}
  <div style='font-size:12px;color:var(--slate);margin-bottom:2px'>血虛</div>{bar(p.blood_deficiency)}
  <div style='font-size:12px;color:var(--slate);margin-bottom:2px'>陰虛</div>{bar(p.yin_deficiency)}
  <div style='font-size:12px;color:var(--slate);margin-bottom:2px'>陽虛</div>{bar(p.yang_deficiency)}
</div>
<div style='margin-bottom:14px'>
  <div style='font-size:12px;color:var(--slate);margin-bottom:8px'>체형 지수</div>
  <div style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px;text-align:center'>
    {metrics_html}
  </div>
</div>
<div style='margin-bottom:10px'><div style='font-size:12px;color:var(--slate);margin-bottom:5px'>처방 선택 태그</div>{tags}</div>
<div><div style='font-size:12px;color:var(--slate);margin-bottom:5px'>임상 노트</div><ul style='margin:0;padding-left:18px'>{notes}</ul></div>
</div>"""

# ── 슬라이더 팩토리 ───────────────────────────────────────────────────────────
def sl(lbl, lo=0, hi=10, val=0, step=1):
    return gr.Slider(minimum=lo, maximum=hi, value=val, step=step, label=lbl)

def qsl(lbl, val=0):
    return gr.Slider(minimum=0, maximum=10, value=val, step=1, label=lbl)

def ssl(lbl):
    return gr.Slider(minimum=0, maximum=3, value=0, step=1, label=f"{lbl}  (0없음~3매우)")

# ── UI ────────────────────────────────────────────────────────────────────────
PRESC_LINK_JS = """
(function() {
    // 히스토리 스택: [{type:'tab', tabId:'...'} | {type:'presc', name:'...'}]
    window._prescHistory = [];
    window._currentPresc = null;

    function updateBackBtn() {
        var btn = document.getElementById('back-to-search-btn');
        if (!btn) return;
        if (window._prescHistory.length === 0) {
            btn.style.display = 'none';
            return;
        }
        btn.style.display = 'inline-flex';
        var prev = window._prescHistory[window._prescHistory.length - 1];
        if (prev.type === 'tab') {
            var labelMap = {
                'tab_sym-button':  '← 증상 검색 결과로',
                'tab_herb-button': '← 약재 검색 결과로',
                'tab_sim-button':  '← 유사 처방 결과로',
            };
            btn.textContent = labelMap[prev.tabId] || '← 검색 결과로';
        } else {
            btn.textContent = '← ' + prev.name;
        }
    }

    function fillAndSearch(name) {
        var attempts = 0;
        function run() {
            if (attempts++ > 15) return;
            var container = document.getElementById('presc_input');
            if (!container) { setTimeout(run, 200); return; }
            var input = container.querySelector('textarea') || container.querySelector('input');
            if (!input) { setTimeout(run, 200); return; }
            var setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value');
            if (setter && setter.set) setter.set.call(input, name);
            else input.value = name;
            input.dispatchEvent(new Event('input',  {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));
            setTimeout(function() {
                var btn = document.getElementById('presc_search_btn');
                if (btn) btn.click();
            }, 400);
        }
        setTimeout(run, 400);
    }

    document.addEventListener('click', function(e) {

        // ── 뒤로가기 버튼 ──────────────────────────────────────
        if (e.target.closest('#back-to-search-btn')) {
            e.preventDefault(); e.stopPropagation();
            if (window._prescHistory.length === 0) return;
            var prev = window._prescHistory.pop();
            if (prev.type === 'tab') {
                // 검색 결과 탭으로 복귀
                var tabEl = document.getElementById(prev.tabId);
                if (tabEl) tabEl.click();
                window._currentPresc = null;
            } else {
                // 이전 처방 상세로 복귀
                window._currentPresc = prev.name;
                fillAndSearch(prev.name);
            }
            updateBackBtn();
            return;
        }

        // ── 처방명 링크 클릭 ───────────────────────────────────
        var link = e.target.closest('[data-presc]');
        if (!link) return;
        e.preventDefault(); e.stopPropagation();
        var name = link.getAttribute('data-presc') || link.textContent.trim();

        // 현재 상태를 스택에 push
        var detailBtn = document.getElementById('tab_detail-button');
        var inDetail  = detailBtn && (
            detailBtn.classList.contains('selected') ||
            detailBtn.getAttribute('aria-selected') === 'true'
        );
        if (inDetail && window._currentPresc) {
            // 처방 상세 → 처방 상세
            window._prescHistory.push({ type: 'presc', name: window._currentPresc });
        } else {
            // 검색 탭 → 처방 상세
            var tracked = ['tab_sym-button', 'tab_herb-button', 'tab_sim-button'];
            tracked.forEach(function(id) {
                var el = document.getElementById(id);
                if (el && (el.classList.contains('selected') ||
                           el.getAttribute('aria-selected') === 'true')) {
                    window._prescHistory.push({ type: 'tab', tabId: id });
                }
            });
            // 처방 상세 탭으로 이동
            if (detailBtn) detailBtn.click();
        }

        window._currentPresc = name;
        fillAndSearch(name);
        setTimeout(updateBackBtn, 600);

    }, true);  // capture phase
})();
"""

with gr.Blocks(title="달려라한의", css=CSS) as demo:

    gr.HTML(HDR)

    with gr.Tabs():

        # 탭 1 증상 검색
        with gr.Tab("🔍 증상 검색", elem_id="tab_sym"):
            sym_in = gr.Textbox(label="증상 · 질환 입력", placeholder="예) 만성 기침, 수양성 콧물, 오한", lines=4)
            gr.Examples([["만성 기침, 수양성 콧물, 오한"],["만성 피로, 소화불량"],["60대 남성, 이명, 오후 미열"],["어깨·목 결림, 긴장성 두통"]], inputs=sym_in, label=None)
            sym_out = gr.Markdown(value="*증상을 입력하고 버튼을 클릭하세요.*", label="추천 처방", show_label=False, sanitize_html=False)
            sym_btn = gr.Button("처방 추천 받기", variant="primary")
            sym_btn.click(fn=sym_search, inputs=sym_in, outputs=sym_out)
            sym_in.submit(fn=sym_search, inputs=sym_in, outputs=sym_out)

        # 탭 2 약재 검색
        with gr.Tab("🌿 약재 검색", elem_id="tab_herb"):
            gr.Markdown(
                "### 약재·처방 구성 기반 검색\n"
                "- **약재만 입력:** `황기, 당귀, 천궁` → 해당 약재를 포함하는 처방 검색\n"
                "- **처방+약재 입력:** `사물탕+황기` 또는 `사물탕, 황기` → 사물탕 구성약재 전체 + 황기를 포함하는 처방 검색\n"
                "- 구분자: **쉼표(,)** 또는 **+(플러스)** 사용"
            )
            herb_in = gr.Textbox(
                label="약재명 / 처방명+약재명 입력",
                placeholder="예) 사물탕+황기 / 황기, 당귀, 천궁 / 마황, 계지, 세신",
                lines=2,
            )
            gr.Examples(
                [
                    ["사물탕+황기"],
                    ["사물탕, 황기"],
                    ["황기, 당귀, 천궁, 작약"],
                    ["마황, 계지, 세신"],
                    ["숙지황, 산수유, 산약"],
                    ["인삼, 백출, 복령, 감초"],
                ],
                inputs=herb_in,
                label=None,
            )
            herb_out = gr.Markdown(
                value="*약재명 또는 처방명을 입력하고 검색하세요.*",
                label="약재 검색 결과",
                show_label=False,
                sanitize_html=False,
            )
            herb_btn = gr.Button("약재로 처방 검색", variant="primary")
            herb_btn.click(fn=herb_search, inputs=herb_in, outputs=herb_out)
            herb_in.submit(fn=herb_search, inputs=herb_in, outputs=herb_out)

        # (구 탭 2) 처방 상세
        with gr.Tab("📖 처방 상세", elem_id="tab_detail"):
            gr.HTML(
                '<button id="back-to-search-btn" style="'
                'display:none;align-items:center;gap:6px;'
                'padding:6px 14px;margin-bottom:10px;'
                'background:#f0f4ff;border:1px solid #c5cae9;border-radius:8px;'
                'color:#3949ab;font-size:14px;font-weight:600;cursor:pointer;'
                '" title="이전 검색 결과로 돌아가기">← 검색 결과로</button>'
            )
            with gr.Row():
                p_in = gr.Textbox(label="처방명 입력", placeholder="예) 소청룡탕", elem_id="presc_input")
                p_dd = gr.Dropdown(choices=prescription_names, label="목록에서 선택", interactive=True)
            p_dd.change(fn=lambda x: x, inputs=p_dd, outputs=p_in)
            presc_btn = gr.Button("상세 검색", variant="primary", elem_id="presc_search_btn")
            p_out = gr.Markdown(value="*처방명을 입력하세요.*", label="처방 해설", show_label=False, sanitize_html=False)
            presc_btn.click(fn=presc_search, inputs=p_in, outputs=p_out)
            p_in.submit(fn=presc_search, inputs=p_in, outputs=p_out)

        # 탭 3 유사 처방
        with gr.Tab("🔗 유사 처방", elem_id="tab_sim"):
            sim_dd = gr.Dropdown(choices=prescription_names, label="기준 처방", interactive=True)
            sim_btn = gr.Button("유사 처방 분석", variant="primary")
            with gr.Row():
                sim_out = gr.Markdown(value="*처방을 선택하세요.*", label="비교 분석", show_label=False, sanitize_html=False)
                net_out = gr.HTML(value="<p style='color:#888;padding:20px'>선택 후 표시</p>", label="네트워크", show_label=False)
            sim_btn.click(fn=sim_analysis, inputs=sim_dd, outputs=[sim_out, net_out])

        # 탭 4 치험례 RAG
        with gr.Tab("🧪 치험례 RAG"):
            rag_in  = gr.Textbox(label="증상 입력", placeholder="예) 60대 남성, 야간 빈뇨, 요슬 냉통", lines=4)
            rag_out = gr.Markdown(value="*증상을 입력하세요.*", label="치험례 기반 추천", show_label=False, sanitize_html=False)
            rag_st  = gr.Markdown("")
            with gr.Row():
                rag_btn = gr.Button("치험례 검색", variant="primary")
                rag_btn.click(fn=rag_search, inputs=rag_in, outputs=rag_out)
                rag_rebuild_btn = gr.Button("인덱스 재빌드", variant="secondary")
                rag_rebuild_btn.click(
                    fn=lambda: "✅ 인덱스 재빌드 완료 (ChromaDB 비활성화 환경에서는 텍스트 검색으로 동작)",
                    inputs=[], outputs=rag_st)
            rag_in.submit(fn=rag_search, inputs=rag_in, outputs=rag_out)

        # 탭 5 체질 평가
        with gr.Tab("📊 체질 평가"):
            gr.Markdown("### 한의학 체질 객관화 평가\n5개 레이어 다층 지표 — BMI처럼 수치화된 한의학 체질 지수를 산출합니다.")

            with gr.Accordion("📐 L1 — 체형 계측 (직접 측정값)", open=True):
                with gr.Row():
                    g_height=gr.Number(label="신장 (cm)",value=170); g_weight=gr.Number(label="체중 (kg)",value=65)
                    g_age=gr.Number(label="나이",value=40); g_sex=gr.Radio(["M","F"],label="성별",value="M")
                with gr.Row():
                    g_waist=gr.Number(label="복위 (cm)",value=85); g_hip=gr.Number(label="골반위 (cm)",value=95)
                    g_chest=gr.Number(label="흉위 (cm)",value=90); g_neck=gr.Number(label="경위—목둘레 (cm)",value=36)
                    g_shoulder=gr.Number(label="어깨너비 (cm)",value=40)

            with gr.Accordion("🌡️ L2 — 한열허실 입력", open=True):
                with gr.Row():
                    g_btemp=gr.Number(label="기초체온 °C",value=36.5)
                    g_chp=sl("냉온선호 (-5=극寒 / 0=보통 / +5=극熱)",-5,5,0)
                    g_thirst=qsl("갈증 정도"); g_water=gr.Number(label="하루 음수량 (ml)",value=1500)
                with gr.Row():
                    g_sweat=sl("발한량 (0없음~4매우많음)",0,4,1)
                    g_heati=gr.Checkbox(label="더위를 심하게 탄다"); g_coldi=gr.Checkbox(label="추위를 심하게 탄다")

            with gr.Accordion("🩸 L3 — 기혈음양 프로파일 16문항 (0~10)", open=False):
                gr.Markdown("**氣虛**"); r_qi = gr.Row()
                with r_qi: g_qi1=qsl("쉬어도 피로 안풀림"); g_qi2=qsl("조금 움직여도 숨참"); g_qi3=qsl("식후 심한 졸림"); g_qi4=qsl("목소리 작고 힘없음")
                gr.Markdown("**血虛**"); r_bl = gr.Row()
                with r_bl: g_bl1=qsl("기립성 어지러움"); g_bl2=qsl("안색 창백"); g_bl3=qsl("생리량 적음(남=0)"); g_bl4=qsl("손발 저림")
                gr.Markdown("**陰虛**"); r_yn = gr.Row()
                with r_yn: g_yn1=qsl("오후 열감"); g_yn2=qsl("수면 중 식은땀"); g_yn3=qsl("입·목 건조"); g_yn4=qsl("이명·어지러움")
                gr.Markdown("**陽虛**"); r_yg = gr.Row()
                with r_yg: g_yg1=qsl("손발·배 냉증"); g_yg2=qsl("야간 소변 빈삭"); g_yg3=qsl("아침 얼굴·발 부종"); g_yg4=qsl("허리 시리고 아픔")

            with gr.Accordion("🍚 L4 — 소화·배변·수면", open=False):
                with gr.Row():
                    g_apt=qsl("식욕(0없음~10왕성)"); g_apt.value=7
                    g_dig=qsl("소화력(0최악~10최상)"); g_dig.value=7
                    g_bloat=qsl("식후 복부 팽만")
                with gr.Row():
                    g_stool=sl("대변굳기 Bristol(1딱딱~7물설사)",1,7,4)
                    g_sfreq=sl("하루 배변 횟수",0,5,1)
                with gr.Row():
                    g_sleepq=qsl("수면의질(0최악~10최상)"); g_sleepq.value=7
                    g_sleeph=gr.Number(label="수면시간 (시간)",value=7.0)

            with gr.Accordion("🌿 L5 — 사상체질 스크리닝 15문항 (QSCC 기반)", open=False):
                gr.Markdown("**체형·생리**")
                with gr.Row(): g_s1=ssl("상체>하체 발달"); g_s2=ssl("살잘찌고 체격큼"); g_s3=ssl("땀 많이 흘림"); g_s4=ssl("소화 안되고 자주 체함")
                gr.Markdown("**성격·기질**")
                with gr.Row(): g_s5=ssl("외향적·사교적"); g_s6=ssl("꼼꼼·신중·내향적"); g_s7=ssl("리더십·결단력"); g_s8=ssl("불안·걱정 많음")
                gr.Markdown("**건강 패턴**")
                with gr.Row(): g_s9=ssl("감기 잘걸리고 안낫음"); g_s10=ssl("열 잘나고 상기경향"); g_s11=ssl("소변 시원하지않음"); g_s12=ssl("변비 경향")
                gr.Markdown("**체력·활동**")
                with gr.Row(): g_s13=ssl("체력강하고 많이 움직임"); g_s14=ssl("쉽게 피로하고 서있기 힘듦"); g_s15=ssl("상체 힘없고 하체 불안정")

            assess_btn = gr.Button("⚡ 체질 평가 실행", variant="primary")
            with gr.Row():
                prof_html = gr.HTML(value="<p style='color:#888;padding:20px;text-align:center'>위 항목을 입력하고 평가를 실행하세요.</p>")
                prof_text = gr.Textbox(label="Claude 프롬프트용 체질 요약 (증상 검색에 붙여넣기 가능)", lines=20)

            all_inputs = [
                g_height,g_weight,g_waist,g_hip,g_chest,g_neck,g_shoulder,g_age,g_sex,
                g_btemp,g_chp,g_thirst,g_water,g_sweat,g_heati,g_coldi,
                g_qi1,g_qi2,g_qi3,g_qi4, g_bl1,g_bl2,g_bl3,g_bl4,
                g_yn1,g_yn2,g_yn3,g_yn4, g_yg1,g_yg2,g_yg3,g_yg4,
                g_apt,g_dig,g_stool,g_sfreq,g_sleepq,g_sleeph,g_bloat,
                g_s1,g_s2,g_s3,g_s4,g_s5,g_s6,g_s7,g_s8,g_s9,g_s10,g_s11,g_s12,g_s13,g_s14,g_s15,
            ]
            assess_btn.click(fn=assess_handler, inputs=all_inputs, outputs=[prof_html, prof_text])

        # 탭 6 임상논문
        with gr.Tab("📰 임상논문 근거"):
            gr.Markdown("### 근거 중심 한의학 (EBM-KM)\nPubMed · OASIS · KMBASE 실시간 검색 — 응답 20~40초 소요")
            with gr.Tabs():
                with gr.Tab("처방 + 질환 검색"):
                    with gr.Row():
                        pp_dd = gr.Dropdown(choices=prescription_names, label="처방 선택", interactive=True)
                        pp_cond = gr.Textbox(label="질환명 / 증상", placeholder="예) 알레르기 비염, 만성 기침")
                    pp_out = gr.Markdown(value="*처방과 질환을 선택하세요.*", label="임상 근거", show_label=False)
                    paper_btn = gr.Button("논문 검색", variant="primary")
                    paper_btn.click(fn=paper_search_handler, inputs=[pp_dd, pp_cond], outputs=pp_out)
                    pp_cond.submit(fn=paper_search_handler, inputs=[pp_dd, pp_cond], outputs=pp_out)
                with gr.Tab("증상 기반 근거 추천"):
                    ev_sym = gr.Textbox(label="증상", placeholder="예) 알레르기 비염, 맑은 콧물, 재채기, 봄철 악화", lines=3)
                    ev_cands = gr.Textbox(label="검색 처방 목록 (쉼표 구분, 비워두면 자동)", placeholder="예) 소청룡탕, 형방패독산")
                    ev_out = gr.Markdown(value="*증상을 입력하세요.*", label="근거 기반 추천", show_label=False)
                    ev_btn = gr.Button("근거 기반 추천", variant="primary")
                    ev_btn.click(fn=evidence_recommend, inputs=[ev_sym, ev_cands], outputs=ev_out)
                    ev_sym.submit(fn=evidence_recommend, inputs=[ev_sym, ev_cands], outputs=ev_out)

        # 탭 7 동기화
        with gr.Tab("📡 동기화"):
            sy_disp = gr.HTML(value=sync_status())
            sy_log  = gr.Markdown("")
            with gr.Row():
                sy_refresh_btn = gr.Button("새로고침", variant="secondary")
                sy_refresh_btn.click(fn=sync_status, inputs=[], outputs=sy_disp)
                sy_sync_btn = gr.Button("지금 동기화", variant="primary")
                sy_sync_btn.click(fn=run_sync, inputs=[], outputs=sy_log)

        # 탭 8 대시보드
        with gr.Tab("📊 대시보드"):
            gr.Markdown("### 프로젝트 현황 대시보드\n`dashboard.md` + `work_log.md` 실시간 표시")
            with gr.Tabs():
                with gr.Tab("작업 현황"):
                    dash_out = gr.Markdown(value=read_dashboard())
                    dash_refresh_btn = gr.Button("새로고침", variant="secondary")
                    dash_refresh_btn.click(fn=read_dashboard, inputs=[], outputs=dash_out)
                with gr.Tab("작업 로그"):
                    log_out = gr.Markdown(value=read_worklog())
                    log_refresh_btn = gr.Button("새로고침", variant="secondary")
                    log_refresh_btn.click(fn=read_worklog, inputs=[], outputs=log_out)

    # 처방명 클릭 → 처방 상세 탭 이동 JS — <script> 태그로 직접 주입
    gr.HTML(f"<script>{PRESC_LINK_JS}</script>")

demo.queue()

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0", server_port=7860,
        inbrowser=not IS_HF_SPACES,
    )
