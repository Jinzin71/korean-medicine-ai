"""
prescription_db.py — 처방 데이터 레이어
=========================================================
Obsidian vault (방약합편/) 의 533개 .md 파일을 파싱하여
SQLite DB에 저장하고 검색·유사도 분석 기능을 제공합니다.

스키마:
  prescriptions  — 처방 메타데이터 (약재, 적응증, 설명, 관련처방)
  cases          — 치험례 (밴드 링크, 환자정보)
"""

import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

# ── 데이터 모델 ───────────────────────────────────────────────────────────────

@dataclass
class Prescription:
    id: str                          # 처방명 기반 slug
    name: str                        # 처방명 (한글)
    name_hanja: str = ""             # 한자 처방명
    description: str = ""           # 처방 설명
    indications: list[str] = field(default_factory=list)   # 적응증/증상
    herbs: list[str] = field(default_factory=list)         # 구성 약재
    herbs_detail: dict = field(default_factory=dict)       # {약재명: 용량} 상세
    source_file: str = ""           # Obsidian .md 파일 경로
    section: str = ""               # 상통/중통/하통
    code: str = ""                  # 전체 코드 (상통-022)
    parent_id: str = ""             # 부모 처방 ID (변형인 경우)
    related: list[str] = field(default_factory=list)  # 관련 처방 [[링크]]
    cases: list[dict] = field(default_factory=list)        # 치험례 목록


@dataclass
class Case:
    id: str
    prescription_id: str
    date: str = ""
    author: str = ""
    url: str = ""
    symptoms: str = ""
    content: str = ""
    patient_age: str = ""
    patient_sex: str = ""
    patient_bmi: str = ""
    constitution: str = ""


# ── DB 클래스 ─────────────────────────────────────────────────────────────────

class PrescriptionDB:
    """
    SQLite 기반 처방 데이터베이스.
    Phase 1 완료 전까지 mock 데이터로 동작.
    """

    def __init__(self, db_path: str = "prescriptions.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS prescriptions (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                name_hanja  TEXT DEFAULT '',
                description TEXT DEFAULT '',
                indications TEXT DEFAULT '[]',   -- JSON array
                herbs       TEXT DEFAULT '[]',   -- JSON array
                herbs_detail TEXT DEFAULT '{}',  -- JSON dict {약재:용량}
                source_file TEXT DEFAULT '',
                section     TEXT DEFAULT '',     -- 상통/중통/하통
                code        TEXT DEFAULT '',     -- 전체 코드 (상통-022)
                parent_id   TEXT DEFAULT '',     -- 부모 처방 ID
                related     TEXT DEFAULT '[]'    -- JSON array 관련처방
            );
            CREATE TABLE IF NOT EXISTS cases (
                id              TEXT PRIMARY KEY,
                prescription_id TEXT NOT NULL,
                date            TEXT DEFAULT '',
                author          TEXT DEFAULT '',
                url             TEXT DEFAULT '',
                symptoms        TEXT DEFAULT '',
                content         TEXT DEFAULT '',
                patient_age     TEXT DEFAULT '',
                patient_sex     TEXT DEFAULT '',
                patient_bmi     TEXT DEFAULT '',
                constitution    TEXT DEFAULT '',
                FOREIGN KEY (prescription_id) REFERENCES prescriptions(id)
            );
            CREATE INDEX IF NOT EXISTS idx_cases_presc ON cases(prescription_id);
        """)
        self.conn.commit()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def upsert_prescription(self, p: Prescription):
        self.conn.execute("""
            INSERT INTO prescriptions (id,name,name_hanja,description,indications,herbs,herbs_detail,source_file,section,code,parent_id,related)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, name_hanja=excluded.name_hanja,
                description=excluded.description, indications=excluded.indications,
                herbs=excluded.herbs, herbs_detail=excluded.herbs_detail,
                source_file=excluded.source_file, section=excluded.section,
                code=excluded.code, parent_id=excluded.parent_id, related=excluded.related
        """, (p.id, p.name, p.name_hanja, p.description,
              json.dumps(p.indications, ensure_ascii=False),
              json.dumps(p.herbs, ensure_ascii=False),
              json.dumps(p.herbs_detail, ensure_ascii=False),
              p.source_file, p.section, p.code, p.parent_id,
              json.dumps(p.related, ensure_ascii=False)))
        self.conn.commit()

    def add_case(self, c: Case):
        self.conn.execute("""
            INSERT OR IGNORE INTO cases (id,prescription_id,date,author,url,symptoms,content,patient_age,patient_sex,patient_bmi,constitution)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (c.id, c.prescription_id, c.date, c.author, c.url, c.symptoms, c.content,
              c.patient_age, c.patient_sex, c.patient_bmi, c.constitution))
        self.conn.commit()

    def get_all_prescriptions(self) -> list[Prescription]:
        rows = self.conn.execute("SELECT * FROM prescriptions").fetchall()
        return [self._row_to_prescription(r) for r in rows]

    def get_prescription(self, prescription_id: str) -> Optional[Prescription]:
        row = self.conn.execute(
            "SELECT * FROM prescriptions WHERE id=?", (prescription_id,)
        ).fetchone()
        return self._row_to_prescription(row) if row else None

    def get_cases(self, prescription_id: str) -> list[Case]:
        rows = self.conn.execute(
            "SELECT * FROM cases WHERE prescription_id=? ORDER BY date DESC",
            (prescription_id,)
        ).fetchall()
        return [Case(**dict(r)) for r in rows]

    def search_by_symptoms(self, query: str) -> list[Prescription]:
        """증상 키워드로 처방 검색 (간단한 텍스트 매칭)"""
        q = f"%{query}%"
        rows = self.conn.execute("""
            SELECT * FROM prescriptions
            WHERE indications LIKE ? OR description LIKE ? OR name LIKE ?
        """, (q, q, q)).fetchall()
        return [self._row_to_prescription(r) for r in rows]

    def _row_to_prescription(self, row) -> Prescription:
        d = dict(row)
        d["indications"] = json.loads(d.get("indications", "[]"))
        d["herbs"] = json.loads(d.get("herbs", "[]"))
        d["herbs_detail"] = json.loads(d.get("herbs_detail", "{}"))
        d["related"] = json.loads(d.get("related", "[]"))
        d["cases"] = []
        # 누락 필드 기본값
        for k in ("section", "code", "parent_id", "source_file", "name_hanja"):
            d.setdefault(k, "")
        return Prescription(**d)

    # ── 유사도 계산 ────────────────────────────────────────────────────────────

    def jaccard_similarity(self, herbs_a: list[str], herbs_b: list[str]) -> float:
        """약재 집합 간 Jaccard 유사도"""
        a, b = set(herbs_a), set(herbs_b)
        if not a and not b:
            return 0.0
        return len(a & b) / len(a | b)

    def weighted_similarity(self, target: Prescription, other: Prescription) -> float:
        """
        가중 유사도: 약재 Jaccard + 관련처방 보너스 + 부모-자식 보너스.
        Returns: 0.0 ~ 1.0
        """
        # 기본 약재 Jaccard
        herb_score = self.jaccard_similarity(target.herbs, other.herbs)

        # 관련처방 보너스: [[링크]]로 직접 연결된 경우 +0.15
        link_bonus = 0.0
        target_related_names = set()
        for link in target.related:
            # "상통-022 보중익기탕" → "보중익기탕" 추출
            parts = link.split(maxsplit=1)
            if len(parts) > 1:
                target_related_names.add(parts[1])
        if other.name in target_related_names or other.code in [r.split()[0] for r in target.related if r]:
            link_bonus = 0.15

        # 부모-자식 보너스: 같은 부모의 변형이면 +0.2
        parent_bonus = 0.0
        if target.parent_id and target.parent_id == other.parent_id:
            parent_bonus = 0.2
        elif target.code and other.parent_id and other.parent_id == f"{target.section}-{target.code.split('-')[1] if '-' in target.code else ''}":
            parent_bonus = 0.2
        elif other.code and target.parent_id and target.parent_id == f"{other.section}-{other.code.split('-')[1] if '-' in other.code else ''}":
            parent_bonus = 0.2

        return min(1.0, herb_score + link_bonus + parent_bonus)

    def get_similar_prescriptions(
        self, prescription_id: str, top_k: int = 5
    ) -> list[tuple[Prescription, float]]:
        """
        약재 구성 + 관련처방 링크 기반 유사 처방 상위 k개 반환.
        Returns: [(Prescription, similarity_score), ...]
        """
        target = self.get_prescription(prescription_id)
        if not target:
            return []
        all_p = self.get_all_prescriptions()
        scored = []
        for p in all_p:
            if p.id == prescription_id:
                continue
            score = self.weighted_similarity(target, p)
            if score > 0:
                scored.append((p, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # ── Vault 로드 ─────────────────────────────────────────────────────────────

    def load_from_vault(self, vault_path: str):
        """
        Obsidian vault의 .md 파일을 파싱하여 DB에 로드합니다.
        vault_parser.py의 VaultParser를 사용합니다.
        """
        from vault_parser import VaultParser

        parser = VaultParser(vault_path)
        parsed_list = parser.parse_all()

        for pp in parsed_list:
            # Prescription 객체 생성
            p = Prescription(
                id=pp.name,
                name=pp.name,
                name_hanja="",
                description=pp.description[:2000] if pp.description else "",
                indications=pp.indications,
                herbs=pp.herbs,
                herbs_detail=pp.herbs_detail,
                source_file=pp.file_path,
                section=pp.section,
                code=pp.full_code,
                parent_id=pp.parent_id,
                related=pp.related_prescriptions,
            )
            self.upsert_prescription(p)

            # 치험례 로드
            for ce in pp.cases:
                case_id = hashlib.md5(
                    f"{pp.name}:{ce.number}:{ce.url}".encode()
                ).hexdigest()[:12]
                c = Case(
                    id=case_id,
                    prescription_id=pp.name,
                    url=ce.url,
                    symptoms=ce.symptoms,
                    content=ce.raw_text,
                    patient_age=ce.patient_age,
                    patient_sex=ce.patient_sex,
                    patient_bmi=ce.patient_bmi,
                    constitution=ce.constitution,
                )
                self.add_case(c)

        return len(parsed_list)

    # ── Mock 데이터 로드 ──────────────────────────────────────────────────────

    def load_mock_data(self):
        """개발/테스트용 mock 처방 데이터"""
        mock_prescriptions = [
            Prescription(
                id="소청룡탕",
                name="소청룡탕",
                name_hanja="小靑龍湯",
                description="한랭한 기후나 냉기에 의한 표한(表寒)을 발산시키고 "
                            "폐의 수분대사를 조절하여 기침, 천식, 수양성 콧물을 치료하는 처방.",
                indications=["기침", "천식", "수양성 콧물", "오한", "발열 없는 감기", "알레르기 비염", "묽은 가래"],
                herbs=["마황", "계지", "작약", "건강", "세신", "반하", "오미자", "감초"],
            ),
            Prescription(
                id="보중익기탕",
                name="보중익기탕",
                name_hanja="補中益氣湯",
                description="비위(脾胃)의 기능을 보강하고 기운을 북돋아 만성 피로, "
                            "소화불량, 면역력 저하에 사용하는 대표적 보기제(補氣劑).",
                indications=["만성 피로", "소화불량", "식욕부진", "기력저하", "잦은 감기", "탈항", "자궁하수"],
                herbs=["황기", "인삼", "백출", "감초", "당귀", "진피", "승마", "시호"],
            ),
            Prescription(
                id="육미지황탕",
                name="육미지황탕",
                name_hanja="六味地黃湯",
                description="신(腎)과 간(肝)의 음허(陰虛)를 보충하는 처방으로 "
                            "허열, 도한, 요통, 이명 등 음허 증상에 광범위하게 사용.",
                indications=["음허", "허열", "도한", "요통", "이명", "어지러움", "구건", "유정"],
                herbs=["숙지황", "산수유", "산약", "택사", "목단피", "복령"],
            ),
            Prescription(
                id="팔미지황탕",
                name="팔미지황탕",
                name_hanja="八味地黃湯",
                description="육미지황탕에 계지와 부자를 더한 처방. "
                            "신양(腎陽) 부족으로 인한 냉증, 요슬냉통, 야간뇨 등에 사용.",
                indications=["신양허", "냉증", "요슬냉통", "야간뇨", "부종", "양위", "기력저하"],
                herbs=["숙지황", "산수유", "산약", "택사", "목단피", "복령", "계지", "부자"],
            ),
            Prescription(
                id="갈근탕",
                name="갈근탕",
                name_hanja="葛根湯",
                description="발열, 두통, 항배강통(項背强痛)을 주치하는 처방. "
                            "감기 초기 또는 목·어깨 결림에 폭넓게 사용.",
                indications=["발열", "두통", "항강", "어깨결림", "감기 초기", "비염", "설사"],
                herbs=["갈근", "마황", "계지", "작약", "감초", "생강", "대조"],
            ),
            Prescription(
                id="형방패독산",
                name="형방패독산",
                name_hanja="荊防敗毒散",
                description="풍한습사(風寒濕邪)를 표산(表散)하는 처방. "
                            "감기, 두통, 인후통, 피부 발적에 활용.",
                indications=["감기", "두통", "인후통", "피부 발적", "초기 농피증", "오한 발열"],
                herbs=["형개", "방풍", "강활", "독활", "시호", "전호", "지각", "복령", "천궁", "인삼", "감초", "생강"],
            ),
            Prescription(
                id="오령산",
                name="오령산",
                name_hanja="五苓散",
                description="수분 대사 이상으로 인한 구갈(口渴), 소변불리, 부종, "
                            "설사, 두통, 현훈 등에 사용하는 이수제(利水劑).",
                indications=["구갈", "소변불리", "부종", "설사", "현훈", "두통", "숙취"],
                herbs=["택사", "저령", "복령", "백출", "계지"],
            ),
            Prescription(
                id="사군자탕",
                name="사군자탕",
                name_hanja="四君子湯",
                description="비위 기허(氣虛)의 기본 처방. 인삼·백출·복령·감초의 "
                            "조합으로 소화기 기능을 보강.",
                indications=["소화불량", "식욕부진", "피로", "기허", "묽은 변"],
                herbs=["인삼", "백출", "복령", "감초"],
            ),
            Prescription(
                id="사물탕",
                name="사물탕",
                name_hanja="四物湯",
                description="혈허(血虛)의 기본 처방. 숙지황·당귀·천궁·작약으로 "
                            "혈액 생성 및 순환을 도움.",
                indications=["혈허", "빈혈", "생리불순", "생리통", "안색창백", "어지러움", "불면"],
                herbs=["숙지황", "당귀", "천궁", "작약"],
            ),
            Prescription(
                id="쌍화탕",
                name="쌍화탕",
                name_hanja="雙和湯",
                description="기혈(氣血)을 동시에 보충하는 처방. "
                            "사물탕과 황기·육계·감초를 합하여 과로 회복, 허약 체질에 활용.",
                indications=["기혈양허", "피로 회복", "수술 후 허약", "과로", "허약 체질"],
                herbs=["숙지황", "당귀", "천궁", "작약", "황기", "육계", "감초", "생강", "대조"],
            ),
        ]

        mock_cases = [
            Case(id="c001", prescription_id="소청룡탕", date="2025-01-10",
                 author="김원장", url="https://band.us/post/example1",
                 symptoms="기침, 수양성 콧물, 오한",
                 content="50대 여성. 찬바람 노출 후 기침과 맑은 콧물 3일. 소청룡탕 3일 복용 후 현저히 호전."),
            Case(id="c002", prescription_id="소청룡탕", date="2025-02-15",
                 author="이원장", url="https://band.us/post/example2",
                 symptoms="알레르기 비염, 재채기",
                 content="30대 남성 알레르기 비염. 봄철 악화. 소청룡탕 2주 복용으로 재채기 및 콧물 60% 감소."),
            Case(id="c003", prescription_id="보중익기탕", date="2025-01-20",
                 author="박원장", url="https://band.us/post/example3",
                 symptoms="만성 피로, 소화불량",
                 content="40대 직장인. 만성 피로, 식후 더부룩함. 보중익기탕 1개월 복용 후 식욕 회복, 피로감 개선."),
            Case(id="c004", prescription_id="육미지황탕", date="2025-03-01",
                 author="최원장", url="https://band.us/post/example4",
                 symptoms="이명, 허열, 도한",
                 content="60대 남성. 이명 6개월, 오후 미열, 수면 중 식은땀. 육미지황탕 복용 후 이명 완화 및 수면 개선."),
            Case(id="c005", prescription_id="갈근탕", date="2025-02-05",
                 author="정원장", url="https://band.us/post/example5",
                 symptoms="목·어깨 결림, 두통",
                 content="30대 사무직. 장시간 PC 작업 후 목·어깨 강직 및 긴장성 두통. 갈근탕 1주 복용으로 호전."),
        ]

        for p in mock_prescriptions:
            self.upsert_prescription(p)
        for c in mock_cases:
            self.add_case(c)
