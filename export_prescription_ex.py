from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from band_web_sync import (
    BandPost,
    DEFAULT_EXPORT_DIR,
    DEFAULT_VAULT_PATH,
    _prescription_name_from_file,
    detect_prescription_matches,
    extract_patient_info,
    extract_symptoms,
    is_treatment_symptom_text,
    latest_export_path,
    load_prescription_index,
)


ROLE_MARKERS = {"공동리더", "리더", "멤버", "운영자", "관리자"}
DEFAULT_AUTHOR_TOKENS = ["이종대", "이윤호(98) since2002"]
INVALID_FS_CHARS = r'[<>:"/\\|?*]+'


@dataclass
class CaseRecord:
    post_id: str
    author: str
    author_line: str
    prescription_name: str
    matched_alias: str
    patient_info: str
    symptoms: str
    created_at: str
    created_label: str
    url: str
    content: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export case posts by specific BAND authors into prescription_ex folders."
    )
    parser.add_argument(
        "--export-json",
        default="",
        help="Path to BAND export JSON. Default: latest band_web_exports/band_posts_*.json",
    )
    parser.add_argument(
        "--output-dir",
        default="prescription_ex",
        help="Output directory. Default: prescription_ex",
    )
    parser.add_argument("--vault", default=str(DEFAULT_VAULT_PATH), help="Prescription vault root")
    parser.add_argument(
        "--authors",
        default="|".join(DEFAULT_AUTHOR_TOKENS),
        help="Author substrings separated by '|'.",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Delete output directory before exporting.",
    )
    return parser.parse_args()


def safe_name(name: str) -> str:
    cleaned = re.sub(INVALID_FS_CHARS, "_", name).strip()
    cleaned = cleaned.rstrip(". ")
    return cleaned or "unknown_prescription"


def read_posts(export_json: Path) -> list[BandPost]:
    rows = json.loads(export_json.read_text(encoding="utf-8"))
    posts: list[BandPost] = []
    for row in rows:
        posts.append(
            BandPost(
                post_id=str(row.get("post_id", "")),
                url=row.get("url", ""),
                content=row.get("content", ""),
                created_at=row.get("created_at"),
                created_label=row.get("created_label", ""),
            )
        )
    return posts


def extract_author_lines(content: str) -> tuple[str, str]:
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    if not lines:
        return "", ""
    if len(lines) >= 2 and lines[0] in ROLE_MARKERS:
        return lines[1], lines[0]
    if len(lines) >= 2:
        return lines[1], lines[0]
    return lines[0], lines[0]


def write_case_file(case_file: Path, record: CaseRecord) -> None:
    case_text = (
        f"# {record.prescription_name} 치험례\n\n"
        f"- 작성자: {record.author}\n"
        f"- 역할표시: {record.author_line}\n"
        f"- 환자정보: {record.patient_info}\n"
        f"- 주증상: {record.symptoms}\n"
        f"- 작성시각: {record.created_label or record.created_at or '미상'}\n"
        f"- 게시글: {record.url}\n"
        f"- 처방매칭: {record.matched_alias}\n\n"
        "## 원문\n\n"
        "```text\n"
        f"{record.content.strip()}\n"
        "```\n"
    )
    case_file.write_text(case_text, encoding="utf-8")


def write_index_file(folder: Path, prescription_name: str, records: list[CaseRecord]) -> None:
    rows = sorted(records, key=lambda r: (r.created_at or "", r.post_id), reverse=True)
    lines = [f"# {prescription_name} 치험례 모음", "", f"- 총 {len(rows)}건", ""]
    for row in rows:
        lines.append(
            f"- [{row.author} / {row.patient_info} / {row.symptoms}](post_{row.post_id}.md) "
            f"({row.created_at or '날짜미상'})"
        )
    lines.append("")
    (folder / "index.md").write_text("\n".join(lines), encoding="utf-8")


def write_root_summary(output_dir: Path, folder_map: dict[str, list[CaseRecord]]) -> None:
    items = sorted(
        folder_map.items(),
        key=lambda kv: (len(kv[1]), kv[0]),
        reverse=True,
    )
    lines = ["# prescription_ex 요약", "", f"- 처방 폴더 수: {len(items)}", ""]
    for folder_name, records in items:
        lines.append(f"- [{folder_name}]({folder_name}/index.md): {len(records)}건")
    lines.append("")
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    export_json = Path(args.export_json) if args.export_json else latest_export_path(Path(DEFAULT_EXPORT_DIR))
    output_dir = Path(args.output_dir)
    vault_path = Path(args.vault)
    author_tokens = [token.strip() for token in args.authors.split("|") if token.strip()]

    if args.clean_output and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    posts = read_posts(export_json)
    if not posts:
        print(f"export_json={export_json}")
        print("선택한 export에 게시글이 없어 prescription_ex를 생성하지 않았습니다.")
        return 1

    prescription_index = load_prescription_index(vault_path)

    folder_records: dict[str, list[CaseRecord]] = defaultdict(list)
    stats = {
        "posts_total": len(posts),
        "posts_author_matched": 0,
        "cases_written": 0,
        "posts_no_prescription_match": 0,
        "posts_non_case": 0,
    }

    for post in posts:
        author, author_line = extract_author_lines(post.content)
        if not any(token in author for token in author_tokens):
            continue

        stats["posts_author_matched"] += 1
        matches = detect_prescription_matches(post.content, prescription_index)
        if not matches:
            stats["posts_no_prescription_match"] += 1
            continue

        written_for_post = 0
        for md_file, alias in matches:
            symptoms = extract_symptoms(post.content, alias)
            if not is_treatment_symptom_text(symptoms):
                continue

            prescription_name = _prescription_name_from_file(md_file) or alias
            folder_name = safe_name(prescription_name)
            folder = output_dir / folder_name
            folder.mkdir(parents=True, exist_ok=True)

            record = CaseRecord(
                post_id=post.post_id,
                author=author,
                author_line=author_line,
                prescription_name=prescription_name,
                matched_alias=alias,
                patient_info=extract_patient_info(post.content),
                symptoms=symptoms,
                created_at=post.created_at or "",
                created_label=post.created_label,
                url=post.url,
                content=post.content,
            )

            case_file = folder / f"post_{post.post_id}.md"
            write_case_file(case_file, record)
            folder_records[folder_name].append(record)
            stats["cases_written"] += 1
            written_for_post += 1

        if written_for_post == 0:
            stats["posts_non_case"] += 1

    for folder_name, records in folder_records.items():
        if not records:
            continue
        folder = output_dir / folder_name
        prescription_name = records[0].prescription_name
        # Deduplicate repeated post ids within one prescription folder.
        unique_by_post: dict[str, CaseRecord] = {}
        for record in records:
            unique_by_post[record.post_id] = record
        deduped = list(unique_by_post.values())
        folder_records[folder_name] = deduped
        write_index_file(folder, prescription_name, deduped)

    write_root_summary(output_dir, folder_records)

    summary_path = output_dir / "README.md"
    print(f"export_json={export_json}")
    print(f"output_dir={output_dir}")
    print(f"summary={summary_path}")
    print(f"stats={stats}")
    print(f"prescription_folders={len(folder_records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
