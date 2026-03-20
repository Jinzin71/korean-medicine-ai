"""
local_engine.py — Obsidian vault 기반 로컬 검색 엔진
=========================================================
Claude API 없이 SQLite DB + 텍스트 매칭으로 동작합니다.
vault_parser.py 로 파싱한 532개 처방 데이터를 활용합니다.

기능:
  A. 증상/질환 → 처방 추천 (적응증 태그 + 설명 텍스트 매칭)
  B. 처방명 직접 검색 → 상세 정보 표시
  C. 유사 처방 분석 → 약재 가감 비교
  D. 치험례 검색 → DB 텍스트 매칭
  E. 유사도 네트워크 데이터
"""

import re
from typing import Optional
from prescription_db import PrescriptionDB, Prescription, Case
from herb_knowledge import (
    format_herb_diff_analysis, analyze_herb_group,
    CATEGORY_DESC, CATEGORY_CONSTITUTION, HERB_FUNCTIONS,
)
from canvas_parser import CanvasParser


# ─────────────────────────────────────────────────────────────────────────────
# 텍스트 매칭 유틸
# ─────────────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    """한글 키워드 토큰화 — 조사/공백 기준 분리"""
    text = re.sub(r"[,\.·\-/\(\)\[\]{}\"']", " ", text)
    return {t for t in text.split() if len(t) >= 2}


def _match_score(query_tokens: set[str], target_tokens: set[str]) -> float:
    """쿼리 토큰이 타겟에 얼마나 포함되는지 비율"""
    if not query_tokens:
        return 0.0
    hits = sum(1 for qt in query_tokens if any(qt in tt or tt in qt for tt in target_tokens))
    return hits / len(query_tokens)


def _symptom_relevance(query: str, p: Prescription, cases: list[Case]) -> float:
    """처방의 증상 관련도 점수 (0~1)"""
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0.0

    # 적응증 태그 매칭 (가중치 높음)
    ind_text = " ".join(p.indications)
    ind_score = _match_score(q_tokens, _tokenize(ind_text))

    # 설명 텍스트 매칭
    desc_score = _match_score(q_tokens, _tokenize(p.description))

    # 치험례 증상 매칭
    case_text = " ".join(c.symptoms for c in cases[:20])
    case_score = _match_score(q_tokens, _tokenize(case_text)) if case_text else 0.0

    # 직접 문자열 포함 보너스
    direct_hits = sum(1 for qt in q_tokens if qt in ind_text or qt in p.description)
    direct_bonus = min(direct_hits / max(len(q_tokens), 1) * 0.3, 0.3)

    return min(1.0, ind_score * 0.5 + desc_score * 0.25 + case_score * 0.15 + direct_bonus)


# ─────────────────────────────────────────────────────────────────────────────
# 마크다운 포매터
# ─────────────────────────────────────────────────────────────────────────────

def _presc_link(name: str) -> str:
    """처방명을 클릭 가능한 HTML 스팬으로 감싸기"""
    return f'<span class="presc-link" title="클릭하여 상세 보기">{name}</span>'


def _format_herbs_table(p: Prescription) -> str:
    """약재 구성 — 같은 용량끼리 묶어서 한눈에 표시"""
    if not p.herbs_detail:
        return ", ".join(p.herbs)

    from collections import OrderedDict
    # 용량별 그룹핑 (원래 순서 보존, 첫 등장 용량 순)
    dose_groups: OrderedDict[str, list[str]] = OrderedDict()
    for herb, dose in p.herbs_detail.items():
        dose_groups.setdefault(dose, []).append(herb)

    lines = []
    for dose, herbs in dose_groups.items():
        herbs_str = ", ".join(herbs)
        lines.append(f"**{dose}** — {herbs_str}")
    return "\n\n".join(lines)


def _format_prescription_detail(p: Prescription, cases: list[Case],
                                 similar: list[tuple[Prescription, float]]) -> str:
    """처방 상세 마크다운"""
    sections = []

    # 기본 정보
    header = f"## {p.name}"
    if p.code:
        header += f"  `{p.code}`"
    sections.append(header)

    if p.section:
        sections.append(f"**분류:** {p.section}")

    # 설명
    if p.description:
        sections.append(f"\n### 처방 설명\n{p.description}")

    # 약재 구성
    sections.append(f"\n### 구성 약재 ({len(p.herbs)}종)")
    sections.append(_format_herbs_table(p))

    # 적응증
    if p.indications:
        tags = "  ".join(f"`#{ind}`" for ind in p.indications)
        sections.append(f"\n### 적응증\n{tags}")

    # 치험례
    if cases:
        sections.append(f"\n### 치험례 ({len(cases)}건)")
        for i, c in enumerate(cases[:10], 1):
            info_parts = []
            if c.patient_age:
                info_parts.append(c.patient_age)
            if c.patient_sex:
                info_parts.append(c.patient_sex)
            if c.patient_bmi:
                info_parts.append(f"BMI {c.patient_bmi}")
            if c.constitution:
                info_parts.append(c.constitution)
            patient_info = " / ".join(info_parts) if info_parts else ""
            symptoms = c.symptoms or c.content[:100]
            line = f"{i}. "
            if patient_info:
                line += f"**[{patient_info}]** "
            line += symptoms
            if c.url:
                line += f"  [링크]({c.url})"
            sections.append(line)

    # 유사 처방 (약재 차이 분석 포함)
    if similar:
        sections.append(f"\n### 유사 처방")
        for sp, score in similar[:5]:
            shared = set(p.herbs) & set(sp.herbs)
            added = set(sp.herbs) - set(p.herbs)
            removed = set(p.herbs) - set(sp.herbs)
            sections.append('<div class="sim-card">')
            sections.append(
                f"**{_presc_link(sp.name)}** (유사도 {score:.0%})\n"
                f"- 공통: {', '.join(sorted(shared)) if shared else '없음'}\n"
                f"- 추가: {', '.join(sorted(added)) if added else '없음'}\n"
                f"- 제거: {', '.join(sorted(removed)) if removed else '없음'}"
            )
            sections.append('</div>')

        # 상위 3개 유사 처방에 대한 상세 분석
        sections.append(f"\n### 유사 처방 차이 분석")
        for sp, score in similar[:3]:
            sections.append('<div class="sim-card">')
            analysis = format_herb_diff_analysis(
                p.name, sp.name, p.herbs, sp.herbs,
                p.indications, sp.indications,
            )
            sections.append(f"\n{analysis}")
            sections.append('</div>')

    # 관련 처방
    if p.related:
        sections.append(f"\n### 관련 처방 (본문 링크)")
        sections.append(", ".join(_presc_link(r) for r in p.related))

    return "\n".join(sections)


def _format_symptom_results(query: str, scored: list[tuple[Prescription, list[Case], float]]) -> str:
    """증상 검색 결과 마크다운"""
    if not scored:
        return f"**'{query}'**에 해당하는 처방을 찾지 못했습니다.\n\n다른 증상 키워드로 검색해 보세요."

    sections = [f"## 「{query}」 검색 결과\n"]
    sections.append(f"총 **{len(scored)}개** 처방이 검색되었습니다.\n")

    for rank, (p, cases, score) in enumerate(scored[:8], 1):
        sections.append(f"---\n### {rank}. {_presc_link(p.name)}  (관련도 {score:.0%})")

        if p.code:
            sections.append(f"`{p.code}`  |  {p.section}")

        # 적응증
        if p.indications:
            # 쿼리와 매칭되는 태그 강조
            q_tokens = _tokenize(query)
            tags = []
            for ind in p.indications[:15]:
                if any(qt in ind or ind in qt for qt in q_tokens):
                    tags.append(f"**`#{ind}`**")
                else:
                    tags.append(f"`#{ind}`")
            sections.append("적응증: " + "  ".join(tags))

        # 설명 발췌
        if p.description:
            desc = p.description[:300]
            if len(p.description) > 300:
                desc += "..."
            sections.append(f"\n> {desc}")

        # 약재
        if p.herbs_detail:
            herb_str = ", ".join(f"{h}({d})" for h, d in list(p.herbs_detail.items())[:12])
            if len(p.herbs_detail) > 12:
                herb_str += f" 외 {len(p.herbs_detail)-12}종"
            sections.append(f"\n**구성:** {herb_str}")
        elif p.herbs:
            sections.append(f"\n**구성:** {', '.join(p.herbs[:12])}")

        # 치험례 요약
        if cases:
            sections.append(f"\n**치험례** {len(cases)}건:")
            for c in cases[:3]:
                info = []
                if c.patient_age:
                    info.append(c.patient_age)
                if c.patient_sex:
                    info.append(c.patient_sex)
                symptoms = c.symptoms or c.content[:80]
                prefix = f"[{'/'.join(info)}] " if info else ""
                sections.append(f"- {prefix}{symptoms}")

    return "\n".join(sections)


def _format_similar_analysis(target: Prescription, similar: list[tuple[Prescription, float]],
                             canvas: CanvasParser = None) -> str:
    """유사 처방 분석 마크다운 — 약재 기능 차이 + 체질 타겟 + 캔버스 관계 포함"""
    if not similar:
        return f"**{target.name}**과 유사한 처방을 찾지 못했습니다."

    sections = [f"## {target.name} — 유사 처방 비교 분석\n"]

    # 기준 처방 요약 + 약재 카테고리 분석
    sections.append(f"**기준 처방:** {target.name} (`{target.code}`)")
    if target.herbs_detail:
        herb_str = ", ".join(f"{h}({d})" for h, d in target.herbs_detail.items())
    else:
        herb_str = ", ".join(target.herbs)
    sections.append(f"**구성:** {herb_str}")

    target_group = analyze_herb_group(target.herbs)
    if target_group["categories"]:
        cat_str = ", ".join(f"{c}({n})" for c, n in target_group["categories"].items())
        sections.append(f"**약재 카테고리:** {cat_str}")
    if target_group["main_categories"]:
        main_descs = [CATEGORY_DESC.get(c, c) for c in target_group["main_categories"]]
        sections.append(f"**주된 치료 방향:** {' + '.join(main_descs)}")
    sections.append("")

    # 비교 테이블
    sections.append("### 약재 가감 비교\n")
    sections.append("| 유사 처방 | 유사도 | 공통 약재 | 추가된 약재 | 빠진 약재 |")
    sections.append("|-----------|--------|-----------|-------------|-----------|")

    for sp, score in similar:
        shared = sorted(set(target.herbs) & set(sp.herbs))
        added = sorted(set(sp.herbs) - set(target.herbs))
        removed = sorted(set(target.herbs) - set(sp.herbs))
        sections.append(
            f"| {_presc_link(sp.name)} | {score:.0%} | "
            f"{', '.join(shared[:5])}{'...' if len(shared)>5 else ''} | "
            f"{', '.join(added) if added else '-'} | "
            f"{', '.join(removed) if removed else '-'} |"
        )

    # ── 각 처방 상세 비교 + 기능 분석 ──
    sections.append("\n### 개별 비교 · 기능 분석\n")
    for sp, score in similar:
        shared = set(target.herbs) & set(sp.herbs)
        added = set(sp.herbs) - set(target.herbs)
        removed = set(target.herbs) - set(sp.herbs)

        sections.append('<div class="sim-card">')
        sections.append(f"\n#### {_presc_link(sp.name)}  (유사도 {score:.0%})")
        if sp.code:
            sections.append(f"`{sp.code}`  |  {sp.section}")

        # 용량 비교 (공통 약재)
        if target.herbs_detail and sp.herbs_detail and shared:
            dose_diffs = []
            for h in sorted(shared):
                d1 = target.herbs_detail.get(h, "?")
                d2 = sp.herbs_detail.get(h, "?")
                if d1 != d2:
                    dose_diffs.append(f"{h}: {target.name} {d1} → {sp.name} {d2}")
            if dose_diffs:
                sections.append("\n**용량 차이:**")
                for dd in dose_diffs:
                    sections.append(f"- {dd}")

        # ★ 약재 기능 차이 분석 ★
        diff_analysis = format_herb_diff_analysis(
            target.name, sp.name, target.herbs, sp.herbs,
            target.indications, sp.indications,
        )
        sections.append(f"\n{diff_analysis}")

        if sp.description:
            sections.append(f"\n> {sp.description[:200]}{'...' if len(sp.description)>200 else ''}")

        sections.append('\n</div>\n')

    # ── 캔버스 관계 (플로우차트가 있는 경우) ──
    if canvas and canvas.has_canvas_data(target.name):
        related = canvas.get_related(target.name)
        if related:
            sections.append("### 플로우차트 관계도 (한의사 정의)\n")
            sections.append(f"**{target.name}**에서 연결된 처방 {len(related)}개:\n")

            # 관계 방향별 분류
            parents = [r for r in related if r["relation"] == "parent"]
            children = [r for r in related if r["relation"] == "child"]
            siblings = [r for r in related if r["relation"] == "sibling"]

            if parents:
                sections.append("**상위 처방 (이 처방의 근원):**")
                for r in parents:
                    code_str = f" `{r['code']}`" if r["code"] else ""
                    sections.append(f"- ⬆ {_presc_link(r['name'])}{code_str}")

            if children:
                sections.append("\n**파생 처방 (이 처방에서 발전):**")
                for r in children:
                    code_str = f" `{r['code']}`" if r["code"] else ""
                    sections.append(f"- ⬇ {_presc_link(r['name'])}{code_str}")

            if siblings:
                sections.append("\n**연관 처방:**")
                for r in siblings:
                    code_str = f" `{r['code']}`" if r["code"] else ""
                    sections.append(f"- ↔ {_presc_link(r['name'])}{code_str}")

    return "\n".join(sections)


# ─────────────────────────────────────────────────────────────────────────────
# 통합 로컬 엔진
# ─────────────────────────────────────────────────────────────────────────────

class LocalHerbEngine:
    """
    Claude API 없이 vault 데이터만으로 동작하는 로컬 엔진.
    HerbEngine과 동일한 인터페이스를 제공합니다.
    """

    def __init__(self, db_path: str = "prescriptions.db", vault_path: str = "방약합편",
                 canvas_dir: str = "플로우차트"):
        self.db = PrescriptionDB(db_path)
        from pathlib import Path
        if Path(vault_path).exists():
            count = self.db.load_from_vault(vault_path)
            print(f"[LocalHerbEngine] Vault 로드 완료: {count}개 처방")
        else:
            self.db.load_mock_data()
            print("[LocalHerbEngine] Vault 없음, mock 데이터 사용")

        # 캔버스 파서 초기화
        self.canvas = CanvasParser(canvas_dir)
        stats = self.canvas.stats
        if stats["total_nodes"] > 0:
            print(f"[LocalHerbEngine] 캔버스 로드: {stats['canvas_files']}개 파일, "
                  f"{stats['total_nodes']}개 노드, {stats['total_edges']}개 엣지")

    # ── 증상 → 처방 추천 ──────────────────────────────────────────────────

    def recommend_by_symptom(self, query: str):
        """증상/질환 → 처방 추천 (generator, 즉시 반환)"""
        all_p = self.db.get_all_prescriptions()

        scored = []
        for p in all_p:
            cases = self.db.get_cases(p.id)
            score = _symptom_relevance(query, p, cases)
            if score > 0.05:
                scored.append((p, cases, score))

        scored.sort(key=lambda x: x[2], reverse=True)
        yield _format_symptom_results(query, scored)

    # ── 처방 상세 검색 ────────────────────────────────────────────────────

    def search_prescription(self, name: str):
        """처방명 직접 검색 (generator)"""
        p = self.db.get_prescription(name)
        if not p:
            # 부분 매칭 시도
            all_p = self.db.get_all_prescriptions()
            matches = [pp for pp in all_p if name in pp.name or pp.name in name]
            if matches:
                p = matches[0]
                if len(matches) > 1:
                    names = ", ".join(m.name for m in matches[:10])
                    yield f"**'{name}'** 검색 결과 {len(matches)}개: {names}\n\n---\n\n"
            else:
                yield f"**'{name}'** 처방을 찾을 수 없습니다.\n\n유사한 이름의 처방도 없습니다."
                return

        cases = self.db.get_cases(p.id)
        similar = self.db.get_similar_prescriptions(p.id, top_k=5)
        yield _format_prescription_detail(p, cases, similar)

    # ── 유사 처방 분석 ────────────────────────────────────────────────────

    def analyze_similar(self, prescription_id: str):
        """유사 처방 분석 (generator) — 약재 기능 분석 + 캔버스 관계 포함"""
        target = self.db.get_prescription(prescription_id)
        if not target:
            yield f"처방을 찾을 수 없습니다: {prescription_id}"
            return
        similar = self.db.get_similar_prescriptions(prescription_id, top_k=6)
        yield _format_similar_analysis(target, similar, canvas=self.canvas)

    # ── 치험례 검색 ──────────────────────────────────────────────────────

    def search_by_case_rag(self, query: str):
        """치험례 텍스트 매칭 검색 (generator)"""
        q_tokens = _tokenize(query)
        all_p = self.db.get_all_prescriptions()

        matched_cases = []
        for p in all_p:
            cases = self.db.get_cases(p.id)
            for c in cases:
                text = f"{c.symptoms} {c.content}"
                c_tokens = _tokenize(text)
                score = _match_score(q_tokens, c_tokens)
                # 직접 포함 보너스
                direct = sum(1 for qt in q_tokens if qt in text)
                score += min(direct / max(len(q_tokens), 1) * 0.4, 0.4)
                if score > 0.1:
                    matched_cases.append((p, c, score))

        matched_cases.sort(key=lambda x: x[2], reverse=True)

        if not matched_cases:
            yield f"**'{query}'**와 관련된 치험례를 찾지 못했습니다."
            return

        sections = [f"## 「{query}」 치험례 검색 결과\n"]
        sections.append(f"총 **{len(matched_cases)}건** 매칭\n")

        for i, (p, c, score) in enumerate(matched_cases[:15], 1):
            info_parts = []
            if c.patient_age:
                info_parts.append(c.patient_age)
            if c.patient_sex:
                info_parts.append(c.patient_sex)
            if c.patient_bmi:
                info_parts.append(f"BMI {c.patient_bmi}")
            if c.constitution:
                info_parts.append(c.constitution)

            patient_info = " / ".join(info_parts) if info_parts else "정보 없음"
            sections.append(f"### {i}. {_presc_link(p.name)} — 관련도 {score:.0%}")
            sections.append(f"**환자:** {patient_info}")
            symptoms = c.symptoms or c.content[:150]
            sections.append(f"**증상:** {symptoms}")
            if c.url:
                sections.append(f"[원문 링크]({c.url})")
            sections.append("")

        # 처방별 빈도 요약
        from collections import Counter
        presc_counts = Counter(p.name for p, c, s in matched_cases)
        if presc_counts:
            sections.append("\n---\n### 처방별 치험례 빈도")
            for name, cnt in presc_counts.most_common(10):
                sections.append(f"- **{name}**: {cnt}건")

        yield "\n".join(sections)

    # ── 네트워크 데이터 ──────────────────────────────────────────────────

    def get_similar_network(self, prescription_id: str, top_k: int = 5) -> list[dict]:
        """유사도 네트워크 + 캔버스 관계 병합"""
        target = self.db.get_prescription(prescription_id)
        if not target:
            return []

        # 기존 Jaccard 유사도 기반 엣지
        similar = self.db.get_similar_prescriptions(prescription_id, top_k=top_k)
        edges = [
            {"source": target.name, "target": p.name, "score": round(score, 3), "type": "similarity"}
            for p, score in similar
        ]

        # 캔버스 관계 엣지 추가
        existing_targets = {e["target"] for e in edges}
        canvas_related = self.canvas.get_related(target.name)
        for rel in canvas_related:
            if rel["name"] not in existing_targets and rel["name"] != target.name:
                edges.append({
                    "source": target.name,
                    "target": rel["name"],
                    "score": 0,
                    "type": "canvas",
                    "relation": rel["relation"],
                    "color": rel.get("color", ""),
                })
                existing_targets.add(rel["name"])

        return edges

    def get_all_prescription_names(self) -> list[str]:
        return sorted(p.name for p in self.db.get_all_prescriptions())
