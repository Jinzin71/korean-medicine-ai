# BAND API 없이 글 수집하기

이 도구는 BAND API 승인이 안 될 때 쓰는 로컬 대체 경로입니다. 사용자가 직접 로그인한 브라우저 세션으로만 읽고, 캡차나 권한 장벽은 우회하지 않습니다.

현재 기본 수집 대상은 사진첩이 아니라 게시글 카테고리입니다.

```text
https://www.band.us/band/12411046/post
```

## 1. 최초 1회 준비

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

## 2. 로그인 후 수집만 하기

```powershell
python band_web_sync.py --band-url "https://www.band.us/band/12411046/post" --pause-after-open --since 2025-01-01
```

브라우저가 열리면 BAND에 로그인하고, 대상 밴드의 게시글 목록 화면이 보이는지 확인한 뒤 터미널에서 Enter를 누릅니다.

Enter 없이 자동으로 진행하려면 `--pause-after-open` 대신 로그인 대기 옵션을 사용하세요.

```powershell
python band_web_sync.py --band-url "https://www.band.us/band/12411046/post" --since 2025-01-01 --wait-login-secs 1800
```

기본값은 각 게시글 상세 페이지를 다시 열어 `더보기`를 펼친 전체 본문을 저장합니다. 테스트처럼 목록 화면만 빠르게 확인하려면 `--no-hydrate-full-posts`를 붙입니다.

```powershell
python band_web_sync.py --band-url "https://www.band.us/band/12411046/post" --since 2025-01-01 --no-hydrate-full-posts
```

수집 결과는 `band_web_exports/` 아래에 JSON/JSONL로 저장됩니다.

## 3. 수집과 동시에 처방 파일에 삽입하기

```powershell
python band_web_sync.py --band-url "https://www.band.us/band/12411046/post" --pause-after-open --since 2025-01-01 --insert
```

삽입 형식은 기존 처방 md 파일의 `### 치험례` 형식을 따릅니다.

```md
17. [여 70세 태음인 BMI 24.8 / 소화불량, 피로, 두통](https://band.us/band/.../post/...)
```

## 4. 두 번째 실행부터

로그인 세션은 `.band_browser_profile/`에 남아 있으므로 다시 로그인하지 않아도 됩니다.

```powershell
python band_web_sync.py --band-url "https://www.band.us/band/12411046/post" --since 2025-01-01 --insert
```

## 5. 기존 삽입 항목 정리

역할명(`공동리더`, `멤버`)이 증상 자리에 들어갔거나, 짧은 처방명에 중복 삽입된 항목은 저장된 JSON을 기준으로 정리할 수 있습니다.

```powershell
python band_web_sync.py --repair-existing --repair-export band_web_exports/band_posts_2025-01-01_to_2026-04-29.json
python band_web_sync.py --cleanup-label-prefixes
python band_web_sync.py --prune-mismatched-existing --repair-export band_web_exports/band_posts_2025-01-01_to_2026-04-29.json
```

## 6. 주의할 점

- 비공개 밴드는 본인이 볼 수 있는 글만 수집됩니다.
- 빠른 대량 요청을 하지 않도록 스크롤 간격을 두고 동작합니다.
- 기본 실행은 `더보기` 버튼을 누르지 않고 스크롤만 합니다. 밴드 화면의 사이드바 `더보기`가 사진첩으로 이동할 수 있으므로 `--click-load-more`는 필요한 경우에만 사용하세요.
- 환자 이름, 전화번호 같은 식별 정보가 글에 있으면 원문 JSON에 남을 수 있으니 외부 공유하지 마세요.
- `band_web_seen.json`은 중복 삽입 방지용 파일입니다.
