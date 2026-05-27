"""
Collect BAND posts from the logged-in web UI and insert case links into
prescription markdown files.

This is a local, user-driven fallback for cases where BAND Open API approval is
not available. It does not bypass login, captcha, or private access checks: you
sign in in the opened browser, then the script reads posts visible to that
browser session.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


DEFAULT_BAND_POST_URL = "https://www.band.us/band/12411046/post"
DEFAULT_PROFILE_DIR = Path(".band_browser_profile")
DEFAULT_EXPORT_DIR = Path("band_web_exports")
DEFAULT_SEEN_FILE = Path("band_web_seen.json")
DEFAULT_VAULT_PATH = Path("방약합편")
CASE_HEADER = "### 치험례"
ROLE_SYMPTOMS = {"공동리더", "리더", "멤버", "운영자", "관리자"}
NON_CASE_HINTS = {
    "강의",
    "스터디",
    "보고",
    "참가자",
    "일시",
    "방식",
    "구성",
    "조문",
    "계통처방",
    "처방에 대한",
    "매일듣기",
    "방약합편",
}


@dataclass
class BandPost:
    post_id: str
    url: str
    content: str
    created_at: str | None = None
    created_label: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="BAND web posts -> prescription markdown case links"
    )
    parser.add_argument(
        "--band-url",
        default=DEFAULT_BAND_POST_URL,
        help="Target BAND post-list URL. Example: https://www.band.us/band/12411046/post",
    )
    parser.add_argument("--since", default="2025-01-01", help="Start date, YYYY-MM-DD")
    parser.add_argument(
        "--until",
        default=date.today().isoformat(),
        help="End date, YYYY-MM-DD. Default: today.",
    )
    parser.add_argument("--vault", default=str(DEFAULT_VAULT_PATH), help="Prescription md root")
    parser.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR), help="Browser profile dir")
    parser.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR), help="Local export dir")
    parser.add_argument("--seen-file", default=str(DEFAULT_SEEN_FILE), help="Deduplication file")
    parser.add_argument("--max-scrolls", type=int, default=250, help="Maximum feed scrolls")
    parser.add_argument("--scroll-wait-ms", type=int, default=1200, help="Delay after each scroll")
    parser.add_argument(
        "--hydrate-full-posts",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Open each collected post URL and save the expanded full text. Default: on.",
    )
    parser.add_argument(
        "--post-detail-wait-ms",
        type=int,
        default=700,
        help="Delay after opening each post detail page before extracting text.",
    )
    parser.add_argument(
        "--post-detail-limit",
        type=int,
        default=0,
        help="Limit detail-page hydration count for testing. 0 means all posts.",
    )
    parser.add_argument(
        "--wait-login-secs",
        type=int,
        default=900,
        help="When redirected to BAND login, wait this many seconds for manual login (default: 900).",
    )
    parser.add_argument(
        "--click-load-more",
        action="store_true",
        help="Click explicit load-more buttons. Default is off because BAND sidebars can navigate to albums.",
    )
    parser.add_argument(
        "--pause-after-open",
        action="store_true",
        help="Pause after opening the browser so you can log in or move to a BAND page.",
    )
    parser.add_argument(
        "--insert",
        action="store_true",
        help="Insert collected posts into matching prescription markdown files.",
    )
    parser.add_argument(
        "--include-undated",
        action="store_true",
        default=True,
        help="Keep posts whose date label cannot be parsed. Default: on.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser headlessly after a login profile already exists.",
    )
    parser.add_argument(
        "--repair-existing",
        action="store_true",
        help="Repair existing BAND case labels from a saved export without opening the browser.",
    )
    parser.add_argument(
        "--repair-export",
        default="",
        help="Export JSON to use with --repair-existing. Default: latest band_web_exports/band_posts_*.json",
    )
    parser.add_argument(
        "--hydrate-export",
        default="",
        help="Open an existing export JSON and replace truncated post text from detail pages without scrolling.",
    )
    parser.add_argument(
        "--hydrate-output",
        default="",
        help="Output JSON path for --hydrate-export. Default: overwrite the input after creating a .bak file.",
    )
    parser.add_argument(
        "--backup-hydrate-export",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Create a .bak backup before overwriting --hydrate-export. Default: on.",
    )
    parser.add_argument(
        "--cleanup-label-prefixes",
        action="store_true",
        help="Remove leading labels such as (투약2) from existing BAND case link symptoms.",
    )
    parser.add_argument(
        "--prune-mismatched-existing",
        action="store_true",
        help="Remove existing BAND case links from files that are no longer matched by the refined prescription detector.",
    )
    return parser.parse_args()


def parse_date(value: str, *, today: date | None = None) -> date | None:
    """Parse common BAND date labels from visible text."""
    if not value:
        return None

    today = today or date.today()
    text = " ".join(value.split())

    iso_match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if iso_match:
        return _safe_date(*map(int, iso_match.groups()))

    dotted_match = re.search(r"(\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})", text)
    if dotted_match:
        return _safe_date(*map(int, dotted_match.groups()))

    korean_match = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
    if korean_match:
        return _safe_date(*map(int, korean_match.groups()))

    short_match = re.search(r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
    if short_match:
        month, day = map(int, short_match.groups())
        parsed = _safe_date(today.year, month, day)
        if parsed and parsed > today + timedelta(days=1):
            parsed = _safe_date(today.year - 1, month, day)
        return parsed

    if "오늘" in text:
        return today
    if "어제" in text:
        return today - timedelta(days=1)

    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def normalize_band_url(url: str) -> str:
    """Prefer the post-list tab, not albums/photos or a generic band home."""
    url = (url or DEFAULT_BAND_POST_URL).strip()
    band_page = re.match(r"^(https?://(?:www\.)?band\.us/band/\d+)(?:/.*)?$", url)
    if band_page:
        return f"{band_page.group(1)}/post"
    return url


def choose_band_page(context, fallback_page, target_url: str):
    target_base_match = re.match(r"^(https?://(?:www\.)?band\.us/band/\d+)", target_url)
    target_base = target_base_match.group(1) if target_base_match else ""

    pages = list(context.pages)
    for candidate in reversed(pages):
        if normalize_band_url(candidate.url) == target_url:
            return candidate

    if target_base:
        for candidate in reversed(pages):
            if candidate.url.startswith(target_base):
                return candidate

    return fallback_page


def same_url_without_query(left: str, right: str) -> bool:
    left_base = left.split("#", 1)[0].split("?", 1)[0].rstrip("/")
    right_base = right.split("#", 1)[0].split("?", 1)[0].rstrip("/")
    return left_base == right_base


def force_post_page(page, target_url: str):
    target_url = normalize_band_url(target_url)
    if is_band_login_url(page.url):
        return page
    if not same_url_without_query(page.url, target_url):
        print(f"게시글 목록으로 이동합니다: {target_url}")
        safe_goto(page, target_url)
    return page


def is_band_login_url(url: str) -> bool:
    url = url or ""
    login_markers = [
        "auth.band.us",
        "nid.naver.com",
        "nid.naver.com/oauth2.0",
        "nid.naver.com/nidlogin",
        "nid.naver.com/login",
    ]
    return any(marker in url for marker in login_markers)


def looks_like_band_login_page(page) -> bool:
    if is_band_login_url(page.url):
        return True
    try:
        body_text = page.locator("body").inner_text(timeout=1000)
    except PlaywrightError:
        return False
    login_markers = [
        "네이버로 로그인",
        "이메일로 로그인",
        "휴대폰 번호로 로그인",
        "로그인 상태 유지",
    ]
    return sum(1 for marker in login_markers if marker in body_text) >= 2


def wait_for_manual_login(page, target_url: str, wait_login_secs: int) -> bool:
    ready_count = 0
    for _ in range(16):
        if looks_like_band_login_page(page):
            break
        current_url = page.url or ""
        if current_url and not current_url.startswith("about:blank"):
            ready_count += 1
            if ready_count >= 4:
                return True
        else:
            ready_count = 0
        page.wait_for_timeout(500)

    if not looks_like_band_login_page(page):
        return True
    if wait_login_secs <= 0:
        print("로그인 페이지로 이동되었습니다. --wait-login-secs 값을 늘려 다시 실행하세요.")
        return False

    print(f"로그인이 필요합니다. 브라우저에서 로그인하세요. 최대 {wait_login_secs}초 대기합니다.")
    deadline = time.monotonic() + wait_login_secs

    while time.monotonic() < deadline:
        page.wait_for_timeout(1000)
        current_url = page.url or ""
        if looks_like_band_login_page(page):
            continue

        # 로그인 완료 직후 인증 콜백 이동을 유지해야 하므로 강제 새로고침하지 않는다.
        if current_url.startswith("about:blank"):
            continue
        page.wait_for_timeout(1500)
        if looks_like_band_login_page(page):
            continue
        return True

    print("로그인 대기 시간이 초과되었습니다.")
    return False


def safe_goto(page, url: str) -> bool:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        return True
    except PlaywrightTimeoutError:
        return False
    except PlaywrightError as exc:
        message = str(exc)
        if "interrupted by another navigation" in message:
            return False
        print(f"페이지 이동 중 오류: {message}")
        return False


def extract_posts_from_page(page) -> list[BandPost]:
    try:
        rows = page.evaluate(
            """
            () => {
              const rows = [];
              const seen = new Set();
              const anchors = Array.from(document.querySelectorAll(
                'a[href*="/post/"], a[href*="/band/"][href*="/post/"]'
              ));

              for (const anchor of anchors) {
                const hrefRaw = anchor.getAttribute('href') || '';
                let href = '';
                try {
                  href = new URL(hrefRaw, location.href).href;
                } catch (_) {
                  continue;
                }

                const idMatch = href.match(/\\/post\\/(\\d+)/);
                if (!idMatch || seen.has(idMatch[1])) continue;
                seen.add(idMatch[1]);

                let node = anchor;
                let best = anchor;
                for (let i = 0; i < 10 && node; i += 1) {
                  const text = (node.innerText || '').trim();
                  if (text.length > 100) {
                    best = node;
                    break;
                  }
                  best = node;
                  node = node.parentElement;
                }

                const text = (best.innerText || anchor.innerText || '')
                  .replace(/\\n{3,}/g, '\\n\\n')
                  .trim();
                const timeEl = best.querySelector('time, [datetime], abbr[title]');
                const createdLabel =
                  (timeEl && (timeEl.getAttribute('datetime') || timeEl.getAttribute('title') || timeEl.innerText)) ||
                  '';

                rows.push({
                  post_id: idMatch[1],
                  url: href,
                  content: text,
                  created_label: createdLabel
                });
              }
              return rows;
            }
            """
        )
    except PlaywrightError:
        return []

    posts: list[BandPost] = []
    for row in rows:
        content = normalize_post_text(row.get("content", ""))
        if not content:
            continue
        created_label = row.get("created_label", "") or _first_date_like_text(content)
        parsed_date = parse_date(created_label) or parse_date(content[:500])
        posts.append(
            BandPost(
                post_id=str(row["post_id"]),
                url=row["url"],
                content=content,
                created_at=parsed_date.isoformat() if parsed_date else None,
                created_label=created_label,
            )
        )
    return posts


def normalize_post_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def hydrate_posts_from_detail_pages(
    context,
    posts: list[BandPost],
    args: argparse.Namespace,
    checkpoint_path: Path | None = None,
) -> list[BandPost]:
    if not posts or not args.hydrate_full_posts:
        return posts

    limit = args.post_detail_limit or len(posts)
    detail_page = context.new_page()
    hydrated: list[BandPost] = []

    for index, post in enumerate(posts, start=1):
        if index > limit:
            hydrated.append(post)
            continue

        print(f"[detail {index:03d}/{min(limit, len(posts)):03d}] post={post.post_id}")
        safe_goto(detail_page, post.url)
        if not wait_for_manual_login(detail_page, post.url, args.wait_login_secs):
            hydrated.append(post)
            continue

        if is_band_login_url(detail_page.url):
            hydrated.append(post)
            continue
        if not same_url_without_query(detail_page.url, post.url):
            safe_goto(detail_page, post.url)
        detail_page.wait_for_timeout(args.post_detail_wait_ms)
        snippet = find_post_anchor_snippet(post.content)
        expand_more_buttons(detail_page, snippet=snippet)
        full_content = extract_detail_post_text(detail_page, post)

        if full_content and len(full_content) >= len(post.content):
            created_label = post.created_label or _first_date_like_text(full_content)
            parsed_date = post.created_at or (
                parse_date(created_label) or parse_date(full_content[:500])
            )
            post = BandPost(
                post_id=post.post_id,
                url=post.url,
                content=full_content,
                created_at=parsed_date.isoformat() if isinstance(parsed_date, date) else parsed_date,
                created_label=created_label,
            )

        hydrated.append(post)
        if checkpoint_path and (index % 25 == 0 or index >= min(limit, len(posts))):
            write_posts_to_export_path(hydrated + posts[index:], checkpoint_path)

    try:
        detail_page.close()
    except PlaywrightError:
        pass
    return hydrated


def expand_more_buttons(page, snippet: str = "", rounds: int = 8) -> None:
    for _ in range(rounds):
        try:
            clicked = page.evaluate(
                """
                ({ snippet }) => {
                  const roots = [];
                  if (snippet) {
                    const rootCandidates = Array.from(document.querySelectorAll(
                      'article, [role="article"], main, section, div'
                    ));
                    for (const node of rootCandidates) {
                      const rect = node.getBoundingClientRect();
                      const text = (node.innerText || '').trim();
                      if (rect.width <= 0 || rect.height <= 0) continue;
                      if (!text.includes(snippet)) continue;
                      roots.push({ node, length: text.length });
                    }
                    roots.sort((a, b) => a.length - b.length);
                  }

                  const searchRoots = roots.length
                    ? roots.slice(0, 4).map((row) => row.node)
                    : [document.body];
                  let clicked = 0;

                  for (const root of searchRoots) {
                    const candidates = Array.from(root.querySelectorAll(
                      'button, [role="button"], a, span'
                    ));

                    for (const el of candidates) {
                      const text = (el.innerText || el.textContent || '').trim();
                      const compact = text.replace(/\\s+/g, '');
                      if (!compact || compact.length > 12) continue;
                      if (!['더보기', '...더보기', 'More', 'SeeMore'].includes(compact)) continue;

                      const label = [
                        el.getAttribute('aria-label') || '',
                        el.getAttribute('title') || '',
                        el.closest('[aria-label]')?.getAttribute('aria-label') || '',
                        el.parentElement?.innerText || ''
                      ].join(' ');
                      if (/표정|반응|좋아요|댓글|공유|스티커|이모티콘/.test(label)) continue;

                      const href = el.getAttribute('href') || '';
                      if (href && !href.startsWith('#') && !href.toLowerCase().startsWith('javascript')) {
                        continue;
                      }

                      const rect = el.getBoundingClientRect();
                      if (rect.width <= 0 || rect.height <= 0) continue;

                      el.click();
                      clicked += 1;
                    }
                  }
                  return clicked;
                }
                """,
                {"snippet": snippet},
            )
        except PlaywrightError:
            return

        if not clicked:
            return
        page.wait_for_timeout(350)


def extract_detail_post_text(page, fallback: BandPost) -> str:
    snippet = find_post_anchor_snippet(fallback.content)
    try:
        candidates = page.evaluate(
            """
            ({ snippet }) => {
              const selectors = 'article, [role="article"], main, section, div';
              const nodes = [document.body, ...Array.from(document.querySelectorAll(selectors))];
              return nodes
                .map((node) => {
                  const rect = node.getBoundingClientRect();
                  const text = (node.innerText || '').trim();
                  return {
                    text,
                    tag: node.tagName,
                    visible: rect.width > 0 && rect.height > 0,
                    hasTime: !!node.querySelector('time, [datetime], abbr[title]'),
                    containsSnippet: snippet ? text.includes(snippet) : false
                  };
                })
                .filter((row) => row.visible && row.text);
            }
            """,
            {"snippet": snippet},
        )
    except PlaywrightError:
        return ""

    best = choose_detail_text_candidate(candidates, fallback, snippet)
    return trim_detail_post_text(best, fallback, snippet)


def fallback_post_meta_lines(fallback: BandPost) -> list[str]:
    lines = normalize_post_text(fallback.content).split("\n")
    if len(lines) >= 3 and lines[0] in {"공동리더", "리더", "멤버", "운영자", "관리자"}:
        return lines[:3]
    if len(lines) >= 2 and re.search(r"\d{4}\s*년|\d{1,2}\s*시간 전|오전|오후", lines[1]):
        return lines[:2]
    return []


def is_detail_control_line(line: str) -> bool:
    text = line.strip()
    if not text:
        return False
    if text in {"글 옵션", "표정짓기", "댓글쓰기", "댓글을 남겨주세요."}:
        return True
    if re.fullmatch(r"(?:좋아요|최고예요|재밌어요|놀랐어요|슬퍼요|응원해요|슬퍼요|화나요)(?:\s+\S+){0,4}", text):
        return True
    if re.search(r"(?:^|\s)댓글\s*\d+\s*$", text) and re.search(r"\d", text):
        return True
    return False


def is_reaction_tail_line(line: str) -> bool:
    text = line.strip()
    if not text:
        return True
    if is_detail_control_line(text):
        return True
    if re.fullmatch(r"\d+", text):
        return True
    if text in {"좋아요", "최고예요", "재밌어요", "놀랐어요", "슬퍼요", "응원해요", "화나요"}:
        return True
    return False


def trim_detail_post_text(text: str, fallback: BandPost, snippet: str) -> str:
    normalized = normalize_post_text(text)
    if not normalized:
        return ""

    lines = normalized.split("\n")
    snippet = snippet.strip()
    start_idx = 0
    if snippet:
        for idx, line in enumerate(lines):
            if snippet in line:
                start_idx = idx
                break

    stop_idx = len(lines)
    for idx in range(start_idx, len(lines)):
        if is_detail_control_line(lines[idx]):
            stop_idx = idx
            break

    body_lines = lines[start_idx:stop_idx]
    while body_lines and is_reaction_tail_line(body_lines[-1]):
        body_lines.pop()

    cleaned_lines = []
    for line in body_lines:
        cleaned = line.replace("...더보기", "").replace("더보기", "").strip()
        if cleaned:
            cleaned_lines.append(cleaned)

    if not cleaned_lines:
        return normalize_post_text(fallback.content)

    meta_lines = fallback_post_meta_lines(fallback)
    if cleaned_lines[: len(meta_lines)] == meta_lines:
        result_lines = cleaned_lines
    else:
        result_lines = meta_lines + cleaned_lines
    return "\n".join(result_lines).strip()


def find_post_anchor_snippet(text: str) -> str:
    skip_words = {
        "공동리더",
        "리더",
        "멤버",
        "운영자",
        "관리자",
        "채팅",
        "댓글",
        "좋아요",
        "공유",
        "...더보기",
        "더보기",
    }
    lines = normalize_post_text(text).split("\n")
    meta_cutoff = 3 if lines and lines[0] in {"공동리더", "리더", "멤버", "운영자", "관리자"} else 2

    for idx, line in enumerate(lines):
        line = line.strip()
        if idx < meta_cutoff:
            continue
        if len(line) < 6:
            continue
        if line in skip_words:
            continue
        if re.search(r"\d{4}\s*년|\d{1,2}\s*시간 전|오전|오후", line):
            continue
        return line[:80]
    return ""


def choose_detail_text_candidate(candidates: list[dict], fallback: BandPost, snippet: str) -> str:
    fallback_text = normalize_post_text(fallback.content)
    fallback_len = len(fallback_text)
    nav_penalty_words = ["최근 사진", "새 채팅", "그룹콜", "밴드 전체 멤버", "파일", "원글 보기"]

    viable = []
    for row in candidates:
        text = normalize_post_text(row.get("text", ""))
        if not text:
            continue
        if snippet and snippet not in text:
            continue
        if len(text) < max(40, fallback_len):
            continue

        trimmed = trim_detail_post_text(text, fallback, snippet)
        if len(trimmed) < max(40, fallback_len):
            continue
        penalty = sum(5000 for word in nav_penalty_words if word in text)
        score = len(trimmed) - penalty
        if row.get("hasTime"):
            score += 600
        if "...더보기" not in trimmed and "더보기" not in trimmed:
            score += 300
        viable.append((score, len(trimmed), text))

    if viable:
        viable.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return viable[0][2]

    scored = []
    for row in candidates:
        text = normalize_post_text(row.get("text", ""))
        if len(text) < max(40, fallback_len):
            continue
        penalty = sum(5000 for word in nav_penalty_words if word in text)
        score = len(trim_detail_post_text(text, fallback, snippet)) - penalty
        if row.get("hasTime"):
            score += 600
        scored.append((score, text))

    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]

    return fallback_text


def _first_date_like_text(text: str) -> str:
    patterns = [
        r"\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}",
        r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일",
        r"\d{1,2}\s*월\s*\d{1,2}\s*일",
        r"오늘|어제",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return ""


def collect_posts(args: argparse.Namespace) -> list[BandPost]:
    since = date.fromisoformat(args.since)
    until = date.fromisoformat(args.until)
    profile_dir = Path(args.profile_dir)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=args.headless,
            viewport={"width": 1440, "height": 950},
            locale="ko-KR",
        )
        page = context.pages[0] if context.pages else context.new_page()
        target_url = normalize_band_url(args.band_url)
        safe_goto(page, target_url)
        if not wait_for_manual_login(page, target_url, args.wait_login_secs):
            context.close()
            return []

        if args.pause_after_open:
            print("\n브라우저에서 BAND 로그인 후 대상 밴드 게시글 목록을 확인하세요.")
            print(f"반드시 이 주소에서 수집합니다: {target_url}")
            input("준비되면 Enter를 누르세요: ")

        page = choose_band_page(context, page, target_url)
        page = force_post_page(page, target_url)

        collected: dict[str, BandPost] = {}
        stale_rounds = 0

        for scroll_no in range(1, args.max_scrolls + 1):
            if not wait_for_manual_login(page, target_url, args.wait_login_secs):
                break
            page = force_post_page(page, target_url)
            if not wait_for_manual_login(page, target_url, args.wait_login_secs):
                break
            page.wait_for_timeout(args.scroll_wait_ms)
            if not wait_for_manual_login(page, target_url, args.wait_login_secs):
                break
            before = len(collected)

            for post in extract_posts_from_page(page):
                parsed = date.fromisoformat(post.created_at) if post.created_at else None
                if parsed and (parsed < since or parsed > until):
                    continue
                if not parsed and not args.include_undated:
                    continue
                collected[post.post_id] = post

            added = len(collected) - before
            print(f"[scroll {scroll_no:03d}] collected={len(collected)} added={added} url={page.url}")

            if args.click_load_more:
                _click_load_more_if_visible(page)
            page.mouse.wheel(0, 2600)
            page.wait_for_timeout(args.scroll_wait_ms)
            if not same_url_without_query(page.url, target_url):
                print(f"게시글이 아닌 탭으로 이동되어 복귀합니다: {page.url}")
                safe_goto(page, target_url)
                if not wait_for_manual_login(page, target_url, args.wait_login_secs):
                    break

            oldest = _oldest_dated(collected.values())
            if oldest and oldest < since:
                stale_rounds += 1
            elif added == 0:
                stale_rounds += 1
            else:
                stale_rounds = 0

            if stale_rounds >= 8:
                break

        posts = sorted(
            collected.values(),
            key=lambda p: (p.created_at or "9999-99-99", p.post_id),
            reverse=True,
        )
        posts = hydrate_posts_from_detail_pages(context, posts, args)
        context.close()

    return sorted(
        posts,
        key=lambda p: (p.created_at or "9999-99-99", p.post_id),
        reverse=True,
    )


def _click_load_more_if_visible(page) -> None:
    try:
        for label in ["더보기", "More", "Load more"]:
            locator = page.get_by_text(label, exact=False).last
            if locator.count() > 0:
                locator.click(timeout=1000)
                return
    except PlaywrightTimeoutError:
        return
    except Exception:
        return


def _oldest_dated(posts: Iterable[BandPost]) -> date | None:
    dates = [date.fromisoformat(p.created_at) for p in posts if p.created_at]
    return min(dates) if dates else None


def save_posts(posts: list[BandPost], export_dir: Path, since: str, until: str) -> Path:
    export_dir.mkdir(parents=True, exist_ok=True)
    output = export_dir / f"band_posts_{since}_to_{until}.json"
    write_posts_to_export_path(posts, output)
    return output


def write_posts_to_export_path(posts: list[BandPost], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([asdict(p) for p in posts], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    jsonl = output.with_suffix(".jsonl")
    with jsonl.open("w", encoding="utf-8") as f:
        for post in posts:
            f.write(json.dumps(asdict(post), ensure_ascii=False) + "\n")


def load_posts_from_export(export_path: Path) -> list[BandPost]:
    rows = json.loads(export_path.read_text(encoding="utf-8"))
    return [BandPost(**row) for row in rows]


def count_more_markers(posts: list[BandPost]) -> int:
    more = "\ub354\ubcf4\uae30"
    return sum(more in (post.content or "") for post in posts)


def hydrate_export_file(args: argparse.Namespace) -> int:
    export_path = Path(args.hydrate_export)
    if not export_path.exists():
        print(f"hydrate export file not found: {export_path}")
        return 1

    posts = load_posts_from_export(export_path)
    if not posts:
        print(f"hydrate export has no posts: {export_path}")
        return 1

    before_more = count_more_markers(posts)
    output_path = Path(args.hydrate_output) if args.hydrate_output else export_path
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(Path(args.profile_dir)),
            headless=args.headless,
            viewport={"width": 1440, "height": 950},
            locale="ko-KR",
        )
        page = context.pages[0] if context.pages else context.new_page()
        first_url = posts[0].url or normalize_band_url(args.band_url)
        safe_goto(page, first_url)
        if not wait_for_manual_login(page, first_url, args.wait_login_secs):
            context.close()
            return 1

        hydrated = hydrate_posts_from_detail_pages(context, posts, args, output_path)
        try:
            context.close()
        except PlaywrightError:
            pass

    after_more = count_more_markers(hydrated)
    if output_path.resolve() == export_path.resolve() and args.backup_hydrate_export:
        backup_path = export_path.with_suffix(export_path.suffix + ".bak")
        if not backup_path.exists():
            shutil.copy2(export_path, backup_path)
            jsonl_path = export_path.with_suffix(".jsonl")
            if jsonl_path.exists():
                shutil.copy2(jsonl_path, jsonl_path.with_suffix(jsonl_path.suffix + ".bak"))
            print(f"backup={backup_path}")

    write_posts_to_export_path(hydrated, output_path)
    print(f"hydrate_export={export_path}")
    print(f"hydrate_output={output_path}")
    print(f"rows={len(hydrated)} before_more={before_more} after_more={after_more}")
    return 0


def latest_export_path(export_dir: Path) -> Path:
    exports = sorted(export_dir.glob("band_posts_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not exports:
        raise FileNotFoundError(f"No band_posts_*.json files found in {export_dir}")
    return exports[0]


def load_prescription_index(vault_path: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for md_file in vault_path.rglob("*.md"):
        name = _prescription_name_from_file(md_file)
        if not name:
            continue
        aliases = {name}
        aliases.update(part.strip() for part in re.split(r"[=,]", name) if part.strip())
        aliases.add(re.sub(r"\(=.+?\)", "", name).strip())
        for alias in aliases:
            if alias:
                index.setdefault(alias, md_file)
    return dict(sorted(index.items(), key=lambda item: len(item[0]), reverse=True))


def _prescription_name_from_file(md_file: Path) -> str:
    stem = md_file.stem
    match = re.match(r"^(?:상통|중통|하통)-\d{3}(?:-\d{3})?\s+(.+)$", stem)
    if match:
        return match.group(1).strip()
    return ""


def insert_posts(posts: list[BandPost], vault_path: Path, seen_file: Path) -> dict[str, int]:
    index = load_prescription_index(vault_path)
    seen = _load_seen(seen_file)
    stats = {"inserted": 0, "skipped": 0, "unmatched": 0}

    for post in posts:
        matches = detect_prescription_matches(post.content, index)
        if not matches:
            stats["unmatched"] += 1
            continue

        for md_file, alias in matches:
            if not is_treatment_symptom_text(extract_symptoms(post.content, alias)):
                stats["unmatched"] += 1
                continue
            key = f"{post.post_id}::{md_file.as_posix()}"
            if key in seen:
                stats["skipped"] += 1
                continue
            if insert_case_entry(md_file, post, alias):
                seen.add(key)
                stats["inserted"] += 1
            else:
                stats["skipped"] += 1

    seen_file.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def _load_seen(seen_file: Path) -> set[str]:
    if seen_file.exists():
        return set(json.loads(seen_file.read_text(encoding="utf-8")))
    return set()


def detect_prescription_matches(text: str, index: dict[str, Path]) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    seen_paths: set[Path] = set()
    covered_spans: list[tuple[int, int]] = []
    for alias, md_file in index.items():
        if len(alias) < 2:
            continue

        for match in re.finditer(re.escape(alias), text):
            span = match.span()
            if any(span[0] >= start and span[1] <= end for start, end in covered_spans):
                continue
            if md_file not in seen_paths:
                found.append((md_file, alias))
                seen_paths.add(md_file)
                covered_spans.append(span)
            break
    return found


def detect_prescription_files(text: str, index: dict[str, Path]) -> list[Path]:
    return [md_file for md_file, _alias in detect_prescription_matches(text, index)]


def insert_case_entry(md_file: Path, post: BandPost, prescription_name: str = "") -> bool:
    content = md_file.read_text(encoding="utf-8")
    if post.url in content:
        return False

    next_num = next_case_number(content)
    entry = build_case_entry(next_num, post, prescription_name or _prescription_name_from_file(md_file))
    updated = insert_into_case_section(content, entry)
    md_file.write_text(updated, encoding="utf-8")
    return True


def next_case_number(content: str) -> int:
    block = case_section_text(content)
    numbers = re.findall(r"^(\d+)\.\s*\[", block, re.MULTILINE)
    return max(map(int, numbers), default=0) + 1


def case_section_text(content: str) -> str:
    if CASE_HEADER not in content:
        return ""
    start = content.index(CASE_HEADER) + len(CASE_HEADER)
    tail = content[start:]
    next_section = re.search(r"\n###\s+", tail)
    if next_section:
        tail = tail[: next_section.start()]
    return tail


def insert_into_case_section(content: str, entry: str) -> str:
    if CASE_HEADER not in content:
        return content.rstrip() + f"\n\n{CASE_HEADER}\n{entry}\n"

    start = content.index(CASE_HEADER)
    before = content[:start]
    tail = content[start + len(CASE_HEADER) :]
    next_section = re.search(r"\n###\s+", tail)
    if next_section:
        case_block = tail[: next_section.start()].rstrip()
        rest = tail[next_section.start() :]
        return before + CASE_HEADER + case_block + "\n" + entry + "\n" + rest
    return before + CASE_HEADER + tail.rstrip() + "\n" + entry + "\n"


def build_case_entry(number: int, post: BandPost, prescription_name: str = "") -> str:
    patient = extract_patient_info(post.content)
    symptoms = extract_symptoms(post.content, prescription_name)
    return f"{number}. [{patient} / {symptoms}]({post.url})"


def extract_patient_info(text: str) -> str:
    parts: list[str] = []

    sex_match = re.search(r"(남성|여성|남자|여자|남\b|여\b|男|女)", text)
    if sex_match:
        raw = sex_match.group(1)
        if raw in {"남성", "남자", "남", "男"}:
            parts.append("남")
        else:
            parts.append("여")

    age_match = re.search(r"(\d{1,3})\s*(세|대(?:\s*[초중후]반)?)", text)
    if age_match:
        parts.append("".join(age_match.groups()).replace(" ", ""))

    constitution_match = re.search(r"(태양인|태음인|소양인|소음인)", text)
    if constitution_match:
        parts.append(constitution_match.group(1))

    bmi_match = re.search(r"BMI\s*([\d.]+)\s*([가-힣A-Za-z0-9단계\s]*)", text, re.IGNORECASE)
    if bmi_match:
        bmi = f"BMI {bmi_match.group(1)}"
        bmi_class = " ".join(bmi_match.group(2).split())[:12]
        if bmi_class:
            bmi += f" {bmi_class}"
        parts.append(bmi)

    return " ".join(parts) if parts else "정보미상"


def extract_symptoms(text: str, prescription_name: str = "") -> str:
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    aliases = prescription_aliases(prescription_name)
    for line in lines[:24]:
        symptom = extract_prescription_line_symptom(line, aliases)
        if symptom:
            return symptom

    if not aliases:
        for line in lines[:24]:
            symptom = extract_prescription_line_symptom(line, [])
            if symptom:
                return symptom

    patterns = [
        r"(?:증상|주소|주증|진단|C/C)\s*[:：]\s*([^\n]+)",
        r"(?:호소|불편)\s*[:：]\s*([^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            symptom = clean_symptom_text(match.group(1))
            if is_good_symptom_text(symptom):
                return symptom

    skip_words = ["댓글", "좋아요", "공유", "사진", "첨부", "작성", "밴드", "공동리더", "멤버"]
    for line in lines[:12]:
        if len(line) < 8:
            continue
        if any(word in line for word in skip_words):
            continue
        if any(word in line for word in ["통증", "불면", "소화", "피로", "기침", "두통", "복통", "설사", "변비", "증상"]):
            return clean_symptom_text(line)

    fallback = clean_symptom_text(lines[0] if lines else "")
    return fallback if is_good_symptom_text(fallback) else "상세 내용 링크 참조"


def prescription_aliases(prescription_name: str) -> list[str]:
    aliases: set[str] = set()
    name = prescription_name.strip()
    if name:
        aliases.add(name)
        aliases.add(re.sub(r"\(=.+?\)", "", name).strip())
        aliases.update(part.strip() for part in re.split(r"[=,]", name) if part.strip())
    return sorted((alias for alias in aliases if alias), key=len, reverse=True)


def extract_prescription_line_symptom(line: str, aliases: list[str]) -> str:
    line = normalize_prescription_line(line)
    if not line:
        return ""

    if aliases:
        for alias in aliases:
            if alias not in line:
                continue
            raw_tail = line.split(alias, 1)[1]
            has_explicit_separator = bool(
                re.match(r"^\s*(?:\([^)]*\)\s*)?[:：\-–—ㅡ]", raw_tail)
            )
            has_parenthetical_alias_tail = bool(re.match(r"^\s*[)\]}]+\s*\S", raw_tail))
            if not has_explicit_separator and not has_parenthetical_alias_tail:
                colon_match = re.search(r"[:：]\s*(.+)$", line)
                if colon_match and line.index(alias) < colon_match.start():
                    symptom = clean_symptom_text(colon_match.group(1))
                    if is_treatment_symptom_text(symptom):
                        return symptom
                loose_symptom = clean_symptom_text(raw_tail)
                if not re.match(r"^\s*(과|와|및|,|，)", raw_tail) and is_treatment_symptom_text(loose_symptom):
                    return loose_symptom
                continue

            tail = raw_tail
            tail = re.sub(r"^\s*\([^)]*\)\s*", "", tail)
            tail = re.sub(r"^[)\]}]+\s*", "", tail)
            tail = re.sub(r"^\s*[:：\-–—ㅡ]+\s*", "", tail)
            symptom = clean_symptom_text(tail)
            if is_treatment_symptom_text(symptom):
                return symptom

            colon_match = re.search(r"[:：]\s*(.+)$", line)
            if colon_match and line.index(alias) < colon_match.start():
                symptom = clean_symptom_text(colon_match.group(1))
                if is_treatment_symptom_text(symptom):
                    return symptom
        return ""

    colon_match = re.search(r"^(.{2,80}?)(?:\([^)]*\))?\s*[:：]\s*(.+)$", line)
    if not colon_match:
        return ""

    title = colon_match.group(1)
    if not looks_like_prescription_title(title):
        return ""

    symptom = clean_symptom_text(colon_match.group(2))
    return symptom if is_treatment_symptom_text(symptom) else ""


def normalize_prescription_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^[\s>*#\-–—•●○◆◇■□▶▷▸▹※]+", "", line)
    return re.sub(r"\s+", " ", line).strip()


def looks_like_prescription_title(title: str) -> bool:
    title = normalize_prescription_line(title)
    if re.search(r"\d{4}\s*년|\d{1,2}\s*월|\d{1,2}\s*일", title):
        return False
    if re.search(r"\(\d[-\d+]*\)", title):
        return True
    return bool(re.search(r"(탕|산|환|음|고|전|단|원|차|방|제|화)\s*$", title))


def is_good_symptom_text(text: str) -> bool:
    symptom = text.strip()
    if not symptom:
        return False
    if symptom in ROLE_SYMPTOMS:
        return False
    if symptom in {"더보기", "...더보기", "상세 내용 링크 참조"}:
        return False
    return len(symptom) >= 2


def is_treatment_symptom_text(text: str) -> bool:
    symptom = text.strip()
    if not is_good_symptom_text(symptom):
        return False
    if symptom.startswith(("+", "＋")):
        return False
    return not any(hint in symptom for hint in NON_CASE_HINTS)


def clean_symptom_text(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = text.replace("...더보기", "").replace("더보기", "")
    text = re.sub(r"^[\s>*#\-–—•●○◆◇■□▶▷▸▹※]+", "", text)
    text = re.sub(r"^(?:\([^)]{1,20}\)\s*[,/:：\-–—+]*\s*)+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" /,.;")
    for marker in ["처방:", "처방 :", "투약:", "투약 :", "약:", "약 :"]:
        if marker in text:
            text = text.split(marker, 1)[0].strip(" /,.;")
    return text[:90] + ("..." if len(text) > 90 else "")


CASE_LINK_RE = re.compile(
    r"^(?P<number>\d+\.\s*)\[(?P<patient>[^/\]]+?)\s*/\s*(?P<symptom>[^\]]+)\]"
    r"\((?P<url>https?://(?:www\.)?band\.us/band/\d+/post/(?P<post_id>\d+))\)",
    re.MULTILINE,
)
LABEL_PREFIX_RE = re.compile(
    r"(?P<head>^\d+\.\s*\[[^/\]]+?\s*/\s*)"
    r"\((?P<prefix>[^)]{1,30})\)\s*"
    r"(?P<tail>[^\]]+\]\(https?://(?:www\.)?band\.us/band/\d+/post/\d+\))",
    re.MULTILINE,
)


def should_repair_case_symptom(symptom: str) -> bool:
    raw_symptom = symptom.strip()
    if re.match(r"^\([^)]{1,20}\)", raw_symptom):
        return True
    symptom = clean_symptom_text(symptom)
    if symptom in ROLE_SYMPTOMS:
        return True
    return any(role in symptom for role in ROLE_SYMPTOMS)


def repair_existing_case_entries(posts: list[BandPost], vault_path: Path) -> dict[str, int]:
    post_map = {post.post_id: post for post in posts}
    stats = {"updated": 0, "files_changed": 0, "missing_export": 0, "skipped": 0}

    for md_file in vault_path.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        prescription_name = _prescription_name_from_file(md_file)
        file_changed = False

        def replace(match: re.Match[str]) -> str:
            nonlocal file_changed
            symptom = match.group("symptom")
            if not should_repair_case_symptom(symptom):
                stats["skipped"] += 1
                return match.group(0)

            post = post_map.get(match.group("post_id"))
            if not post:
                stats["missing_export"] += 1
                return match.group(0)

            new_patient = extract_patient_info(post.content)
            new_symptom = extract_symptoms(post.content, prescription_name)
            if not is_treatment_symptom_text(new_symptom) or should_repair_case_symptom(new_symptom):
                stats["skipped"] += 1
                return match.group(0)

            file_changed = True
            stats["updated"] += 1
            return f"{match.group('number')}[{new_patient} / {new_symptom}]({match.group('url')})"

        updated = CASE_LINK_RE.sub(replace, content)
        if file_changed:
            md_file.write_text(updated, encoding="utf-8")
            stats["files_changed"] += 1

    return stats


def should_remove_label_prefix(prefix: str) -> bool:
    return bool(
        re.search(r"투약|케이스|case|상통|중통|하통|보감|\d[-\d+]*", prefix, re.IGNORECASE)
    )


def cleanup_existing_label_prefixes(vault_path: Path) -> dict[str, int]:
    stats = {"updated": 0, "files_changed": 0}

    for md_file in vault_path.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        file_changed = False

        def replace(match: re.Match[str]) -> str:
            nonlocal file_changed
            if not should_remove_label_prefix(match.group("prefix")):
                return match.group(0)
            file_changed = True
            stats["updated"] += 1
            return f"{match.group('head')}{match.group('tail')}"

        updated = LABEL_PREFIX_RE.sub(replace, content)
        if file_changed:
            md_file.write_text(updated, encoding="utf-8")
            stats["files_changed"] += 1

    return stats


def prune_mismatched_existing_entries(posts: list[BandPost], vault_path: Path) -> dict[str, int]:
    index = load_prescription_index(vault_path)
    post_map = {post.post_id: post for post in posts}
    stats = {"removed": 0, "files_changed": 0, "missing_export": 0, "kept": 0}

    for md_file in vault_path.rglob("*.md"):
        lines = md_file.read_text(encoding="utf-8").splitlines(keepends=True)
        changed = False
        new_lines: list[str] = []

        for line in lines:
            stripped = line.rstrip("\r\n")
            match = CASE_LINK_RE.match(stripped)
            if not match:
                new_lines.append(line)
                continue

            post = post_map.get(match.group("post_id"))
            if not post:
                stats["missing_export"] += 1
                new_lines.append(line)
                continue

            desired_files = {path for path, _alias in detect_prescription_matches(post.content, index)}
            if desired_files and md_file not in desired_files:
                stats["removed"] += 1
                changed = True
                continue

            stats["kept"] += 1
            new_lines.append(line)

        if changed:
            md_file.write_text("".join(new_lines), encoding="utf-8")
            stats["files_changed"] += 1

    return stats


def main() -> int:
    args = parse_args()

    if args.hydrate_export:
        return hydrate_export_file(args)

    if args.cleanup_label_prefixes:
        stats = cleanup_existing_label_prefixes(Path(args.vault))
        print(f"치험례 링크 앞표지 정리 완료: {stats}")
        return 0

    if args.prune_mismatched_existing:
        export_path = Path(args.repair_export) if args.repair_export else latest_export_path(Path(args.export_dir))
        posts = load_posts_from_export(export_path)
        stats = prune_mismatched_existing_entries(posts, Path(args.vault))
        print(f"불일치 치험례 링크 정리 완료: {stats}")
        print(f"사용한 수집 파일: {export_path}")
        return 0

    if args.repair_existing:
        export_path = Path(args.repair_export) if args.repair_export else latest_export_path(Path(args.export_dir))
        posts = load_posts_from_export(export_path)
        stats = repair_existing_case_entries(posts, Path(args.vault))
        print(f"기존 치험례 정정 완료: {stats}")
        print(f"사용한 수집 파일: {export_path}")
        return 0

    posts = collect_posts(args)
    if not posts:
        print("\n수집된 게시글이 없어 export 파일을 저장하지 않았습니다.")
        print("로그인 후 다시 실행하세요.")
        return 1

    export_path = save_posts(posts, Path(args.export_dir), args.since, args.until)
    print(f"\n수집 완료: {len(posts)}건")
    print(f"저장 위치: {export_path}")

    if args.insert:
        stats = insert_posts(posts, Path(args.vault), Path(args.seen_file))
        print(f"삽입 결과: {stats}")
    else:
        print("md 파일에는 아직 삽입하지 않았습니다. 삽입하려면 --insert를 붙여 다시 실행하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
