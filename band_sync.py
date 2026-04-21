"""
band_sync.py — Phase 2: 네이버 밴드 동기화 모듈 (공식 API 방식)
=========================================================
BandCrawler 가 Playwright 대신 Band Open API 를 사용합니다.

기능:
  1. BandAPICollector — 공식 REST API로 게시물 수집
  2. ObsidianLinker   — 처방 감지 후 .md 파일에 치험례 링크 삽입
  3. SyncScheduler    — APScheduler 기반 주기적 자동 동기화

의존성:
  pip install requests apscheduler pyyaml python-frontmatter

사전 준비:
  python band_api.py --auth   ← 최초 1회 OAuth 인증
  python band_api.py --bands  ← band_key 확인 후 config 에 입력
"""

import re
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from band_api import BandAPIClient, BandAuthError, BandAPIError

# ── 로거 ─────────────────────────────────────────────────────────────────────

LOG_FILE = Path(__file__).parent / "work_log.md"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M",
)
logger = logging.getLogger(__name__)


def log(level: str, msg: str):
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
    icons = {"INFO":"✅","ERROR":"❌","FIX":"🔧","START":"🚀","DONE":"🎉","WARN":"⚠️"}
    icon  = icons.get(level.upper(), "•")
    logger.info(f"[{level}] {msg}")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{now}] {icon} {level.upper():<6} {msg}\n")
    except Exception:
        pass


# ── 설정 로더 ─────────────────────────────────────────────────────────────────

def load_config(config_path: str = "band_config.yaml") -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"설정 파일 없음: {config_path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────────────────────────────
# 1. BandAPICollector — 공식 API 게시물 수집
# ─────────────────────────────────────────────────────────────────────────────

class BandAPICollector:
    """
    Band Open API 로 게시물을 수집합니다.
    증분 동기화: 마지막 수집 timestamp 이후 신규 게시물만 가져옵니다.
    """

    CURSOR_FILE = Path("band_cursor.json")  # 마지막 수집 위치 저장

    def __init__(self, config: dict):
        self.band_key: str   = config["band"]["band_key"]
        self.max_posts: int  = config["schedule"].get("max_posts_per_run", 50)
        self.client          = BandAPIClient.from_config(
            config.get("config_path", "band_config.yaml")
        )

    # ── 커서 관리 (증분 동기화) ───────────────────────────────────────────────

    def _load_cursor(self) -> Optional[int]:
        """마지막 수집 게시물의 created_at timestamp 로드"""
        if self.CURSOR_FILE.exists():
            return json.loads(self.CURSOR_FILE.read_text(encoding="utf-8")).get("last_ts")
        return None

    def _save_cursor(self, posts: list[dict]):
        """수집된 게시물 중 가장 오래된 것의 timestamp 저장"""
        if not posts:
            return
        # API는 최신순 반환이므로 마지막 항목이 가장 오래됨
        last_ts = posts[-1].get("created_at")
        if last_ts:
            self.CURSOR_FILE.write_text(
                json.dumps({"last_ts": last_ts, "saved_at": datetime.now().isoformat()},
                           ensure_ascii=False),
                encoding="utf-8",
            )

    # ── 수집 ─────────────────────────────────────────────────────────────────

    def fetch(self) -> list[dict]:
        """
        신규 게시물 수집 (증분).
        Returns: band_sync 공통 포맷의 게시물 목록
        """
        log("START", "밴드 게시물 수집 시작 (공식 API)")

        after_ts = self._load_cursor()
        if after_ts:
            log("INFO", f"증분 수집 — {datetime.fromtimestamp(after_ts/1000).strftime('%Y-%m-%d %H:%M')} 이후 게시물")
        else:
            log("INFO", "전체 수집 — 최초 실행")

        try:
            raw_posts = self.client.get_all_posts(
                band_key  = self.band_key,
                max_posts = self.max_posts,
                after_ts  = after_ts,
            )
        except BandAuthError as e:
            log("ERROR", f"인증 오류: {e}")
            raise
        except BandAPIError as e:
            log("ERROR", f"API 오류: {e}")
            raise

        parsed = [BandAPIClient.parse_post(r) for r in raw_posts]
        self._save_cursor(raw_posts)

        log("INFO", f"게시물 {len(parsed)}건 수집 완료")
        return parsed


# ─────────────────────────────────────────────────────────────────────────────
# 2. ObsidianLinker — 처방 감지 + .md 파일 링크 삽입
# ─────────────────────────────────────────────────────────────────────────────

class ObsidianLinker:
    """
    수집된 게시물에서 처방명을 감지하고
    해당 Obsidian .md 파일의 ### 치험례 섹션에 치험례 항목을 삽입합니다.

    삽입 형식 (vault 기존 형식 준수):
        N. [남 81세 BMI 22.5 정상 / 어지러움, 두통, 전신피로](https://band.us/...)
    """

    SECTION_HEADER = "### 치험례"
    SEEN_FILE      = Path("seen_posts.json")

    # ── 환자정보 추출 정규식 (vault_parser.py 와 동일) ─────────────────────
    _SEX_RE          = re.compile(r"(남성|여성|남자|여자|남|여)")
    _AGE_RE          = re.compile(r"(\d{1,3})\s*세|(\d{1,2})\s*대\s*([초중후]반?)?")
    _BMI_RE          = re.compile(r"BMI\s*([\d.]+)\s*([\w가-힣]*)")
    _CONSTITUTION_RE = re.compile(r"(태양인|태음인|소양인|소음인)")

    # ── 증상 추출 패턴 ────────────────────────────────────────────────────────
    _SYMPTOM_PATTERNS = [
        re.compile(r"증상[:\s]+([^\n]+)"),
        re.compile(r"주소[:\s]+([^\n]+)"),
        re.compile(r"주증[:\s]+([^\n]+)"),
        re.compile(r"진단[:\s]+([^\n]+)"),
        re.compile(r"C/C[:\s]+([^\n]+)", re.IGNORECASE),
    ]

    def __init__(self, config: dict):
        self.vault_path: Path = Path(config["obsidian"]["vault_path"])
        presc_cfg = config["obsidian"]["prescriptions"]
        if presc_cfg == "auto":
            from vault_parser import VaultParser
            parser = VaultParser(str(self.vault_path))
            self.prescriptions = [p.name for p in parser.parse_all()]
            log("INFO", f"처방명 자동 로드: {len(self.prescriptions)}개")
        else:
            self.prescriptions = presc_cfg
        self._seen: set[str] = self._load_seen()

    # ── 중복 추적 ─────────────────────────────────────────────────────────────

    def _load_seen(self) -> set[str]:
        if self.SEEN_FILE.exists():
            return set(json.loads(self.SEEN_FILE.read_text(encoding="utf-8")))
        return set()

    def _save_seen(self):
        self.SEEN_FILE.write_text(
            json.dumps(sorted(self._seen), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 처방명 감지 ───────────────────────────────────────────────────────────

    def detect_prescriptions(self, text: str) -> list[str]:
        return [p for p in self.prescriptions if re.search(re.escape(p), text)]

    # ── 환자정보 추출 ─────────────────────────────────────────────────────────

    def extract_patient_info(self, text: str) -> str:
        """
        게시물 내용에서 환자정보를 추출하여 vault 형식 문자열로 조합.
        예: "남 81세 BMI 22.5 정상" 또는 "여 57세 소양인"
        """
        parts = []

        # 성별
        m = self._SEX_RE.search(text)
        if m:
            sex = m.group(1)
            # 정규화: 남성→남, 여성→여, 남자→남, 여자→여
            sex = "남" if sex.startswith("남") else "여"
            parts.append(sex)

        # 나이
        m = self._AGE_RE.search(text)
        if m:
            if m.group(1):
                parts.append(f"{m.group(1)}세")
            elif m.group(2):
                age_str = f"{m.group(2)}대"
                if m.group(3):
                    age_str += m.group(3)
                parts.append(age_str)

        # 체질
        m = self._CONSTITUTION_RE.search(text)
        if m:
            parts.append(m.group(1))

        # BMI
        m = self._BMI_RE.search(text)
        if m:
            bmi_val = m.group(1)
            bmi_class = m.group(2).strip() if m.group(2) else ""
            bmi_str = f"BMI {bmi_val}"
            if bmi_class:
                bmi_str += f" {bmi_class}"
            parts.append(bmi_str)

        return " ".join(parts) if parts else "정보미상"

    # ── 증상 추출 ─────────────────────────────────────────────────────────────

    def extract_symptoms(self, text: str) -> str:
        """게시물에서 증상/주소/진단 키워드 추출"""
        for pat in self._SYMPTOM_PATTERNS:
            m = pat.search(text)
            if m:
                s = m.group(1).strip()
                # 불필요한 뒤쪽 잘라내기 (처방명이 나오면 거기서 끊기)
                for sep in ["처방:", "처방 :", "→", "투약:"]:
                    if sep in s:
                        s = s[:s.index(sep)].strip().rstrip(",. ")
                        break
                return s[:80] + ("..." if len(s) > 80 else "")

        # fallback: 게시물 첫 번째 줄에서 유의미한 텍스트 추출
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for line in lines[:5]:
            # 처방명만 있는 줄은 스킵
            if len(line) < 6:
                continue
            # 환자 정보/증상이 포함된 줄 찾기
            if any(kw in line for kw in ["세 ", "세,", "남 ", "여 ", "통증", "불편", "증상"]):
                return line[:80] + ("..." if len(line) > 80 else "")

        return "상세 내용 링크 참조"

    # ── 치험례 항목 조합 ─────────────────────────────────────────────────────

    def _build_case_entry(self, number: int, post: dict) -> str:
        """
        vault 형식에 맞는 치험례 항목 생성.
        형식: N. [환자정보 / 증상](URL)
        """
        patient_info = self.extract_patient_info(post["content"])
        symptoms     = self.extract_symptoms(post["content"])
        return f"{number}. [{patient_info} / {symptoms}]({post['url']})"

    # ── 파일에 링크 삽입 ──────────────────────────────────────────────────────

    def insert_link(self, prescription: str, post: dict) -> bool:
        key = f"{prescription}::{post['post_id']}"
        if key in self._seen:
            return False

        md_file = self._find_file(prescription)
        if not md_file:
            log("WARN", f"처방 파일 없음: {prescription}")
            return False

        try:
            content = md_file.read_text(encoding="utf-8")
            next_num = self._get_next_case_number(content)
            entry    = self._build_case_entry(next_num, post)
            updated  = self._insert_into_section(content, entry)
            md_file.write_text(updated, encoding="utf-8")
            self._seen.add(key)
            self._save_seen()
            log("INFO", f"치험례 삽입: {prescription} #{next_num} ← {post['url'][:50]}")
            return True
        except Exception as e:
            log("ERROR", f"파일 쓰기 실패 ({prescription}): {e}")
            return False

    def _find_file(self, prescription: str) -> Optional[Path]:
        # 정확한 파일명 매칭 (하위 디렉토리 포함)
        for f in self.vault_path.rglob("*.md"):
            # "상통-001 신력탕.md" → stem에서 처방명 부분 추출
            stem = f.stem
            # 코드-번호 뒤의 처방명과 일치하는지 확인
            if stem.endswith(prescription):
                return f
            if prescription == stem:
                return f
        return None

    def _get_next_case_number(self, content: str) -> int:
        """기존 치험례의 마지막 번호를 찾아 다음 번호 반환"""
        if self.SECTION_HEADER not in content:
            return 1
        section_start = content.index(self.SECTION_HEADER) + len(self.SECTION_HEADER)
        after = content[section_start:]
        # 다음 ### 섹션이 나오면 거기까지만
        next_section = re.search(r"\n###\s", after)
        if next_section:
            after = after[:next_section.start()]
        # "N. [" 패턴에서 최대 번호 찾기
        numbers = re.findall(r"^(\d+)\.\s*\[", after, re.MULTILINE)
        if numbers:
            return max(int(n) for n in numbers) + 1
        return 1

    def _insert_into_section(self, content: str, entry: str) -> str:
        """### 치험례 섹션 끝에 새 항목 삽입"""
        if self.SECTION_HEADER not in content:
            # 섹션이 없으면 파일 끝에 추가
            return content.rstrip() + f"\n\n{self.SECTION_HEADER}\n{entry}\n"

        header_pos = content.index(self.SECTION_HEADER)
        before     = content[:header_pos]
        after      = content[header_pos + len(self.SECTION_HEADER):]

        # 다음 ### 섹션의 위치 찾기
        next_section = re.search(r"\n(###\s)", after)
        if next_section:
            # 치험례 섹션 내용 + 새 항목 + 나머지 섹션
            case_block   = after[:next_section.start()]
            rest         = after[next_section.start():]
            # 기존 항목 마지막 줄 뒤에 삽입
            case_block   = case_block.rstrip() + "\n" + entry + "\n"
            return before + self.SECTION_HEADER + case_block + rest
        else:
            # 치험례가 파일 마지막 섹션인 경우
            return before + self.SECTION_HEADER + after.rstrip() + "\n" + entry + "\n"

    # ── 일괄 처리 ─────────────────────────────────────────────────────────────

    def process_posts(self, posts: list[dict]) -> dict:
        stats = {"inserted": 0, "skipped": 0, "errors": 0}
        for post in posts:
            found = self.detect_prescriptions(post["content"])
            if not found:
                stats["skipped"] += 1
                continue
            for presc in found:
                try:
                    if self.insert_link(presc, post):
                        stats["inserted"] += 1
                    else:
                        stats["skipped"] += 1
                except Exception as e:
                    log("ERROR", f"처리 오류: {e}")
                    stats["errors"] += 1
        log("INFO", f"처리 완료 — 삽입:{stats['inserted']} 스킵:{stats['skipped']} 오류:{stats['errors']}")
        return stats


# ─────────────────────────────────────────────────────────────────────────────
# 3. SyncScheduler — 주기 실행 관리
# ─────────────────────────────────────────────────────────────────────────────

class SyncScheduler:
    """
    APScheduler 기반 주기적 동기화.
    band_config.yaml 의 schedule.cron 에 따라 반복 실행.
    """

    def __init__(self, config: dict):
        self.config    = config
        self.collector = BandAPICollector(config)
        self.linker    = ObsidianLinker(config)
        self.cron: str = config["schedule"].get("cron", "0 */6 * * *")
        self._scheduler = BlockingScheduler(timezone="Asia/Seoul")

    def run_once(self) -> dict:
        """단발 동기화 (수동 실행 / 테스트)"""
        log("START", "밴드 동기화 시작 (공식 API)")
        posts = self.collector.fetch()
        stats = self.linker.process_posts(posts)
        log("DONE", f"동기화 완료: {stats}")
        return stats

    def start(self):
        """스케줄러 시작 (blocking — 종료: Ctrl+C)"""
        cron_parts = self.cron.split()
        trigger = CronTrigger(
            minute=cron_parts[0], hour=cron_parts[1],
            day=cron_parts[2],   month=cron_parts[3],
            day_of_week=cron_parts[4], timezone="Asia/Seoul",
        )
        self._scheduler.add_job(self.run_once, trigger, id="band_sync")
        log("START", f"동기화 스케줄러 시작 — cron: {self.cron}")
        try:
            self._scheduler.start()
        except KeyboardInterrupt:
            log("INFO", "스케줄러 종료")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys

    parser = argparse.ArgumentParser(description="밴드 → Obsidian 치험례 동기화 (공식 API)")
    parser.add_argument("--config",   default="band_config.yaml")
    parser.add_argument("--once",     action="store_true", help="단발 실행 후 종료")
    parser.add_argument("--schedule", action="store_true", help="스케줄러 모드 (반복 실행)")
    args = parser.parse_args()

    config = load_config(args.config)
    config["config_path"] = args.config   # BandAPICollector 에 경로 전달

    if args.once:
        SyncScheduler(config).run_once()
    elif args.schedule:
        SyncScheduler(config).start()
    else:
        print("사용법:")
        print("  python band_api.py  --auth    ← 최초 인증 (1회만)")
        print("  python band_api.py  --bands   ← band_key 확인")
        print("  python band_sync.py --once    ← 즉시 1회 동기화")
        print("  python band_sync.py --schedule← 스케줄 반복 실행")
