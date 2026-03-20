"""
vault_parser.py — Obsidian Vault .md 파일 파서
=========================================================
방약합편/ 하위 533개 처방 파일을 파싱하여
prescription_db.py 의 PrescriptionDB 에 로드합니다.

파일 구조:
  ### 구성       — 약재 테이블 (용량 | 약재명)
  ### 주치       — 주치 설명 (일부 파일)
  ### 임상응용   — 한문 원문 + 해설 + 가감법
  ### 적용증     — #태그 형태 적응증
  ### 치험례     — 번호. [환자정보](URL)

파일명 규칙:
  (상통|중통|하통)-NNN[-SSS] 처방명.md
  예) 상통-022 보중익기탕.md, 상통-006-001 치중탕.md
"""

import re
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# 파싱 결과 데이터 모델
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HerbEntry:
    """약재 1개 (용량 포함)"""
    name: str           # 약재명 (링크 제거된 순수 이름)
    dosage: str = ""    # 원본 용량 문자열 ("6g", "1구", "2.8g" 등)
    dosage_g: float = 0.0  # 그램 변환값 (변환 불가 시 0)


@dataclass
class CaseEntry:
    """치험례 1건"""
    number: int = 0
    raw_text: str = ""          # [환자정보 / 증상] 부분
    url: str = ""               # band URL
    patient_age: str = ""       # 나이 (예: "81세", "60대초반")
    patient_sex: str = ""       # 성별 (남/여)
    patient_bmi: str = ""       # BMI (예: "22.5")
    bmi_class: str = ""         # BMI 분류 (정상, 1단계비만 등)
    constitution: str = ""      # 체질 (소양인, 소음인 등)
    symptoms: str = ""          # 증상 텍스트


@dataclass
class ParsedPrescription:
    """파싱된 처방 1개"""
    file_path: str = ""
    section: str = ""           # 상통 / 중통 / 하통
    number: str = ""            # 주번호 (예: "022")
    sub_number: str = ""        # 부번호 (예: "001", 없으면 "")
    name: str = ""              # 처방명 (한글)
    parent_id: str = ""         # 부모 처방 ID (변형인 경우)

    herbs: list[str] = field(default_factory=list)              # 약재명 리스트
    herbs_detail: dict[str, str] = field(default_factory=dict)  # {약재명: 용량}
    herbs_entries: list[HerbEntry] = field(default_factory=list) # 상세 정보

    description: str = ""       # 주치 + 임상응용 텍스트
    clinical_app: str = ""      # 임상응용 전문
    indications: list[str] = field(default_factory=list)  # 적용증 태그
    cases: list[CaseEntry] = field(default_factory=list)  # 치험례
    related_prescriptions: list[str] = field(default_factory=list)  # [[링크]] 처방들

    @property
    def id(self) -> str:
        """고유 ID: 처방명 기반"""
        return self.name

    @property
    def full_code(self) -> str:
        """전체 코드: 상통-022 또는 상통-006-001"""
        base = f"{self.section}-{self.number}"
        if self.sub_number:
            base += f"-{self.sub_number}"
        return base


# ─────────────────────────────────────────────────────────────────────────────
# VaultParser
# ─────────────────────────────────────────────────────────────────────────────

class VaultParser:
    """
    Obsidian vault의 방약합편/ 디렉토리를 파싱합니다.

    사용 예시:
        parser = VaultParser("방약합편")
        prescriptions = parser.parse_all()
        print(f"{len(prescriptions)}개 처방 파싱 완료")
    """

    # 파일명 정규식: (섹션)-(번호)[-부번호] 처방명.md
    FILENAME_RE = re.compile(
        r"^(상통|중통|하통)-(\d{3})(?:-(\d{3}))?\s+(.+)\.md$"
    )

    # 섹션 디렉토리명
    SECTION_DIRS = ["상통(001-123)", "중통(001-181)", "하통(001-163)"]

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)

    def parse_all(self) -> list[ParsedPrescription]:
        """전체 vault 파싱 — 모든 .md 파일을 순회합니다."""
        results = []
        for section_dir in self.SECTION_DIRS:
            dir_path = self.vault_path / section_dir
            if not dir_path.exists():
                continue
            for md_file in sorted(dir_path.glob("*.md")):
                # 섹션 인덱스 파일 제외 (상통(001-123).md 등)
                if not self.FILENAME_RE.match(md_file.name):
                    continue
                parsed = self.parse_file(md_file)
                if parsed:
                    results.append(parsed)
        return results

    def parse_file(self, file_path: Path) -> Optional[ParsedPrescription]:
        """단일 .md 파일 파싱"""
        match = self.FILENAME_RE.match(file_path.name)
        if not match:
            return None

        section, number, sub_number, name = match.groups()
        # 처방명에서 (=별칭) 같은 것 정리
        clean_name = re.sub(r"\(=.+\)", "", name).strip()

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return None

        p = ParsedPrescription(
            file_path=str(file_path),
            section=section,
            number=number,
            sub_number=sub_number or "",
            name=clean_name,
        )

        # 부모 처방 ID 설정 (sub_number가 있으면 부모가 존재)
        if sub_number:
            p.parent_id = f"{section}-{number}"

        # 섹션별 파싱
        sections = self._split_sections(content)

        if "구성" in sections:
            self._parse_herbs(sections["구성"], p)

        desc_parts = []
        if "주치" in sections:
            desc_parts.append(sections["주치"].strip())
        if "임상응용" in sections:
            p.clinical_app = sections["임상응용"].strip()
            desc_parts.append(p.clinical_app)
        p.description = "\n\n".join(desc_parts)

        if "적용증" in sections:
            self._parse_indications(sections["적용증"], p)

        if "치험례" in sections:
            self._parse_cases(sections["치험례"], p)

        # [[링크]] 추출 (전체 content에서)
        p.related_prescriptions = self._extract_links(content)

        return p

    # ── 섹션 분리 ──────────────────────────────────────────────────────────

    def _split_sections(self, content: str) -> dict[str, str]:
        """### 헤더 기준으로 섹션 분리"""
        sections = {}
        current_key = None
        current_lines = []

        for line in content.split("\n"):
            header_match = re.match(r"^###\s+(.+)", line)
            if header_match:
                if current_key:
                    sections[current_key] = "\n".join(current_lines)
                current_key = header_match.group(1).strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_key:
            sections[current_key] = "\n".join(current_lines)

        return sections

    # ── 구성 (약재 테이블) 파싱 ────────────────────────────────────────────

    def _parse_herbs(self, text: str, p: ParsedPrescription):
        """약재 테이블 파싱 — 용량 + 약재명 추출"""
        for line in text.split("\n"):
            line = line.strip()
            # 테이블 헤더/구분선 스킵
            if not line or line.startswith("|") and ("용량" in line or "---" in line or ":--" in line or "----" in line):
                continue
            if not line.startswith("|"):
                continue

            # | 용량 | 약재명 | 형태 파싱
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c]  # 빈 셀 제거

            if len(cells) < 2:
                continue

            dosage_raw = cells[0].strip()
            herbs_raw = cells[1].strip()

            # 약재명 추출: [[링크]] 제거 + 공백 분리
            herb_names = self._extract_herb_names(herbs_raw)

            for herb_name in herb_names:
                if not herb_name:
                    continue
                entry = HerbEntry(
                    name=herb_name,
                    dosage=dosage_raw,
                    dosage_g=self._parse_dosage(dosage_raw),
                )
                p.herbs_entries.append(entry)
                p.herbs.append(herb_name)
                p.herbs_detail[herb_name] = dosage_raw

    def _extract_herb_names(self, text: str) -> list[str]:
        """약재 셀에서 개별 약재명 추출"""
        # [[약재명]] 링크 제거
        text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
        # 괄호 안 내용은 유지 (포제법: 건강(포), 반하(제) 등)
        # 공백으로 분리
        herbs = text.split()
        return [h.strip() for h in herbs if h.strip()]

    def _parse_dosage(self, dosage_str: str) -> float:
        """용량 문자열을 g 단위로 변환"""
        dosage_str = dosage_str.strip()
        # Xg 형태
        m = re.match(r"^([\d.]+)\s*g$", dosage_str)
        if m:
            return float(m.group(1))
        # X돈 → 4g per 돈
        m = re.match(r"^([\d.]+)\s*돈$", dosage_str)
        if m:
            return float(m.group(1)) * 4.0
        # X냥 → 40g per 냥
        m = re.match(r"^([\d.]+)\s*냥$", dosage_str)
        if m:
            return float(m.group(1)) * 40.0
        # X전 → 4g per 전
        m = re.match(r"^([\d.]+)\s*전$", dosage_str)
        if m:
            return float(m.group(1)) * 4.0
        return 0.0

    # ── 적용증 파싱 ────────────────────────────────────────────────────────

    def _parse_indications(self, text: str, p: ParsedPrescription):
        """#태그 형태의 적응증 추출"""
        tags = re.findall(r"#(\S+)", text)
        p.indications = tags

    # ── 치험례 파싱 ────────────────────────────────────────────────────────

    # 치험례 패턴: N. [텍스트](URL) 또는 N. [텍스트]
    CASE_RE = re.compile(
        r"(\d+)\.\s*\[([^\]]+)\]\s*(?:\(([^)]+)\))?"
    )

    # 환자 정보 추출 패턴
    AGE_RE = re.compile(r"(남|여|남성|여성)?\s*(\d{1,3}세|\d{1,2}대[초중후]?반?|어린이|아기)")
    SEX_RE = re.compile(r"^(남|여)")
    BMI_RE = re.compile(r"BMI\s*([\d.]+)\s*([\w가-힣]*)")
    CONSTITUTION_RE = re.compile(r"(태양인|태음인|소양인|소음인)")

    def _parse_cases(self, text: str, p: ParsedPrescription):
        """치험례 섹션 파싱"""
        for match in self.CASE_RE.finditer(text):
            number = int(match.group(1))
            raw_text = match.group(2).strip()
            url = (match.group(3) or "").strip()

            case = CaseEntry(
                number=number,
                raw_text=raw_text,
                url=url,
            )

            # 환자 정보 추출
            self._extract_patient_info(raw_text, case)

            p.cases.append(case)

    def _extract_patient_info(self, text: str, case: CaseEntry):
        """치험례 텍스트에서 환자 정보 추출"""
        # '/' 기준으로 환자정보와 증상 분리
        parts = text.split("/", 1)
        info_part = parts[0].strip()
        case.symptoms = parts[1].strip() if len(parts) > 1 else info_part

        # 성별
        sex_m = self.SEX_RE.search(info_part)
        if sex_m:
            case.patient_sex = sex_m.group(1)

        # 나이
        age_m = self.AGE_RE.search(info_part)
        if age_m:
            case.patient_age = age_m.group(2) if age_m.group(2) else ""

        # BMI
        bmi_m = self.BMI_RE.search(info_part)
        if bmi_m:
            case.patient_bmi = bmi_m.group(1)
            case.bmi_class = bmi_m.group(2).strip() if bmi_m.group(2) else ""

        # 체질
        const_m = self.CONSTITUTION_RE.search(info_part)
        if const_m:
            case.constitution = const_m.group(1)

    # ── [[링크]] 추출 ──────────────────────────────────────────────────────

    def _extract_links(self, content: str) -> list[str]:
        """[[처방명]] 내부 링크 추출 (약재 링크 제외)"""
        links = re.findall(r"\[\[([^\]]+)\]\]", content)
        prescription_links = []
        seen = set()
        for link in links:
            # 약재 링크 제외: 섹션 코드가 있으면 처방 링크
            if re.match(r"(상통|중통|하통)-\d+", link):
                if link not in seen:
                    prescription_links.append(link)
                    seen.add(link)
        return prescription_links


# ─────────────────────────────────────────────────────────────────────────────
# CLI 테스트
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault_path = sys.argv[1] if len(sys.argv) > 1 else "방약합편"
    parser = VaultParser(vault_path)
    results = parser.parse_all()

    print(f"\n{'='*60}")
    print(f"  파싱 완료: {len(results)}개 처방")
    print(f"{'='*60}")

    # 섹션별 통계
    by_section = {}
    total_herbs = 0
    total_cases = 0
    total_indications = 0
    variants = 0

    for p in results:
        by_section[p.section] = by_section.get(p.section, 0) + 1
        total_herbs += len(p.herbs)
        total_cases += len(p.cases)
        total_indications += len(p.indications)
        if p.sub_number:
            variants += 1

    print(f"\n  섹션별:")
    for sec, cnt in sorted(by_section.items()):
        print(f"    {sec}: {cnt}개")
    print(f"\n  변형 처방: {variants}개")
    print(f"  총 약재 항목: {total_herbs}개")
    print(f"  총 치험례: {total_cases}건")
    print(f"  총 적용증 태그: {total_indications}개")

    # 샘플 출력
    print(f"\n{'─'*60}")
    print("  샘플 5건:")
    for p in results[:5]:
        print(f"\n  [{p.full_code}] {p.name}")
        print(f"    약재({len(p.herbs)}): {', '.join(p.herbs[:6])}{'...' if len(p.herbs)>6 else ''}")
        print(f"    용량: {dict(list(p.herbs_detail.items())[:4])}")
        print(f"    적응증({len(p.indications)}): {', '.join(p.indications[:5])}")
        print(f"    치험례: {len(p.cases)}건")
        print(f"    관련처방: {', '.join(p.related_prescriptions[:3])}")
