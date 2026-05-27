"""
Flowchart-style prescription support built from prescription_ex case files.

This module is intentionally separate from app.py so the existing search app keeps
working unchanged.  It loads the hydrated BAND case markdown files, indexes the
full original text, and turns a new intake form into:

- ranked prescription candidates
- similar case evidence
- discriminating follow-up questions
- prescription-vs-prescription comparison notes

The output is decision support for trained clinical use, not autonomous medical
advice.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from prescription_db import Prescription, PrescriptionDB


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CASE_DIR = BASE_DIR / "prescription_ex"
DEFAULT_DB_PATH = BASE_DIR / "prescriptions.db"
PRESCRIPTION_DOC_DIRS = (BASE_DIR / "방약합편", BASE_DIR / "새로보는 방약합편")
HERB_DOC_DIR = BASE_DIR / "약재"
STYLE_AUTHORS = ("이종대", "이윤호(98) since2002")


INTAKE_TEMPLATE = """■ 신장cm
■ 체중 kg
■ 체질 : **인

■ 과정

■ 용모

■ 주증상
1.
2.

■ 부수증상
3.

■ 참고증상

식습관(끼니, 양) :
식욕(맛있어서, 때가되서) :
즐겨드시는 음식:
거부반응 있는 음식:
간식, 야식 :
술 :
물 :
따뜻 or 차가운물 :

소화 :
위장 :
대변 :
소화관 운동성 :

본인호소 체열 :
추위/더위 :
땀 :
손발 :
복부 :

스스로 느끼는 피로도, 과로정도, 기운 :
직업상 특징 :

스트레스 정도 :
몸의 스트레스 :
심장 이상 :
수면시간 :
수면특이사항 :

붓기 :
근골격계 이상 :

소변 :
정력 :
생리 :

■ 참고
복용중인 약/ 병원 검사상 특이사항 / 기저 등

성품/성향

식성/기호
"""


SECTION_ALIASES = {
    "과정": {"과정", "발병과정", "경과과정"},
    "용모": {"용모", "용모체형", "체형", "외형"},
    "주증상": {"주증상", "주소증", "주소", "주호소", "주소증상"},
    "부수증상": {"부수증상", "부증상", "동반증상"},
    "참고증상": {"참고", "참고증상", "참고사항", "기타증상"},
    "변증": {"변증", "병리", "진단", "판단"},
    "치법": {"치법", "치료원칙", "치료방향"},
    "처방구상": {"처방구상", "처방 구상", "방의", "처방의도", "처방의미"},
    "투약": {"투약", "투약내역", "처방", "투여"},
    "경과": {"경과", "결과", "예후", "경과2", "경과 2"},
}

SECTION_WEIGHTS = {
    "주증상": 3.0,
    "부수증상": 2.2,
    "참고증상": 1.8,
    "과정": 1.6,
    "용모": 1.2,
    "투약": 1.4,
    "경과": 1.1,
    "변증": 1.8,
    "치법": 1.8,
    "처방구상": 1.8,
}

QUESTION_BANK = {
    "소화": [
        "식욕은 배고파서 드시는지, 맛있어서 드시는지, 때가 되어 억지로 드시는지 구분해 주세요.",
        "식후 더부룩함, 트림, 역류, 메스꺼움, 명치 답답함 중 무엇이 뚜렷한가요?",
        "식사량이 줄었을 때 증상이 악화되는지, 먹고 나면 편해지는지 확인해 주세요.",
    ],
    "대변": [
        "대변은 묽은 편인지, 굳은 편인지, 잔변감이나 시원치 않음이 있는지 확인해 주세요.",
        "화장실에 자주 가도 잘 나오지 않는지, 혹은 급하게 나오는지 구분해 주세요.",
    ],
    "한열": [
        "추위를 더 타는지 더위를 더 타는지, 손발과 복부의 냉온감이 서로 같은지 확인해 주세요.",
        "갈증이 실제로 있는지, 물을 마시면 따뜻한 물과 찬물 중 어느 쪽이 편한지 확인해 주세요.",
        "땀은 자한, 도한, 식은땀, 열이 오르며 나는 땀 중 어디에 가까운가요?",
    ],
    "기력": [
        "말할 기운, 눕고 싶은 정도, 움직인 뒤 회복 속도, 오후 피로 악화 여부를 확인해 주세요.",
        "과로 후 악화되는지, 휴식하면 바로 회복되는지, 기운이 아래로 빠지는 느낌이 있는지 확인해 주세요.",
    ],
    "정서": [
        "스트레스 후 증상이 뚜렷해지는지, 울화, 억울함, 가슴 답답함, 한숨 중 무엇이 중심인지 확인해 주세요.",
        "수면은 잠들기 어려움, 자주 깸, 꿈 많음, 새벽 각성 중 어디가 문제인지 확인해 주세요.",
        "두근거림, 불안, 가슴 번거로움, 숨참이 동반되는지 확인해 주세요.",
    ],
    "수분": [
        "붓기는 아침 얼굴, 저녁 다리, 전신 무거움 중 어디가 중심인지 확인해 주세요.",
        "소변 횟수, 야간뇨, 시원함, 색, 잔뇨감, 배뇨 곤란을 구분해 주세요.",
    ],
    "근골": [
        "통증은 고정통인지 이동통인지, 차면 심한지 움직이면 풀리는지, 붓기나 저림이 있는지 확인해 주세요.",
    ],
    "여성": [
        "생리 주기, 양, 색, 덩어리, 통증, 냉대하, 출혈 양상을 구체화해 주세요.",
    ],
}

FIELD_GROUPS = {
    "소화": ["식습관", "식욕", "즐겨드시는 음식", "거부반응 있는 음식", "간식", "야식", "소화", "위장", "소화관 운동성"],
    "대변": ["대변"],
    "한열": ["본인호소 체열", "추위", "더위", "땀", "손발", "복부", "물", "따뜻", "차가운물"],
    "기력": ["피로도", "과로", "기운", "직업상 특징", "붓기"],
    "정서": ["스트레스", "심장 이상", "수면시간", "수면특이사항", "성품", "성향"],
    "수분": ["술", "물", "붓기", "소변"],
    "근골": ["근골격계 이상"],
    "여성": ["생리"],
}

STOP_INPUT_VALUES = {"", "없음", "무", "x", "X", "-", "해당없음", "모름"}

NEUTRAL_VALUES = {
    "정상", "보통", "무난", "양호", "괜찮음", "괜찮다", "좋음", "좋다",
    "특이사항 없음", "이상 없음", "문제 없음", "별무", "없음", "무",
}

PHRASE_STOPWORDS = {
    "주증상", "부수증상", "참고증상", "식습관", "식욕", "즐겨드시는", "음식",
    "거부반응", "간식", "야식", "소화", "위장", "대변", "소화관", "운동성",
    "본인호소", "체열", "추위", "더위", "손발", "복부", "피로도", "과로정도",
    "기운", "직업상", "특징", "스트레스", "심장", "이상", "수면시간",
    "수면특이사항", "붓기", "근골격계", "소변", "정력", "생리", "참고",
    "복용중인", "병원", "검사상", "기저", "성품", "성향", "식성", "기호",
    "정상", "보통", "음식", "먹고", "먹음", "좋아하고", "마심", "마시고",
    "있다", "없다", "있는", "없는", "좋다", "좋음", "때가", "돼서", "되서",
    "세끼", "끼니", "양은", "많이", "적게", "조금", "자주", "가끔", "항상",
}

CLINICAL_AXES = [
    {
        "name": "기허/하함",
        "question": "기운이 아래로 빠지는 느낌, 탈항/하수, 말할 힘 없음이 중심인가?",
        "terms": ["기운", "기핍", "피로", "무력", "전신무력", "일시무력", "말할 기운", "눕", "하수", "탈항", "음탈", "자궁하수", "밑이 빠", "꺼져", "강장", "보기", "승거"],
    },
    {
        "name": "심비허/불면",
        "question": "불면, 꿈 많음, 두근거림, 건망, 생각 과다가 중심인가?",
        "terms": ["불면", "잠", "입면", "천면", "다몽", "꿈", "악몽", "두근", "정충", "심계", "건망", "불안", "생각", "신경쇠약"],
    },
    {
        "name": "간울/정서울체",
        "question": "스트레스 뒤 악화, 울화, 억울함, 가슴 답답, 한숨이 중심인가?",
        "terms": ["스트레스", "신경과다", "충격", "속상", "울화", "억울", "화", "짜증", "가슴", "답답", "한숨", "번거", "분노", "우울", "공황"],
    },
    {
        "name": "담음/소화정체",
        "question": "더부룩함, 담음, 메스꺼움, 흉민, 어지럼이 중심인가?",
        "terms": ["더부룩", "그득", "담", "가래", "메스", "구역", "오심", "트림", "명치", "흉민", "어지", "현훈", "체기", "체함", "식체", "식욕부진", "음식부진", "소화불량", "위약", "복명", "헛배"],
    },
    {
        "name": "한증/냉증",
        "question": "추위, 손발/복부 냉감, 따뜻한 물 선호가 뚜렷한가?",
        "terms": ["추위", "차다", "차가", "냉", "시리", "따뜻", "온수", "복부 냉", "손발 차"],
    },
    {
        "name": "열증/상열",
        "question": "열감, 상열, 갈증, 찬물 선호, 번조가 뚜렷한가?",
        "terms": ["열", "상열", "상기", "더위", "갈증", "찬물", "번조", "번거", "심번", "초조", "입마름", "건조", "땀"],
    },
    {
        "name": "혈허/출혈/월경",
        "question": "출혈, 월경 이상, 덩어리 피, 어지럼/혈허 양상이 중심인가?",
        "terms": ["출혈", "자궁출혈", "월경", "월경불순", "생리", "자궁", "피가", "피는", "피를", "검은 피", "붉은 피", "혈", "혈허", "조혈", "혈소판", "덩어리", "어혈", "빈혈", "어지"],
    },
    {
        "name": "대변/복만",
        "question": "변비/설사/잔변감과 복만이 처방 선택의 핵심인가?",
        "terms": ["대변", "변비", "설사", "잔변", "화장실", "복만", "배가", "그득", "묽", "굳"],
    },
    {
        "name": "소변/신기",
        "question": "잔뇨감, 빈뇨, 야간뇨, 정력 저하가 중심인가?",
        "terms": ["소변", "잔뇨", "빈뇨", "야간뇨", "야뇨", "배뇨", "정력", "유정", "소변불리"],
    },
    {
        "name": "근골/통증",
        "question": "통증, 저림, 결림, 허리/어깨/관절 문제가 중심인가?",
        "terms": ["통증", "아프", "저림", "결림", "허리", "어깨", "관절", "근육", "두통", "옆구리", "쑤시"],
    },
]


@dataclass
class CaseRecord:
    path: Path
    folder_prescription: str
    prescription: str
    post_id: str
    author: str = ""
    role: str = ""
    patient_info: str = ""
    symptoms: str = ""
    created_at: str = ""
    url: str = ""
    matched_alias: str = ""
    title_prescription: str = ""
    original: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    index_text: str = ""
    clinical_text: str = ""
    reasoning_text: str = ""
    clinical_phrases: list[str] = field(default_factory=list)
    axis_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class Intake:
    raw: str
    sections: dict[str, str]
    fields: dict[str, str]
    query_text: str
    missing_groups: list[str]
    present_groups: list[str]
    keywords: list[str]
    clinical_phrases: list[str]
    bmi: float | None = None


@dataclass
class CaseHit:
    case: CaseRecord
    score: float
    matched_terms: list[str]


@dataclass
class Recommendation:
    prescription: str
    score: float
    cases: list[CaseHit]
    case_count: int
    matched_terms: list[str]
    meta: Prescription | None = None
    inference_axes: list[str] = field(default_factory=list)
    style_notes: list[str] = field(default_factory=list)
    author_mix: list[str] = field(default_factory=list)
    knowledge_score: float = 0.0


@dataclass
class PrescriptionKnowledge:
    name: str
    source_path: Path | None = None
    composition: list[tuple[str, str]] = field(default_factory=list)
    clinical_application: str = ""
    indications: list[str] = field(default_factory=list)
    case_titles: list[str] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class HerbKnowledge:
    name: str
    source_path: Path | None = None
    summary: list[str] = field(default_factory=list)
    raw_text: str = ""


def _clean_heading(text: str) -> str:
    text = re.sub(r"^[■●◆\-\s]+", "", text).strip()
    text = re.sub(r"[:：\s]+$", "", text).strip()
    text = re.sub(r"\s+", "", text)
    return text


def _canonical_section(heading: str) -> str | None:
    cleaned = _clean_heading(heading)
    for canonical, aliases in SECTION_ALIASES.items():
        if cleaned in aliases:
            return canonical
    for canonical, aliases in SECTION_ALIASES.items():
        if any(cleaned.startswith(alias) for alias in aliases):
            return canonical
    return None


def _clip(text: str, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _normalize_spaces(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def _extract_metadata(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^-\s*([^:：]+)\s*[:：]\s*(.*)$", line)
        if m:
            meta[m.group(1).strip()] = m.group(2).strip()
    return meta


def _extract_original(text: str) -> str:
    m = re.search(r"```(?:text)?\s*\n(.*?)\n```", text, flags=re.S)
    if m:
        return _normalize_spaces(m.group(1))
    marker = "## 원문"
    if marker in text:
        return _normalize_spaces(text.split(marker, 1)[1])
    return _normalize_spaces(text)


def _extract_sections(original: str) -> dict[str, str]:
    sections: dict[str, list[str]] = defaultdict(list)
    current: str | None = None
    title_seen = False

    for raw_line in original.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                sections[current].append("")
            continue

        heading_match = re.match(r"^[■◆]\s*(.+)$", line)
        if heading_match:
            canonical = _canonical_section(heading_match.group(1))
            if canonical:
                current = canonical
                rest = re.sub(r"^[■◆]\s*", "", line).strip()
                rest = re.sub(r"^" + re.escape(heading_match.group(1)).strip() + r"\s*[:：]?\s*", "", rest)
                if rest:
                    sections[current].append(rest)
                continue

        if line.startswith("●") and not title_seen:
            title_seen = True
            sections["제목"].append(line)
            continue

        if current:
            sections[current].append(line)

    return {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip()}


def _extract_title_prescription(original: str, known_names: list[str]) -> str:
    head = "\n".join(original.splitlines()[:8])
    title_lines = [line.strip() for line in head.splitlines() if line.strip().startswith("●")]
    search_area = title_lines[0] if title_lines else head
    for name in sorted(known_names, key=len, reverse=True):
        if name and name in search_area:
            return name
    return ""


def _extract_bmi(fields: dict[str, str], raw: str) -> float | None:
    height = None
    weight = None

    h_match = re.search(r"신장\s*cm\s*[:：]?\s*(\d+(?:\.\d+)?)", raw)
    w_match = re.search(r"체중\s*kg\s*[:：]?\s*(\d+(?:\.\d+)?)", raw)
    if h_match:
        height = float(h_match.group(1))
    if w_match:
        weight = float(w_match.group(1))

    for key, value in fields.items():
        if height is None and "신장" in key:
            m = re.search(r"\d+(?:\.\d+)?", value)
            height = float(m.group(0)) if m else None
        if weight is None and "체중" in key:
            m = re.search(r"\d+(?:\.\d+)?", value)
            weight = float(m.group(0)) if m else None

    if height and weight and height > 0:
        return round(weight / ((height / 100) ** 2), 1)
    return None


def _significant_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r"\d+\.", line):
            continue
        if line in STOP_INPUT_VALUES:
            continue
        lines.append(line)
    return lines


def _extract_keywords(text: str, limit: int = 45) -> list[str]:
    tokens = re.findall(r"[가-힣A-Za-z0-9一-龥陰陽脾胃肝心腎肺血氣津液汗痛寒熱濕痰瘀]{2,}", text)
    skip = {
        "주증상", "부수증상", "참고증상", "식습관", "식욕", "소화", "위장", "대변",
        "소화관", "운동성", "본인호소", "체열", "추위", "더위", "손발", "복부",
        "스트레스", "수면시간", "수면특이사항", "근골격계", "복용중인", "병원",
        "검사상", "특이사항", "성품", "성향", "식성", "기호", "과정", "용모",
        "있다", "없다", "있는", "없는", "것은", "같다", "같은", "하여", "하고",
        "한다", "했다", "된다", "되어", "되며", "보통", "나왔다", "때문에", "전에",
        "후로", "증상은", "병원에서", "제자리로", "못한", "cm", "kg",
    }
    counts = Counter(t for t in tokens if t not in skip and len(t) >= 2)
    return [t for t, _ in counts.most_common(limit)]


def _content_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[가-힣A-Za-z0-9一-龥陰陽脾胃肝心腎肺血氣津液汗痛寒熱濕痰瘀]{2,}", text)
    return [t for t in tokens if t not in PHRASE_STOPWORDS and t not in STOP_INPUT_VALUES]


def _is_neutral_phrase(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip())
    if not compact:
        return True
    if compact in {re.sub(r"\s+", "", v) for v in NEUTRAL_VALUES}:
        return True
    tokens = _content_tokens(text)
    if not tokens:
        return True
    if len(tokens) == 1 and tokens[0] in PHRASE_STOPWORDS:
        return True
    return False


def _clean_phrase(text: str) -> str:
    text = re.sub(r"^[①-⑳㉠-㉭]\s*", "", text.strip())
    text = re.sub(r"^\d+[.)]\s*", "", text)
    text = re.sub(r"^[\-ㆍ·•○●■◆\s]+", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,.;/·ㆍ-")


def _axis_hit_count(text: str) -> int:
    return sum(1 for axis in CLINICAL_AXES for term in axis["terms"] if term in text)


def _axis_score_map(text: str) -> dict[str, float]:
    scores: dict[str, float] = {}
    compact = re.sub(r"\s+", "", text or "")
    for axis in CLINICAL_AXES:
        score = 0.0
        for term in axis["terms"]:
            term_compact = re.sub(r"\s+", "", term)
            if term in text or term_compact in compact:
                score += 1.0
        if score:
            scores[axis["name"]] = score
    return scores


def _axis_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    keys = set(left) | set(right)
    overlap = sum(min(left.get(k, 0.0), right.get(k, 0.0)) for k in keys)
    total = sum(left.values()) + sum(right.values())
    return (2.0 * overlap / total) if total else 0.0


def _split_phrase_line(line: str) -> list[str]:
    line = _clean_phrase(line)
    if not line:
        return []

    field_match = re.match(r"^([^:：]{1,28})\s*[:：]\s*(.*)$", line)
    field_name = ""
    if field_match:
        field_name = field_match.group(1).strip()
        value = field_match.group(2).strip()
        if value in STOP_INPUT_VALUES or value in NEUTRAL_VALUES:
            return []
        line = f"{field_name}: {value}" if field_name else value

    parts = re.split(r"[,\n;/]+|(?:\s+[ㆍ·]\s+)", line)
    phrases: list[str] = []
    for part in parts:
        phrase = _clean_phrase(part)
        if not phrase or _is_neutral_phrase(phrase):
            continue
        if len(phrase) > 42:
            # Long narrative lines still matter, but evidence works better when
            # shown as compact symptom chunks.
            short_parts = re.split(r"\s*(?:하고|하며|면서|이고|이며|인데|으나|거나)\s*", phrase)
            for short in short_parts:
                short = _clean_phrase(short)
                if 2 <= len(short) <= 42 and not _is_neutral_phrase(short):
                    phrases.append(short)
            continue
        if len(phrase) >= 2:
            phrases.append(phrase)
    return phrases


def _extract_clinical_phrases_from_sections(sections: dict[str, str], fields: dict[str, str], limit: int = 36) -> list[str]:
    phrases: list[str] = []
    weighted_sections = [
        "주증상", "주증상", "주증상",
        "부수증상", "부수증상",
        "참고증상", "과정", "용모", "기타",
    ]
    for section in weighted_sections:
        for line in sections.get(section, "").splitlines():
            for phrase in _split_phrase_line(line):
                if section in {"용모", "기타"} and _axis_hit_count(phrase) == 0:
                    continue
                phrases.append(phrase)

    for key, value in fields.items():
        value = value.strip()
        if value in STOP_INPUT_VALUES or value in NEUTRAL_VALUES:
            continue
        if any(axis_key in key for axis_key in ("식욕", "소화", "위장", "대변", "체열", "추위", "더위", "땀", "손발", "복부", "피로", "기운", "스트레스", "심장", "수면", "붓기", "근골격", "소변", "정력", "생리")):
            phrases.extend(_split_phrase_line(f"{key}: {value}"))

    scored: list[tuple[int, int, str]] = []
    seen = set()
    for phrase in phrases:
        normalized = re.sub(r"\s+", "", phrase)
        if normalized in seen:
            continue
        seen.add(normalized)
        tokens = _content_tokens(phrase)
        axis_hits = _axis_hit_count(phrase)
        score = axis_hits * 3 + min(len(tokens), 5)
        if ":" in phrase:
            score += 1
        scored.append((score, len(phrase), phrase))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [phrase for _, _, phrase in scored[:limit]]


def _phrase_matches_text(phrase: str, text: str) -> bool:
    phrase_compact = re.sub(r"\s+", "", phrase)
    text_compact = re.sub(r"\s+", "", text)
    if len(phrase_compact) >= 4 and phrase_compact in text_compact:
        return True
    tokens = _content_tokens(phrase)
    if not tokens:
        return False
    hits = sum(1 for token in tokens if token in text)
    if len(tokens) == 1:
        return hits == 1 and len(tokens[0]) >= 3
    return hits >= 2 or hits / len(tokens) >= 0.6


def _phrase_match_score(phrases: list[str], text: str) -> tuple[float, list[str]]:
    if not phrases:
        return 0.0, []
    matched = [phrase for phrase in phrases if _phrase_matches_text(phrase, text)]
    return len(matched) / max(len(phrases), 1), matched


def _format_terms(terms: Iterable[str], limit: int = 12) -> str:
    unique = []
    seen = set()
    for term in terms:
        term = _clip(term, 34)
        dedupe_key = re.sub(r"\s+", "", term.split(":", 1)[-1])
        if term and dedupe_key not in seen:
            unique.append(term)
            seen.add(dedupe_key)
    if not unique:
        return "뚜렷한 일치어 없음"
    return ", ".join(unique[:limit])


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig", errors="ignore")


def _clean_markdown_heading(text: str) -> str:
    text = re.sub(r"\s*\{#.+?\}\s*$", "", text or "")
    text = re.sub(r"[*_`#\[\]]+", "", text)
    return text.strip()


def _markdown_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = defaultdict(list)
    current = "개요"
    for raw in (text or "").splitlines():
        heading = re.match(r"^(#{1,5})\s+(.+?)\s*$", raw.strip())
        if heading:
            current = _clean_markdown_heading(heading.group(2))
            continue
        sections[current].append(raw.rstrip())
    return {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip()}


def _extract_hashtags(text: str) -> list[str]:
    tags = []
    for tag in re.findall(r"#([^\s#]+)", text or ""):
        tag = tag.strip(".,;:()[]{}")
        if tag:
            tags.append(tag)
    return list(dict.fromkeys(tags))


def _extract_link_titles(text: str, limit: int = 40) -> list[str]:
    titles = [m.group(1).strip() for m in re.finditer(r"\[([^\]]{2,220})\]\([^)]+\)", text or "")]
    return list(dict.fromkeys(titles))[:limit]


def _normalize_herb_name(name: str) -> str:
    name = re.sub(r"\([^)]*\)|（[^）]*）|\[[^\]]*\]", "", name or "")
    name = re.sub(r"[0-9.]+g?", "", name, flags=re.I)
    name = re.sub(r"\s+", "", name)
    name = name.strip("·ㆍ,.;:/|+-")
    aliases = {
        "대조": "대추",
        "감초자": "감초",
        "감초초": "감초",
        "백복령": "복령",
        "적복령": "복령",
        "백작": "백작약",
        "작약": "백작약",
    }
    return aliases.get(name, name)


def _parse_composition_table(text: str) -> list[tuple[str, str]]:
    composition: list[tuple[str, str]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if any("약재" in cell or "용량" in cell for cell in cells):
            continue
        if all(re.fullmatch(r":?-+:?", cell) for cell in cells if cell):
            continue
        dose, herbs_cell = cells[0], cells[1]
        if not herbs_cell or re.fullmatch(r":?-+:?", herbs_cell):
            continue
        for herb in re.split(r"\s+", herbs_cell):
            herb = _normalize_herb_name(herb)
            if herb:
                composition.append((herb, dose))
    return list(dict.fromkeys(composition))


def _extract_bullets(text: str, limit: int = 80) -> list[str]:
    bullets = []
    seen = set()
    for raw in (text or "").splitlines():
        line = re.sub(r"^\s*[-*+]\s*", "", raw).strip()
        if not line or len(line) < 8:
            continue
        key = re.sub(r"\s+", "", line)
        if key in seen:
            continue
        seen.add(key)
        bullets.append(line)
        if len(bullets) >= limit:
            break
    return bullets


def _is_style_author(author: str) -> bool:
    return any(name in (author or "") for name in STYLE_AUTHORS)


def _case_clinical_text(case: CaseRecord) -> str:
    sections = case.sections
    chunks = [
        case.patient_info,
        case.symptoms,
        sections.get("과정", ""),
        sections.get("용모", ""),
        sections.get("주증상", ""),
        sections.get("부수증상", ""),
        sections.get("참고증상", ""),
    ]
    return "\n".join(chunk for chunk in chunks if chunk)


def _case_reasoning_text(case: CaseRecord) -> str:
    sections = case.sections
    chunks = [
        sections.get("변증", ""),
        sections.get("치법", ""),
        sections.get("처방구상", ""),
        sections.get("투약", ""),
        sections.get("경과", ""),
    ]
    return "\n".join(chunk for chunk in chunks if chunk)


def _extract_decision_snippets(text: str, limit: int = 3) -> list[str]:
    snippets = []
    for raw in (text or "").splitlines():
        line = _clean_phrase(raw)
        if not line:
            continue
        if any(marker in line for marker in ("목표로", "투약", "처방", "가감", "더하여", "복용", "경과", "호전")):
            snippets.append(_clip(line, 140))
        if len(snippets) >= limit:
            break
    return snippets


class FlowchartEngine:
    def __init__(
        self,
        case_dir: Path | str = DEFAULT_CASE_DIR,
        db_path: Path | str = DEFAULT_DB_PATH,
    ) -> None:
        self.case_dir = Path(case_dir)
        self.db_path = Path(db_path)
        self.db = PrescriptionDB(str(self.db_path))
        self._prescriptions = self.db.get_all_prescriptions()
        self._prescription_by_name = {p.name: p for p in self._prescriptions}
        self._prescription_by_id = {p.id: p for p in self._prescriptions}
        self._known_names = self._collect_known_names()
        self.cases: list[CaseRecord] = []
        self._case_matrix = None
        self._vectorizer: TfidfVectorizer | None = None
        self._prescription_file_index: list[Path] | None = None
        self._herb_file_index: dict[str, Path] | None = None
        self._prescription_knowledge_cache: dict[str, PrescriptionKnowledge] = {}
        self._herb_knowledge_cache: dict[str, HerbKnowledge] = {}
        self._loaded = False

    @property
    def prescription_names(self) -> list[str]:
        self.ensure_loaded()
        names = {case.prescription for case in self.cases}
        names.update(p.name for p in self._prescriptions)
        return sorted(names)

    def _collect_known_names(self) -> list[str]:
        names = {p.name for p in self._prescriptions}
        names.update(p.id for p in self._prescriptions)
        if self.case_dir.exists():
            names.update(p.name for p in self.case_dir.iterdir() if p.is_dir())
        return sorted((n for n in names if n), key=len, reverse=True)

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self.cases = self._load_cases()
        docs = [case.index_text for case in self.cases]
        if not docs:
            raise RuntimeError(f"치험례 파일을 찾지 못했습니다: {self.case_dir}")
        self._vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            min_df=2,
            max_features=65000,
            sublinear_tf=True,
            norm="l2",
        )
        self._case_matrix = self._vectorizer.fit_transform(docs)
        self._loaded = True

    def _load_cases(self) -> list[CaseRecord]:
        if not self.case_dir.exists():
            return []

        cases: list[CaseRecord] = []
        seen: set[tuple[str, str]] = set()
        for path in sorted(self.case_dir.glob("*/post_*.md")):
            record = self._parse_case_file(path)
            if not record:
                continue
            dedupe_key = (record.url or record.post_id or str(record.path), record.prescription)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            cases.append(record)
        return cases

    def _parse_case_file(self, path: Path) -> CaseRecord | None:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8-sig", errors="ignore")

        original = _extract_original(text)
        if not original:
            return None

        meta = _extract_metadata(text)
        sections = _extract_sections(original)
        folder = path.parent.name
        title_prescription = _extract_title_prescription(original, self._known_names)

        prescription = title_prescription or meta.get("처방매칭") or folder
        if title_prescription and folder not in title_prescription and title_prescription not in folder:
            # The exporter can duplicate a modified formula under a base formula
            # folder because of substring matching.  The title line is closer to
            # the actual 투약 case, so we use it for scoring.
            prescription = title_prescription

        post_id = path.stem.replace("post_", "")
        record = CaseRecord(
            path=path,
            folder_prescription=folder,
            prescription=prescription,
            post_id=post_id,
            author=meta.get("작성자", ""),
            role=meta.get("역할표시", ""),
            patient_info=meta.get("환자정보", ""),
            symptoms=meta.get("주증상", ""),
            created_at=meta.get("작성시각", ""),
            url=meta.get("게시글", ""),
            matched_alias=meta.get("처방매칭", ""),
            title_prescription=title_prescription,
            original=original,
            sections=sections,
        )
        record.clinical_text = _case_clinical_text(record)
        record.reasoning_text = _case_reasoning_text(record)
        record.clinical_phrases = _extract_clinical_phrases_from_sections(sections, {}, limit=40)
        record.axis_scores = _axis_score_map(record.clinical_text)
        record.index_text = self._build_case_index_text(record)
        return record

    def _build_case_index_text(self, case: CaseRecord) -> str:
        chunks = [
            case.prescription,
            case.patient_info,
            case.symptoms,
            case.title_prescription,
        ]
        for section, weight in SECTION_WEIGHTS.items():
            value = case.sections.get(section, "")
            if value:
                chunks.extend([value] * int(math.ceil(weight)))
        chunks.append(case.original[:3500])
        return "\n".join(chunks)

    def parse_intake(self, raw: str) -> Intake:
        raw = _normalize_spaces(raw or "")
        sections: dict[str, list[str]] = defaultdict(list)
        fields: dict[str, str] = {}
        current: str | None = None

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                if current:
                    sections[current].append("")
                continue

            section_match = re.match(r"^■\s*([^:：]+)(?:\s*[:：]\s*(.*))?$", stripped)
            if section_match:
                heading = section_match.group(1).strip()
                value = (section_match.group(2) or "").strip()
                canonical = _canonical_section(heading) or heading
                current = canonical
                if value:
                    fields[heading] = value
                    sections[current].append(value)
                continue

            field_match = re.match(r"^([^:：]{1,40})\s*[:：]\s*(.*)$", stripped)
            if field_match:
                key = field_match.group(1).strip()
                value = field_match.group(2).strip()
                fields[key] = value
                if value and value not in STOP_INPUT_VALUES:
                    sections[current or "기타"].append(f"{key}: {value}")
                continue

            if current:
                sections[current].append(stripped)
            else:
                sections["기타"].append(stripped)

        normalized_sections = {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip()}
        query_parts: list[str] = []
        for section in ("주증상", "부수증상", "참고증상", "과정", "용모", "기타"):
            value = normalized_sections.get(section, "")
            if value:
                weight = int(math.ceil(SECTION_WEIGHTS.get(section, 1.0)))
                query_parts.extend([value] * weight)

        filled_fields = {
            key: value for key, value in fields.items()
            if value.strip() not in STOP_INPUT_VALUES
        }
        if filled_fields:
            query_parts.append("\n".join(f"{k}: {v}" for k, v in filled_fields.items()))

        query_text = "\n".join(query_parts).strip() or raw
        present_groups = []
        missing_groups = []
        for group, keys in FIELD_GROUPS.items():
            has_value = any(
                any(key in field_key for key in keys) and value.strip() not in STOP_INPUT_VALUES
                for field_key, value in fields.items()
            )
            if has_value:
                present_groups.append(group)
            else:
                missing_groups.append(group)

        clinical_phrases = _extract_clinical_phrases_from_sections(normalized_sections, fields)

        return Intake(
            raw=raw,
            sections=normalized_sections,
            fields=fields,
            query_text=query_text,
            missing_groups=missing_groups,
            present_groups=present_groups,
            keywords=clinical_phrases or _extract_keywords(query_text),
            clinical_phrases=clinical_phrases,
            bmi=_extract_bmi(fields, raw),
        )

    def _style_case_score(
        self,
        intake: Intake,
        intake_axes: dict[str, float],
        case: CaseRecord,
        text_similarity: float,
    ) -> tuple[float, list[str]]:
        phrase_score, matched = _phrase_match_score(intake.clinical_phrases, case.clinical_text)
        axis_score = _axis_similarity(intake_axes, case.axis_scores)
        reasoning_axes = _axis_score_map(case.reasoning_text)
        reasoning_score = _axis_similarity(intake_axes, reasoning_axes)

        chief_score = 0.0
        chief_text = case.sections.get("주증상", "")
        if intake.sections.get("주증상"):
            chief_score, _ = _phrase_match_score(
                _extract_clinical_phrases_from_sections({"주증상": intake.sections["주증상"]}, {}, limit=12),
                chief_text,
            )

        # The authors' cases often decide by a symptom constellation, then confirm
        # through 투약/경과.  Text similarity is kept small so it cannot dominate.
        score = (
            axis_score * 0.36
            + phrase_score * 0.25
            + chief_score * 0.14
            + reasoning_score * 0.13
            + min(text_similarity, 0.45) * 0.12
        )
        if matched:
            score += min(len(matched), 5) * 0.012
        return score, matched

    def _prescription_profile_score(self, intake_axes: dict[str, float], hits: list[CaseHit]) -> float:
        if not hits:
            return 0.0
        profile: dict[str, float] = defaultdict(float)
        for hit in hits:
            for axis, value in hit.case.axis_scores.items():
                profile[axis] += value * hit.score
        return _axis_similarity(intake_axes, profile)

    def _inference_axes_for_hits(self, intake_axes: dict[str, float], hits: list[CaseHit]) -> list[str]:
        axis_weights: Counter[str] = Counter()
        for hit in hits:
            for axis, value in hit.case.axis_scores.items():
                if axis in intake_axes:
                    axis_weights[axis] += value * max(hit.score, 0.01)
        if not axis_weights:
            for hit in hits:
                for axis, value in hit.case.axis_scores.items():
                    axis_weights[axis] += value * max(hit.score, 0.01)
        return [axis for axis, _ in axis_weights.most_common(4)]

    def _style_notes_for_hits(self, hits: list[CaseHit], intake: Intake | None = None) -> list[str]:
        notes: list[str] = []
        phrases = intake.clinical_phrases if intake else []
        axis_names = set(_axis_score_map(intake.query_text).keys()) if intake else set()
        for hit in hits[:5]:
            case = hit.case
            matched = hit.matched_terms[:4]
            chief = _clip(case.sections.get("주증상") or case.symptoms, 90)
            medication = self._best_section_snippet(
                case.sections.get("투약", ""),
                phrases,
                axis_names,
                ("목표로", "더하여", "투약", "처방"),
            )
            course = self._best_section_snippet(
                case.sections.get("경과", ""),
                phrases,
                axis_names,
                ("호전", "없어", "기운", "소실", "좋아", "나았다", "경감"),
            )
            pieces = [f"`{case.post_id}` {case.author or '작성자 미상'}"]
            if matched:
                pieces.append(f"{_format_terms(matched, 4)}")
            elif chief:
                pieces.append(chief)
            if medication:
                pieces.append(f"투약: {_clip(medication, 110)}")
            if course:
                pieces.append(f"경과: {_clip(course, 110)}")
            note = " / ".join(piece for piece in pieces if piece)
            if note not in notes and len(pieces) >= 2:
                notes.append(note)
            if len(notes) >= 4:
                return notes

        for hit in hits[:5]:
            for snippet in _extract_decision_snippets(hit.case.reasoning_text, limit=2):
                if snippet not in notes:
                    notes.append(snippet)
                if len(notes) >= 4:
                    return notes
        return notes

    def _best_section_snippet(
        self,
        text: str,
        phrases: list[str],
        axis_names: set[str],
        preferred_markers: tuple[str, ...],
    ) -> str:
        candidates = _significant_lines(text)
        if not candidates:
            return ""
        axis_terms = []
        for axis in CLINICAL_AXES:
            if axis["name"] in axis_names:
                axis_terms.extend(axis["terms"])

        scored = []
        for idx, line in enumerate(candidates):
            clean = _clean_phrase(line)
            if not clean:
                continue
            score = 0
            score += sum(3 for marker in preferred_markers if marker in clean)
            score += sum(2 for phrase in phrases[:12] if _phrase_matches_text(phrase, clean))
            score += sum(1 for term in axis_terms if term and term in clean)
            if re.search(r"^\d+[.)]", line):
                score += 1
            if score:
                scored.append((score, -idx, clean))
        if scored:
            scored.sort(reverse=True)
            return scored[0][2]
        if any(marker in candidates[0] for marker in preferred_markers):
            return _clean_phrase(candidates[0])
        return ""

    def _prescription_files(self) -> list[Path]:
        if self._prescription_file_index is None:
            files: list[Path] = []
            for doc_dir in PRESCRIPTION_DOC_DIRS:
                if doc_dir.exists():
                    files.extend(path for path in doc_dir.rglob("*.md") if path.name != ".md")
            self._prescription_file_index = sorted(files)
        return self._prescription_file_index

    def _herb_files(self) -> dict[str, Path]:
        if self._herb_file_index is None:
            index: dict[str, Path] = {}
            if HERB_DOC_DIR.exists():
                for path in sorted(HERB_DOC_DIR.glob("*.md")):
                    stem = _normalize_herb_name(path.stem)
                    if stem:
                        index.setdefault(stem, path)
                        index.setdefault(path.stem, path)
            self._herb_file_index = index
        return self._herb_file_index

    def _find_prescription_file(self, name: str) -> Path | None:
        if not name:
            return None
        candidates = []
        compact_name = re.sub(r"\s+", "", name)
        for path in self._prescription_files():
            stem = path.stem
            compact_stem = re.sub(r"\s+", "", stem)
            if compact_stem == compact_name:
                rank = 0
            elif compact_stem.endswith(compact_name):
                rank = 1
            elif compact_name in compact_stem:
                rank = 2
            else:
                continue
            candidates.append((rank, len(stem), path))
        if not candidates:
            meta = self.get_prescription_meta(name)
            if meta and meta.source_file:
                path = Path(meta.source_file)
                if not path.is_absolute():
                    path = BASE_DIR / path
                if path.exists():
                    return path
            return None
        candidates.sort(key=lambda item: (item[0], item[1], str(item[2])))
        return candidates[0][2]

    def _load_prescription_knowledge(self, name: str) -> PrescriptionKnowledge:
        if name in self._prescription_knowledge_cache:
            return self._prescription_knowledge_cache[name]

        source_path = self._find_prescription_file(name)
        if not source_path:
            knowledge = PrescriptionKnowledge(name=name)
            self._prescription_knowledge_cache[name] = knowledge
            return knowledge

        raw_text = _read_text(source_path)
        sections = _markdown_sections(raw_text)
        composition = _parse_composition_table(sections.get("구성", ""))
        clinical_application = sections.get("임상응용", "") or sections.get("임상 응용", "")
        indications = _extract_hashtags(sections.get("적용증", ""))
        case_titles = _extract_link_titles(sections.get("치험례", ""))
        knowledge = PrescriptionKnowledge(
            name=name,
            source_path=source_path,
            composition=composition,
            clinical_application=clinical_application,
            indications=indications,
            case_titles=case_titles,
            raw_text=raw_text,
        )
        self._prescription_knowledge_cache[name] = knowledge
        return knowledge

    def _find_herb_file(self, herb: str) -> Path | None:
        normalized = _normalize_herb_name(herb)
        if not normalized:
            return None
        index = self._herb_files()
        if normalized in index:
            return index[normalized]
        contains = [(abs(len(stem) - len(normalized)), path) for stem, path in index.items() if normalized in stem or stem in normalized]
        if contains:
            contains.sort(key=lambda item: (item[0], str(item[1])))
            return contains[0][1]
        return None

    def _load_herb_knowledge(self, herb: str) -> HerbKnowledge:
        normalized = _normalize_herb_name(herb)
        if normalized in self._herb_knowledge_cache:
            return self._herb_knowledge_cache[normalized]
        source_path = self._find_herb_file(normalized)
        if not source_path:
            knowledge = HerbKnowledge(name=normalized)
            self._herb_knowledge_cache[normalized] = knowledge
            return knowledge
        raw_text = _read_text(source_path)
        sections = _markdown_sections(raw_text)
        summary = _extract_bullets(sections.get("기능 요약", "") or raw_text, limit=120)
        knowledge = HerbKnowledge(name=normalized, source_path=source_path, summary=summary, raw_text=raw_text)
        self._herb_knowledge_cache[normalized] = knowledge
        return knowledge

    def _composition_for_rec(self, rec: Recommendation) -> list[tuple[str, str]]:
        knowledge = self._load_prescription_knowledge(rec.prescription)
        if knowledge.composition:
            return knowledge.composition
        if rec.meta and rec.meta.herbs_detail:
            return [(_normalize_herb_name(herb), str(dose)) for herb, dose in rec.meta.herbs_detail.items()]
        if rec.meta and rec.meta.herbs:
            return [(_normalize_herb_name(herb), "") for herb in rec.meta.herbs]
        return []

    def _prescription_knowledge_score(self, intake: Intake, intake_axes: dict[str, float], name: str) -> float:
        knowledge = self._load_prescription_knowledge(name)
        meta = self.get_prescription_meta(name)
        chunks = [
            knowledge.clinical_application,
            " ".join(knowledge.indications),
            " ".join(knowledge.case_titles[:30]),
        ]
        if meta:
            chunks.extend([meta.description, " ".join(meta.indications), " ".join(meta.herbs)])
        text = "\n".join(chunk for chunk in chunks if chunk)
        if not text:
            return 0.0
        axis_score = _axis_similarity(intake_axes, _axis_score_map(text))
        phrase_score, _ = _phrase_match_score(intake.clinical_phrases, text)

        herb_chunks = []
        rec = Recommendation(name, 0.0, [], 0, [], meta=meta)
        for herb, _dose in self._composition_for_rec(rec)[:14]:
            herb_info = self._load_herb_knowledge(herb)
            herb_chunks.extend(herb_info.summary[:10])
        herb_text = "\n".join(herb_chunks)
        herb_axis_score = _axis_similarity(intake_axes, _axis_score_map(herb_text)) if herb_text else 0.0
        herb_phrase_score, _ = _phrase_match_score(intake.clinical_phrases, herb_text) if herb_text else (0.0, [])
        return axis_score * 0.42 + phrase_score * 0.28 + herb_axis_score * 0.20 + herb_phrase_score * 0.10

    def _author_mix_for_hits(self, hits: list[CaseHit]) -> list[str]:
        counts = Counter(hit.case.author for hit in hits if hit.case.author)
        return [f"{author} {count}례" for author, count in counts.most_common()]

    def recommend(self, raw_intake: str, top_k: int = 8) -> tuple[Intake, list[Recommendation]]:
        self.ensure_loaded()
        intake = self.parse_intake(raw_intake)
        if not intake.query_text.strip():
            return intake, []

        assert self._vectorizer is not None
        assert self._case_matrix is not None
        query_vec = self._vectorizer.transform([intake.query_text])
        sims = cosine_similarity(query_vec, self._case_matrix).ravel()
        if sims.size == 0:
            return intake, []

        intake_axes = _axis_score_map(intake.query_text)
        grouped: dict[str, list[CaseHit]] = defaultdict(list)
        for idx, case in enumerate(self.cases):
            if not _is_style_author(case.author):
                continue
            score, matched = self._style_case_score(intake, intake_axes, case, float(sims[idx]))
            if score <= 0.03:
                continue
            grouped[case.prescription].append(CaseHit(case=case, score=score, matched_terms=matched))

        preliminary: list[tuple[float, str, list[CaseHit], float, float, float, float, float]] = []
        total_counts = Counter(case.prescription for case in self.cases if _is_style_author(case.author))
        for name, hits in grouped.items():
            hits.sort(key=lambda h: h.score, reverse=True)
            top_hits = hits[:8]
            max_score = top_hits[0].score
            mean_top = sum(h.score for h in top_hits[:5]) / min(len(top_hits), 5)
            profile_score = self._prescription_profile_score(intake_axes, top_hits)
            support = min(len(hits) / 12.0, 1.0) * 0.05
            phrase_bonus = min(len({t for hit in top_hits for t in hit.matched_terms}) / 10.0, 1.0) * 0.08
            base_score = max_score * 0.42 + mean_top * 0.28 + profile_score * 0.17 + support + phrase_bonus
            preliminary.append((base_score, name, top_hits, max_score, mean_top, profile_score, support, phrase_bonus))

        preliminary.sort(key=lambda item: item[0], reverse=True)
        candidate_limit = max(top_k * 6, 35)
        recommendations: list[Recommendation] = []
        for _base_score, name, top_hits, max_score, mean_top, profile_score, support, phrase_bonus in preliminary[:candidate_limit]:
            knowledge_score = self._prescription_knowledge_score(intake, intake_axes, name)
            score = max_score * 0.38 + mean_top * 0.25 + profile_score * 0.16 + knowledge_score * 0.13 + support + phrase_bonus
            recommendations.append(
                Recommendation(
                    prescription=name,
                    score=score,
                    cases=top_hits,
                    case_count=total_counts[name],
                    matched_terms=self._aggregate_terms(top_hits),
                    meta=self.get_prescription_meta(name),
                    inference_axes=self._inference_axes_for_hits(intake_axes, top_hits),
                    style_notes=self._style_notes_for_hits(top_hits, intake),
                    author_mix=self._author_mix_for_hits(top_hits),
                    knowledge_score=knowledge_score,
                )
            )

        recommendations.sort(key=lambda r: r.score, reverse=True)
        return intake, recommendations[:top_k]

    def get_prescription_meta(self, name: str) -> Prescription | None:
        if name in self._prescription_by_name:
            return self._prescription_by_name[name]
        if name in self._prescription_by_id:
            return self._prescription_by_id[name]
        matches = [p for p in self._prescriptions if name in p.name or p.name in name]
        return matches[0] if matches else None

    def find_prescription_name(self, query: str) -> str | None:
        query = (query or "").strip()
        if not query:
            return None
        self.ensure_loaded()
        names = self.prescription_names
        if query in names:
            return query
        exact = [name for name in names if query == name]
        if exact:
            return exact[0]
        contains = [name for name in names if query in name or name in query]
        if contains:
            return sorted(contains, key=lambda n: (abs(len(n) - len(query)), len(n)))[0]
        return None

    def _matched_terms(self, keywords: list[str], text: str) -> list[str]:
        return [phrase for phrase in keywords if phrase and _phrase_matches_text(phrase, text)][:15]

    def _matched_indications(self, intake: Intake, indications: list[str]) -> list[str]:
        if not indications:
            return []
        intake_axes = set(_axis_score_map(intake.query_text))
        intake_tokens = set(_content_tokens(intake.query_text))
        scored = []
        for idx, indication in enumerate(indications):
            axis_hits = set(_axis_score_map(indication))
            token_hits = set(_content_tokens(indication)) & intake_tokens
            phrase_hits = sum(1 for phrase in intake.clinical_phrases[:18] if indication in phrase or _phrase_matches_text(phrase, indication))
            score = len(axis_hits & intake_axes) * 4 + len(token_hits) * 2 + phrase_hits * 3
            if score:
                scored.append((score, -idx, indication))
        if not scored:
            return indications[:12]
        scored.sort(reverse=True)
        return [indication for _score, _idx, indication in scored[:18]]

    def _aggregate_terms(self, hits: list[CaseHit]) -> list[str]:
        counts = Counter(term for hit in hits for term in hit.matched_terms)
        return [term for term, _ in counts.most_common(20)]

    def format_recommendations(self, raw_intake: str, top_k: int = 8) -> tuple[str, str, str, str, str]:
        intake, recommendations = self.recommend(raw_intake, top_k=top_k)
        summary = self._format_summary(intake, recommendations)
        questions = self._format_questions(intake, recommendations)
        evidence = self._format_evidence(recommendations)
        detail = self._format_detail_page(intake, recommendations)
        state = recommendations[0].prescription if recommendations else ""
        return summary, questions, evidence, detail, state

    def _format_summary(self, intake: Intake, recommendations: list[Recommendation]) -> str:
        if not recommendations:
            return "문진표 내용이 비어 있거나 매칭되는 치험례가 없습니다. 주증상과 부수증상을 조금 더 적어 주세요."

        lines = [
            "## 처방 후보 요약",
            "",
            "> 이종대, 이윤호(98) since2002 치험례에서 반복되는 증상 판단 흐름을 기준으로 추론합니다. 최종 판단은 직접 문진, 진찰, 검사 정보와 함께 해주세요.",
            "",
        ]
        if intake.bmi:
            lines.append(f"- 계산된 BMI: **{intake.bmi}**")
        if intake.clinical_phrases:
            lines.append(f"- 문진표 핵심 증상축: {_format_terms(intake.clinical_phrases, 8)}")
        lines.append("")
        lines.append("| 순위 | 처방 | 적합도 | 두 작성자식 판단축 | 대표 근거 |")
        lines.append("|---:|---|---:|---|---:|")
        for idx, rec in enumerate(recommendations, 1):
            axes = _format_terms(rec.inference_axes, 4)
            evidence = _format_terms(rec.matched_terms, 3)
            lines.append(
                f"| {idx} | **{rec.prescription}** | {rec.score:.1%} | "
                f"{axes} | {evidence} · {len(rec.cases)} / 전체 {rec.case_count} |"
            )

        top = recommendations[0]
        lines.extend(["", "## 1순위 판단 흐름", ""])
        lines.append(f"**{top.prescription}** 쪽으로 먼저 보는 이유는 두 작성자의 치험례에서 다음 판단 흐름이 가장 가깝기 때문입니다.")
        for reason in self._top_reason_lines(top):
            lines.append(f"- {reason}")
        if top.author_mix:
            lines.append(f"- 작성자 근거 분포: {_format_terms(top.author_mix, 4)}")
        if top.style_notes:
            lines.append(f"- 투약/경과에서 잡힌 판단 단서: {_format_terms(top.style_notes, 3)}")
        if top.knowledge_score:
            lines.append(f"- 처방/약재 문헌 보강도: {top.knowledge_score:.1%}")

        meta = top.meta
        knowledge = self._load_prescription_knowledge(top.prescription)
        if knowledge.clinical_application:
            lines.append(f"- 처방 문헌 임상응용: {_clip(knowledge.clinical_application, 220)}")
        if knowledge.indications:
            matched_indications = self._matched_indications(intake, knowledge.indications)
            lines.append(f"- 처방 문헌 적용증: {_format_terms(matched_indications or knowledge.indications, 12)}")
        if meta:
            if meta.description:
                lines.append(f"- 처방 설명: {_clip(meta.description, 260)}")
            if meta.indications:
                lines.append(f"- DB 적응증 태그: {_format_terms(meta.indications, 12)}")
            if meta.herbs:
                lines.append(f"- 구성 약재 관점: {_format_terms(meta.herbs, 18)}")
                herb_note = self._herb_direction_note(meta.herbs)
                if herb_note:
                    lines.append(f"- 약재 방향성: {herb_note}")

        lines.extend(["", "## 플로우차트", ""])
        lines.extend(self._flowchart_lines(intake, recommendations))
        return "\n".join(lines)

    def _top_reason_lines(self, rec: Recommendation) -> list[str]:
        reasons = []
        if rec.inference_axes:
            reasons.append(f"먼저 본 변증축: {_format_terms(rec.inference_axes, 4)}")
        if rec.matched_terms:
            reasons.append(f"문진표의 증상 구절이 해당 처방 치험례의 주증/참고증 흐름과 겹칩니다: {_format_terms(rec.matched_terms, 6)}")
        for hit in rec.cases[:3]:
            case = hit.case
            summary = case.symptoms or case.sections.get("주증상", "")
            reasons.append(
                f"{case.author or '작성자 미상'} 치험례 `{case.post_id}`에서 비슷한 증상군을 같은 처방 판단으로 연결했습니다: {_clip(summary, 170)}"
            )
        return reasons or ["두 작성자의 상위 치험례 프로필과 가장 가깝습니다."]

    def _herb_direction_note(self, herbs: list[str]) -> str:
        # Keep this intentionally plain Korean.  The bundled herb dictionary is
        # useful but some source comments are mojibake in this repo.
        warmers = {"부자", "건강", "계지", "육계", "오수유", "세신", "마황", "생강"}
        qi_tonics = {"인삼", "황기", "백출", "감초", "대조", "산약"}
        blood_yin = {"당귀", "숙지황", "백작약", "맥문동", "천문동", "구기자", "산수유"}
        movers = {"향부자", "시호", "진피", "청피", "지각", "목향", "후박", "사인", "소엽"}
        damp_phlegm = {"반하", "복령", "창출", "택사", "저령", "의이인", "남성", "지실"}
        heat_clear = {"황련", "황금", "황백", "치자", "석고", "지모", "생지황", "목단피"}
        groups = []
        herbs_set = set(herbs)
        for label, group in [
            ("보기/승거", qi_tonics),
            ("보혈/보음", blood_yin),
            ("온양/산한", warmers),
            ("이기/소간", movers),
            ("화담/이수", damp_phlegm),
            ("청열", heat_clear),
        ]:
            overlap = sorted(herbs_set & group)
            if overlap:
                groups.append(f"{label}({', '.join(overlap[:4])})")
        return " + ".join(groups[:4])

    def _axis_hits_for_text(self, text: str) -> dict[str, list[str]]:
        hits: dict[str, list[str]] = {}
        compact = re.sub(r"\s+", "", text)
        for axis in CLINICAL_AXES:
            terms = []
            for term in axis["terms"]:
                if term in text or re.sub(r"\s+", "", term) in compact:
                    terms.append(term)
            if terms:
                hits[axis["name"]] = list(dict.fromkeys(terms))
        return hits

    def _axis_profile_for_rec(self, rec: Recommendation, intake: Intake, peers: list[Recommendation]) -> list[tuple[str, int, list[str]]]:
        rec_text = self._recommendation_text(rec)
        rec_hits = self._axis_hits_for_text(rec_text)
        intake_hits = self._axis_hits_for_text(intake.query_text)
        peer_hits = [self._axis_hits_for_text(self._recommendation_text(peer)) for peer in peers if peer.prescription != rec.prescription]

        scored = []
        for axis in CLINICAL_AXES:
            name = axis["name"]
            terms = rec_hits.get(name, [])
            if not terms:
                continue
            peer_strength = sum(len(hit.get(name, [])) for hit in peer_hits) / max(len(peer_hits), 1)
            score = len(terms) * 2 - int(peer_strength)
            if name in intake_hits:
                score += 4
            if rec.matched_terms:
                score += sum(1 for phrase in rec.matched_terms if any(term in phrase for term in axis["terms"]))
            scored.append((name, score, terms))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored

    def _recommendation_text(self, rec: Recommendation) -> str:
        chunks: list[str] = []
        knowledge = self._load_prescription_knowledge(rec.prescription)
        chunks.extend([
            knowledge.clinical_application,
            " ".join(knowledge.indications),
            " ".join(knowledge.case_titles[:20]),
        ])
        if rec.meta:
            chunks.extend([rec.meta.description, " ".join(rec.meta.indications), " ".join(rec.meta.herbs)])
        for hit in rec.cases[:6]:
            case = hit.case
            chunks.extend([
                case.symptoms,
                case.sections.get("주증상", ""),
                case.sections.get("부수증상", ""),
                case.sections.get("참고증상", ""),
                case.sections.get("투약", ""),
                case.sections.get("경과", ""),
            ])
        return "\n".join(chunk for chunk in chunks if chunk)

    def _branch_for_rec(self, rec: Recommendation, intake: Intake, peers: list[Recommendation]) -> tuple[str, str]:
        if rec.inference_axes:
            axis_names = rec.inference_axes[:2]
            terms: list[str] = []
            for axis_name in axis_names:
                axis = next((item for item in CLINICAL_AXES if item["name"] == axis_name), None)
                if axis:
                    terms.extend(axis["terms"][:3])
            return " / ".join(axis_names) + " 흐름으로 볼 수 있는가?", _format_terms(terms, 5)
        profile = self._axis_profile_for_rec(rec, intake, peers)
        if profile:
            axis_names = [name for name, _, _ in profile[:2]]
            terms = []
            for _, _, axis_terms in profile[:2]:
                terms.extend(axis_terms[:3])
            question = " / ".join(axis_names) + " 양상이 중심인가?"
            basis = _format_terms(terms, 5)
            return question, basis
        if rec.matched_terms:
            return f"{_format_terms(rec.matched_terms, 2)}가 중심인가?", _format_terms(rec.matched_terms, 4)
        return "상위 치험례와 같은 경과/투약 반응이 예상되는가?", "유사 치험례 본문"

    def _mermaid_label(self, text: str, limit: int = 58) -> str:
        text = _clip(text, limit)
        text = text.replace('"', "'").replace("\n", "<br/>")
        return text

    def _flowchart_lines(self, intake: Intake, recommendations: list[Recommendation]) -> list[str]:
        candidates = recommendations[: min(5, len(recommendations))]
        if not candidates:
            return ["분기할 후보 처방이 없습니다."]

        lines = [
            "아래 흐름은 내부 계산 과정이 아니라, **상위 후보 처방을 실제 문진에서 어떻게 가를지**에 맞춘 질문 트리입니다.",
            "",
            "```mermaid",
            "flowchart TD",
            'A["현재 문진표"] --> Q1',
        ]

        for idx, rec in enumerate(candidates, 1):
            question, basis = self._branch_for_rec(rec, intake, candidates)
            qid = f"Q{idx}"
            rid = f"R{idx}"
            next_qid = f"Q{idx + 1}" if idx < len(candidates) else "RZ"
            lines.append(f'{qid}{{"{self._mermaid_label(question)}"}}')
            lines.append(f'{qid} -- "예: {self._mermaid_label(basis, 34)}" --> {rid}["{self._mermaid_label(rec.prescription, 28)}"]')
            lines.append(f'{qid} -- "아니오" --> {next_qid}')

        lines.append('RZ["추가 문진 후<br/>후보 재분석"]')
        lines.append("```")
        lines.append("")
        lines.append("### 후보별 감별 포인트")
        for rec in candidates:
            question, basis = self._branch_for_rec(rec, intake, candidates)
            lines.append(f"- **{rec.prescription}**: `{question}` 예로 답하면 강화. 근거 축: {basis}")
        if intake.missing_groups:
            lines.append(f"- 아직 비어 있어 처방을 크게 흔들 수 있는 축: {_format_terms(intake.missing_groups, 8)}")
        return lines

    def _discriminator_terms(self, left: Recommendation, right: Recommendation) -> list[str]:
        left_text = "\n".join(hit.case.index_text for hit in left.cases)
        right_text = "\n".join(hit.case.index_text for hit in right.cases)
        left_terms: Counter[str] = Counter()
        right_terms: Counter[str] = Counter()
        for hit in left.cases[:6]:
            left_terms.update(_extract_clinical_phrases_from_sections(hit.case.sections, {}, limit=30))
        for hit in right.cases[:6]:
            right_terms.update(_extract_clinical_phrases_from_sections(hit.case.sections, {}, limit=30))
        candidates = []
        for term, count in left_terms.items():
            if count >= 1 and right_terms.get(term, 0) == 0 and not _phrase_matches_text(term, right_text):
                candidates.append(term)
        for term, count in right_terms.items():
            if count >= 1 and left_terms.get(term, 0) == 0 and not _phrase_matches_text(term, left_text):
                candidates.append(term)
        return candidates[:20]

    def _format_questions(self, intake: Intake, recommendations: list[Recommendation]) -> str:
        lines = ["## 다음 문진 질문", ""]
        lines.append("동일한 주증상에서도 처방이 갈리는 지점만 우선 물어보도록 정리했습니다.")
        lines.append("")

        groups = intake.missing_groups[:]
        if recommendations[:2]:
            lines.append("### 후보를 가르는 질문")
            candidates = recommendations[: min(5, len(recommendations))]
            for rec in candidates:
                question, basis = self._branch_for_rec(rec, intake, candidates)
                lines.append(f"- **{rec.prescription}**: {question} 확인. 근거 축: {basis}")
            lines.append("")

        if not groups:
            groups = ["소화", "대변", "한열", "기력", "정서", "수분"]

        for group in groups[:6]:
            questions = QUESTION_BANK.get(group, [])
            if not questions:
                continue
            lines.append(f"### {group}")
            for question in questions[:3]:
                lines.append(f"- {question}")
            lines.append("")
        return "\n".join(lines)

    def _format_evidence(self, recommendations: list[Recommendation]) -> str:
        if not recommendations:
            return "근거로 표시할 유사 치험례가 없습니다."
        lines = ["## 유사 치험례 근거", ""]
        for rec in recommendations[:5]:
            lines.append(f"### {rec.prescription}  `{rec.score:.1%}`")
            if rec.inference_axes:
                lines.append(f"- 판단축: {_format_terms(rec.inference_axes, 4)}")
            if rec.author_mix:
                lines.append(f"- 작성자 근거: {_format_terms(rec.author_mix, 4)}")
            for hit in rec.cases[:4]:
                case = hit.case
                lines.append(f"- **{hit.score:.1%}** `{case.post_id}` {case.author or ''} {case.patient_info or ''}")
                if hit.matched_terms:
                    lines.append(f"  겹친 증상축: {_format_terms(hit.matched_terms, 8)}")
                if case.url:
                    lines.append(f"  원문 링크: {case.url}")
                lines.append(f"  주증상: {_clip(case.sections.get('주증상') or case.symptoms, 230)}")
                sub = case.sections.get("부수증상")
                if sub:
                    lines.append(f"  부수증상: {_clip(sub, 180)}")
                ref = case.sections.get("참고증상")
                if ref:
                    lines.append(f"  참고: {_clip(ref, 180)}")
                course = case.sections.get("경과")
                if course:
                    lines.append(f"  경과: {_clip(course, 180)}")
                lines.append(f"  파일: `{case.path}`")
            lines.append("")
        return "\n".join(lines)

    def _format_detail_page(self, intake: Intake, recommendations: list[Recommendation]) -> str:
        if not recommendations:
            return "상세 설명을 만들 추천 처방이 없습니다."

        top = recommendations[0]
        knowledge = self._load_prescription_knowledge(top.prescription)
        composition = self._composition_for_rec(top)
        lines = [
            f"## {top.prescription} 상세 판단",
            "",
            "키워드 빈도보다 **문진의 증상 흐름 -> 두 작성자의 유사 치험례 -> 처방 문헌 -> 약재 방향성** 순서로 근거를 묶었습니다.",
            "",
            "### 1. 증상에서 출발한 추론",
            f"- 문진에서 먼저 잡힌 변증축: {_format_terms(top.inference_axes, 5)}",
            f"- 실제 문진 구절과 겹친 증상군: {_format_terms(top.matched_terms, 10)}",
            f"- 두 작성자 치험례 근거: {_format_terms(top.author_mix, 4)}",
            f"- 처방/약재 문헌 보강도: {top.knowledge_score:.1%}",
        ]

        if top.style_notes:
            lines.extend(["", "### 2. 투약/경과에서 잡힌 증상 중심 단서"])
            for note in top.style_notes[:4]:
                lines.append(f"- {note}")

        lines.extend(["", "### 3. 처방 문헌 근거"])
        if knowledge.source_path:
            lines.append(f"- 문헌 파일: `{knowledge.source_path}`")
        if knowledge.clinical_application:
            lines.append(f"- 임상응용: {_clip(knowledge.clinical_application, 520)}")
        if knowledge.indications:
            matched_indications = self._matched_indications(intake, knowledge.indications)
            lines.append(f"- 문진과 직접 맞닿은 적용증: {_format_terms(matched_indications or knowledge.indications, 18)}")
        if top.meta and top.meta.description:
            lines.append(f"- DB 처방 설명: {_clip(top.meta.description, 360)}")
        if top.meta and top.meta.indications:
            lines.append(f"- DB 적응증: {_format_terms(top.meta.indications, 18)}")

        if composition:
            lines.extend(["", "### 4. 구성 약재로 본 처방 방향"])
            lines.append(f"- 구성: {_format_terms([f'{herb} {dose}'.strip() for herb, dose in composition], 24)}")
            for herb, dose, bullets in self._herb_explanations_for_rec(top, intake)[:10]:
                dose_text = f" `{dose}`" if dose else ""
                if bullets:
                    lines.append(f"- **{herb}**{dose_text}: {_format_terms(bullets, 2)}")
                else:
                    lines.append(f"- **{herb}**{dose_text}: 약재 문헌 요약이 없어 구성상 역할만 참고합니다.")
        else:
            lines.append("- 구성 약재 자료를 찾지 못해 치험례와 DB 설명 중심으로 표시합니다.")

        if len(recommendations) > 1:
            lines.extend(["", "### 5. 상위 후보와 갈리는 질문"])
            candidates = recommendations[: min(5, len(recommendations))]
            for rec in candidates:
                question, basis = self._branch_for_rec(rec, intake, candidates)
                lines.append(f"- **{rec.prescription}**: {question} 근거 축: {basis}")

        lines.extend(["", "### 6. 대표 유사 치험례"])
        for hit in top.cases[:4]:
            case = hit.case
            lines.append(f"- `{case.post_id}` {case.author or ''} {case.patient_info or ''} `{hit.score:.1%}`")
            if case.url:
                lines.append(f"  {case.url}")
            lines.append(f"  주증상: {_clip(case.sections.get('주증상') or case.symptoms, 230)}")
            if case.sections.get("투약"):
                lines.append(f"  투약: {_clip(case.sections.get('투약'), 190)}")
            if case.sections.get("경과"):
                lines.append(f"  경과: {_clip(case.sections.get('경과'), 190)}")

        return "\n".join(lines)

    def _herb_explanations_for_rec(self, rec: Recommendation, intake: Intake) -> list[tuple[str, str, list[str]]]:
        intake_axes = _axis_score_map(intake.query_text)
        explanations = []
        for herb, dose in self._composition_for_rec(rec):
            herb_info = self._load_herb_knowledge(herb)
            bullets = self._select_herb_bullets(herb_info, intake, intake_axes)
            relevance = 0.0
            if bullets:
                bullet_text = "\n".join(bullets)
                relevance = _axis_similarity(intake_axes, _axis_score_map(bullet_text))
                phrase_score, _ = _phrase_match_score(intake.clinical_phrases, bullet_text)
                relevance += phrase_score
            explanations.append((relevance, herb, dose, bullets))
        explanations.sort(key=lambda item: (-item[0], item[1]))
        return [(herb, dose, bullets) for _score, herb, dose, bullets in explanations]

    def _select_herb_bullets(
        self,
        herb_info: HerbKnowledge,
        intake: Intake,
        intake_axes: dict[str, float],
        limit: int = 2,
    ) -> list[str]:
        if not herb_info.summary:
            return []
        scored = []
        for idx, bullet in enumerate(herb_info.summary):
            axis_score = _axis_similarity(intake_axes, _axis_score_map(bullet))
            phrase_score, _ = _phrase_match_score(intake.clinical_phrases, bullet)
            marker_score = 0.0
            for axis in CLINICAL_AXES:
                if axis["name"] in intake_axes and any(term in bullet for term in axis["terms"]):
                    marker_score += 0.15
            score = axis_score * 2.5 + phrase_score * 1.8 + marker_score
            if score:
                scored.append((score, -idx, bullet))
        if not scored:
            return herb_info.summary[:1]
        scored.sort(reverse=True)
        return [bullet for _score, _idx, bullet in scored[:limit]]

    def compare(self, raw_intake: str, alternative: str, top_k: int = 8) -> str:
        intake, recommendations = self.recommend(raw_intake, top_k=top_k)
        if not recommendations:
            return "먼저 문진표를 입력하고 분석을 실행해 주세요."

        chosen_name = self.find_prescription_name(alternative)
        if not chosen_name:
            return f"입력한 처방 `{alternative}`을 찾지 못했습니다. 드롭다운에서 처방명을 선택하거나 정확한 이름으로 다시 입력해 주세요."

        recommended = recommendations[0]
        if chosen_name == recommended.prescription:
            return f"선택한 처방이 현재 1순위 추천 처방인 **{recommended.prescription}**와 같습니다."

        chosen = self._recommendation_for_name(intake, chosen_name)
        if not chosen:
            return f"**{chosen_name}** 치험례를 찾지 못했습니다."

        return self._format_comparison(intake, recommended, chosen)

    def _recommendation_for_name(self, intake: Intake, name: str) -> Recommendation | None:
        self.ensure_loaded()
        assert self._vectorizer is not None
        assert self._case_matrix is not None
        case_indices = [idx for idx, case in enumerate(self.cases) if case.prescription == name]
        if not case_indices:
            return None
        query_vec = self._vectorizer.transform([intake.query_text])
        sims = cosine_similarity(query_vec, self._case_matrix[case_indices]).ravel()
        intake_axes = _axis_score_map(intake.query_text)
        scored_cases = []
        for local_idx, case_idx in enumerate(case_indices):
            case = self.cases[case_idx]
            score, matched = self._style_case_score(intake, intake_axes, case, float(sims[local_idx]))
            scored_cases.append((score, matched, case))
        scored_cases.sort(key=lambda item: item[0], reverse=True)
        hits = []
        for score, matched, case in scored_cases[:8]:
            if score <= 0:
                continue
            hits.append(CaseHit(case=case, score=score, matched_terms=matched))
        if not hits:
            hits = [CaseHit(case=self.cases[case_indices[0]], score=0.0, matched_terms=[])]
        knowledge_score = self._prescription_knowledge_score(intake, intake_axes, name)
        score = (
            hits[0].score * 0.46
            + (sum(h.score for h in hits[:5]) / min(len(hits), 5)) * 0.28
            + self._prescription_profile_score(intake_axes, hits) * 0.14
            + knowledge_score * 0.12
        )
        return Recommendation(
            prescription=name,
            score=score,
            cases=hits,
            case_count=len(case_indices),
            matched_terms=self._aggregate_terms(hits),
            meta=self.get_prescription_meta(name),
            inference_axes=self._inference_axes_for_hits(intake_axes, hits),
            style_notes=self._style_notes_for_hits(hits, intake),
            author_mix=self._author_mix_for_hits(hits),
            knowledge_score=knowledge_score,
        )

    def _format_comparison(self, intake: Intake, recommended: Recommendation, chosen: Recommendation) -> str:
        lines = [
            "## 처방 비교",
            "",
            f"- 추천 1순위: **{recommended.prescription}** `{recommended.score:.1%}`",
            f"- 사용자가 선택한 처방: **{chosen.prescription}** `{chosen.score:.1%}`",
            "",
            "### 문진표와 맞는 지점",
            f"- **{recommended.prescription} 판단축**: {_format_terms(recommended.inference_axes, 4)}",
            f"- **{chosen.prescription} 판단축**: {_format_terms(chosen.inference_axes, 4)}",
            f"- **{recommended.prescription}**: {_format_terms(recommended.matched_terms, 14)}",
            f"- **{chosen.prescription}**: {_format_terms(chosen.matched_terms, 14)}",
            "",
        ]

        lines.extend(self._compare_meta_lines(recommended, chosen))
        lines.extend(["", "### 유사 치험례상의 예상 경과", ""])
        lines.append(f"- **{recommended.prescription}**: {self._course_summary(recommended)}")
        lines.append(f"- **{chosen.prescription}**: {self._course_summary(chosen)}")

        lines.extend(["", "### 선택 기준", ""])
        lines.append(
            f"- **{recommended.prescription}**가 더 맞아 보이는 조건: "
            f"{self._case_pattern_summary(recommended)}"
        )
        lines.append(
            f"- **{chosen.prescription}**가 더 맞아 보이는 조건: "
            f"{self._case_pattern_summary(chosen)}"
        )
        rec_q, rec_basis = self._branch_for_rec(recommended, intake, [recommended, chosen])
        chosen_q, chosen_basis = self._branch_for_rec(chosen, intake, [recommended, chosen])
        lines.append(f"- **{recommended.prescription} 감별 질문**: {rec_q} 근거 축: {rec_basis}")
        lines.append(f"- **{chosen.prescription} 감별 질문**: {chosen_q} 근거 축: {chosen_basis}")

        lines.extend(["", "### 대표 치험례", ""])
        for rec in (recommended, chosen):
            lines.append(f"**{rec.prescription}**")
            for hit in rec.cases[:3]:
                case = hit.case
                lines.append(
                    f"- `{case.post_id}` {case.author or ''} {case.patient_info or ''}: "
                    f"{_clip(case.sections.get('주증상') or case.symptoms, 180)}"
                )
                if case.url:
                    lines.append(f"  {case.url}")
            lines.append("")
        return "\n".join(lines)

    def _compare_meta_lines(self, recommended: Recommendation, chosen: Recommendation) -> list[str]:
        lines = ["### 처방 설명과 약재 차이", ""]
        r_meta = recommended.meta
        c_meta = chosen.meta
        if r_meta and r_meta.description:
            lines.append(f"- **{recommended.prescription} 설명**: {_clip(r_meta.description, 220)}")
        if c_meta and c_meta.description:
            lines.append(f"- **{chosen.prescription} 설명**: {_clip(c_meta.description, 220)}")

        for rec in (recommended, chosen):
            knowledge = self._load_prescription_knowledge(rec.prescription)
            if knowledge.clinical_application:
                lines.append(f"- **{rec.prescription} 문헌 임상응용**: {_clip(knowledge.clinical_application, 220)}")
            composition = self._composition_for_rec(rec)
            if composition:
                lines.append(
                    f"- **{rec.prescription} 문헌 구성**: "
                    f"{_format_terms([f'{herb} {dose}'.strip() for herb, dose in composition], 18)}"
                )

        if r_meta and c_meta and (r_meta.herbs or c_meta.herbs):
            r_herbs = set(r_meta.herbs)
            c_herbs = set(c_meta.herbs)
            shared = sorted(r_herbs & c_herbs)
            only_r = sorted(r_herbs - c_herbs)
            only_c = sorted(c_herbs - r_herbs)
            lines.append(f"- 공통 약재: {_format_terms(shared, 16)}")
            lines.append(f"- **{recommended.prescription} 쪽에 더 있는 약재**: {_format_terms(only_r, 16)}")
            lines.append(f"- **{chosen.prescription} 쪽에 더 있는 약재**: {_format_terms(only_c, 16)}")
            r_note = self._herb_direction_note(list(r_herbs))
            c_note = self._herb_direction_note(list(c_herbs))
            if r_note:
                lines.append(f"- **{recommended.prescription} 약재 방향성**: {r_note}")
            if c_note:
                lines.append(f"- **{chosen.prescription} 약재 방향성**: {c_note}")
        else:
            lines.append("- DB에 구성 약재가 부족해 약재 차이는 치험례 본문 중심으로 비교했습니다.")
        return lines

    def _course_summary(self, rec: Recommendation) -> str:
        courses = []
        for hit in self._relevant_hits(rec):
            course = hit.case.sections.get("경과")
            if course:
                courses.append(_clip(course, 150))
        if courses:
            return " / ".join(courses[:2])
        return "상위 유사 치험례에 경과 항목이 부족해 주증상 일치도 중심으로 판단해야 합니다."

    def _case_pattern_summary(self, rec: Recommendation) -> str:
        phrases = []
        for hit in self._relevant_hits(rec)[:4]:
            phrases.extend(_extract_clinical_phrases_from_sections(hit.case.sections, {}, limit=18))
        return _format_terms(phrases, 12)

    def _relevant_hits(self, rec: Recommendation) -> list[CaseHit]:
        if not rec.cases:
            return []
        top_score = rec.cases[0].score
        threshold = max(0.12, top_score * 0.4)
        hits = [hit for hit in rec.cases if hit.score >= threshold]
        return hits or rec.cases[:3]
