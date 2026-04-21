"""
band_api.py — 네이버 밴드 공식 Open API 클라이언트 (OAuth 2.0)
=========================================================
Band Developers: https://developers.band.us

설정 방법:
  1. https://developers.band.us 에서 앱 등록
  2. [서비스 도메인] 에 아래 2개를 모두 등록
     - http://localhost:9000
     - https://magicians7-korean-medicine-ai.hf.space
  3. Client ID / Client Secret 을 band_config.yaml 에 입력
  4. python band_api.py --auth --redirect-target local   ← 로컬 콜백 자동 인증
     python band_api.py --auth --redirect-target remote  ← HF 콜백 + 수동 code 입력
  5. python band_api.py --test   ← 연결 확인

인증 흐름:
  최초: 브라우저 OAuth 로그인 → access_token + refresh_token 저장
  이후: refresh_token 으로 자동 갱신 (만료 전 선제 갱신)

의존성:
  pip install requests pyyaml
"""

import os
import json
import time
import webbrowser
import logging
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urlparse, parse_qs

import requests
import yaml

# ── 상수 ─────────────────────────────────────────────────────────────────────

AUTH_URL    = "https://auth.band.us/oauth2/authorize"
TOKEN_URL   = "https://auth.band.us/oauth2/token"
API_BASE    = "https://openapi.band.us"
LOCAL_REDIRECT_URI_DEFAULT = "http://localhost:9000/callback"
_railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
_remote_fallback = (
    f"https://{_railway_domain}/auth/callback"
    if _railway_domain
    else "https://magicians7-korean-medicine-ai.hf.space/auth/callback"
)
REMOTE_REDIRECT_URI_DEFAULT = os.getenv("BAND_REDIRECT_URI_REMOTE", _remote_fallback)
CALLBACK_TIMEOUT_DEFAULT_SEC = 120

# ── 로거 ─────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


def _is_local_redirect_uri(redirect_uri: str) -> bool:
    host = (urlparse(redirect_uri).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


# ─────────────────────────────────────────────────────────────────────────────
# 예외 클래스
# ─────────────────────────────────────────────────────────────────────────────

class BandAuthError(Exception):
    """인증 실패 또는 토큰 없음"""

class BandTokenExpiredError(BandAuthError):
    """Access token 만료 (refresh 필요)"""

class BandAPIError(Exception):
    """API 호출 오류"""


# ─────────────────────────────────────────────────────────────────────────────
# TokenStore — 토큰 영속화
# ─────────────────────────────────────────────────────────────────────────────

class TokenStore:
    """
    band_token.json 에 토큰을 저장/로드합니다.

    저장 형식:
    {
      "access_token":  "...",
      "refresh_token": "...",
      "expires_at":    1710000000.0,   (Unix timestamp)
      "saved_at":      "2025-03-15 00:00"
    }
    """

    def __init__(self, token_file: str = "band_token.json"):
        self.path = Path(token_file)

    def save(self, token_data: dict):
        """API 응답에서 토큰 추출 후 저장"""
        expires_in = int(token_data.get("expires_in", 3600))
        store = {
            "access_token":  token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", ""),
            "expires_at":    time.time() + expires_in - 60,  # 60초 여유
            "saved_at":      datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        self.path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"토큰 저장 완료 → {self.path}")

    def load(self) -> Optional[dict]:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))

    def access_token(self) -> Optional[str]:
        d = self.load()
        return d["access_token"] if d else None

    def refresh_token(self) -> Optional[str]:
        d = self.load()
        return d.get("refresh_token") if d else None

    def is_expired(self) -> bool:
        d = self.load()
        if not d:
            return True
        return time.time() > d.get("expires_at", 0)

    def clear(self):
        self.path.unlink(missing_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# OAuthHandler — OAuth 2.0 인증 흐름
# ─────────────────────────────────────────────────────────────────────────────

class _CallbackHandler(BaseHTTPRequestHandler):
    """로컬 서버로 OAuth 콜백 수신"""
    code: Optional[str] = None
    error: Optional[str] = None
    callback_path: str = "/callback"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != _CallbackHandler.callback_path:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Not Found".encode("utf-8"))
            return

        qs = parse_qs(parsed.query)
        _CallbackHandler.code  = (qs.get("code",  [None])[0])
        _CallbackHandler.error = (qs.get("error", [None])[0])
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if _CallbackHandler.code:
            body = "<h2 style='font-family:sans-serif;color:#27ae60'>✅ 인증 완료! 이 창을 닫고 터미널로 돌아가세요.</h2>"
        else:
            body = f"<h2 style='font-family:sans-serif;color:#c0392b'>❌ 인증 실패: {_CallbackHandler.error}</h2>"
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args):
        pass  # 서버 로그 억제


class OAuthManager:
    """
    Band OAuth 2.0 인증 흐름 관리.

    사용 예시:
        oauth = OAuthManager(client_id, client_secret, token_store)
        oauth.authorize()        # 최초 1회 브라우저 인증
        token = oauth.get_valid_token()   # 유효 토큰 반환 (자동 갱신)
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        store: TokenStore,
        redirect_uri: str = LOCAL_REDIRECT_URI_DEFAULT,
        redirect_uri_local: str = LOCAL_REDIRECT_URI_DEFAULT,
        redirect_uri_remote: str = REMOTE_REDIRECT_URI_DEFAULT,
        callback_timeout_sec: int = CALLBACK_TIMEOUT_DEFAULT_SEC,
    ):
        self.client_id     = client_id
        self.client_secret = client_secret
        self.store         = store
        self.redirect_uri = redirect_uri
        self.redirect_uri_local = redirect_uri_local
        self.redirect_uri_remote = redirect_uri_remote
        self.callback_timeout_sec = int(callback_timeout_sec)

    # ── 최초 인증 (브라우저 열기) ──────────────────────────────────────────────

    def authorize(
        self,
        auth_mode: str = "auto",
        redirect_uri: Optional[str] = None,
        code: Optional[str] = None,
    ):
        """
        브라우저에서 Band 로그인 → OAuth 코드 수신 → 토큰 교환 → 저장.
        최초 1회 또는 refresh_token 만료 시 호출.
        """
        redirect_uri = (redirect_uri or self.redirect_uri).strip()
        auth_mode = auth_mode.lower().strip()
        if auth_mode not in {"auto", "local", "manual"}:
            raise BandAuthError(f"지원하지 않는 auth_mode: {auth_mode}")

        if code:
            oauth_code = self._extract_code(code)
            self._exchange_code(oauth_code, redirect_uri)
            print("\n✅ 인증 완료! 토큰이 저장되었습니다.\n")
            return

        auth_url = AUTH_URL + "?" + urlencode({
            "response_type": "code",
            "client_id":     self.client_id,
            "redirect_uri":  redirect_uri,
        })

        print("\n" + "="*60)
        print("  밴드 OAuth 인증을 시작합니다.")
        print("  브라우저가 열리면 네이버 계정으로 로그인 후 앱 접근을 허용해주세요.")
        print(f"  redirect_uri: {redirect_uri}")
        print("="*60)
        print(f"\n  인증 URL: {auth_url}\n")

        webbrowser.open(auth_url)

        use_local_callback = (
            auth_mode == "local"
            or (auth_mode == "auto" and _is_local_redirect_uri(redirect_uri))
        )

        if use_local_callback:
            oauth_code = self._wait_local_callback(redirect_uri)
        else:
            oauth_code = self._prompt_code_manually()

        self._exchange_code(oauth_code, redirect_uri)
        print("\n✅ 인증 완료! 토큰이 저장되었습니다.\n")

    def _wait_local_callback(self, redirect_uri: str) -> str:
        parsed = urlparse(redirect_uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        _CallbackHandler.callback_path = parsed.path or "/callback"
        _CallbackHandler.code  = None
        _CallbackHandler.error = None

        server = HTTPServer((host, port), _CallbackHandler)
        server.timeout = self.callback_timeout_sec
        try:
            server.handle_request()
        finally:
            server.server_close()

        if _CallbackHandler.error:
            raise BandAuthError(f"OAuth 인증 거부: {_CallbackHandler.error}")
        if not _CallbackHandler.code:
            raise BandAuthError("인증 코드를 받지 못했습니다. 브라우저에서 인증을 완료해주세요.")
        return _CallbackHandler.code

    def _prompt_code_manually(self) -> str:
        print("원격 콜백 모드입니다.")
        print("브라우저가 callback URL로 이동한 뒤 주소창 전체 URL 또는 code 값만 붙여넣으세요.")
        raw = input("code 또는 redirect URL 입력: ").strip()
        if not raw:
            raise BandAuthError("인증 코드를 입력하지 않았습니다.")
        return self._extract_code(raw)

    def _extract_code(self, raw: str) -> str:
        raw = raw.strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            qs = parse_qs(urlparse(raw).query)
            err = (qs.get("error", [None])[0])
            if err:
                raise BandAuthError(f"OAuth 인증 거부: {err}")
            code = (qs.get("code", [None])[0])
            if code:
                return code
            raise BandAuthError("URL에서 code 파라미터를 찾지 못했습니다.")
        if "code=" in raw:
            qs = parse_qs(urlparse("http://dummy/?" + raw.split("?", 1)[-1]).query)
            code = (qs.get("code", [None])[0])
            if code:
                return code
        return raw

    def _exchange_code(self, code: str, redirect_uri: str):
        """인증 코드 → Access Token + Refresh Token 교환"""
        resp = requests.post(TOKEN_URL, data={
            "grant_type":    "authorization_code",
            "code":          code,
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri":  redirect_uri,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "access_token" not in data:
            raise BandAuthError(f"토큰 교환 실패: {data}")
        self.store.save(data)

    # ── 토큰 자동 갱신 ────────────────────────────────────────────────────────

    def refresh(self) -> bool:
        """
        Refresh Token으로 Access Token 갱신.
        Returns: True(성공) / False(refresh token도 만료 → 재인증 필요)
        """
        rt = self.store.refresh_token()
        if not rt:
            return False
        try:
            resp = requests.post(TOKEN_URL, data={
                "grant_type":    "refresh_token",
                "refresh_token": rt,
                "client_id":     self.client_id,
                "client_secret": self.client_secret,
            }, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if "access_token" not in data:
                logger.warning(f"토큰 갱신 실패: {data}")
                return False
            self.store.save(data)
            logger.info("Access Token 자동 갱신 완료")
            return True
        except Exception as e:
            logger.warning(f"토큰 갱신 오류: {e}")
            return False

    # ── 유효 토큰 반환 (핵심 메서드) ──────────────────────────────────────────

    def get_valid_token(self) -> str:
        """
        유효한 access_token 반환.
        만료 시 refresh → 그래도 안 되면 BandAuthError 발생.
        """
        if not self.store.load():
            raise BandAuthError("토큰이 없습니다. python band_api.py --auth 를 실행하세요.")

        if self.store.is_expired():
            logger.info("Access Token 만료 → Refresh Token으로 갱신 시도")
            success = self.refresh()
            if not success:
                self.store.clear()
                raise BandAuthError(
                    "Refresh Token도 만료되었습니다.\n"
                    "python band_api.py --auth 를 다시 실행해주세요."
                )

        return self.store.access_token()


# ─────────────────────────────────────────────────────────────────────────────
# BandAPIClient — REST API 호출
# ─────────────────────────────────────────────────────────────────────────────

class BandAPIClient:
    """
    Band Open API REST 클라이언트.

    사용 예시:
        client = BandAPIClient.from_config("band_config.yaml")
        bands  = client.get_bands()
        posts  = client.get_posts(band_key, item_count=30)
    """

    def __init__(self, oauth: OAuthManager):
        self.oauth   = oauth
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "HerbPrescription-AI/1.0",
        })

    @classmethod
    def from_config(cls, config_path: str = "band_config.yaml") -> "BandAPIClient":
        cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
        api_cfg = cfg["band"]["api"]
        store = TokenStore(api_cfg.get("token_file", "band_token.json"))
        redirect_uri_local = api_cfg.get("redirect_uri_local", LOCAL_REDIRECT_URI_DEFAULT)
        redirect_uri_remote = api_cfg.get("redirect_uri_remote", REMOTE_REDIRECT_URI_DEFAULT)
        redirect_uri_mode = str(api_cfg.get("redirect_uri_mode", "local")).lower()
        if redirect_uri_mode == "remote":
            redirect_uri = redirect_uri_remote
        elif redirect_uri_mode == "custom" and api_cfg.get("redirect_uri"):
            redirect_uri = api_cfg["redirect_uri"]
        else:
            redirect_uri = redirect_uri_local

        oauth = OAuthManager(
            client_id     = api_cfg["client_id"],
            client_secret = api_cfg["client_secret"],
            store         = store,
            redirect_uri  = redirect_uri,
            redirect_uri_local = redirect_uri_local,
            redirect_uri_remote = redirect_uri_remote,
            callback_timeout_sec = int(api_cfg.get("callback_timeout_sec", CALLBACK_TIMEOUT_DEFAULT_SEC)),
        )
        return cls(oauth)

    # ── 공통 요청 ─────────────────────────────────────────────────────────────

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """GET 요청 (자동 토큰 삽입 + 오류 처리)"""
        token = self.oauth.get_valid_token()
        p = {"access_token": token, **(params or {})}
        url = f"{API_BASE}{endpoint}"
        resp = self._session.get(url, params=p, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        rc = data.get("result_code", 1)
        if rc == -1001:   # 토큰 만료 (API 측 감지)
            logger.info("API 토큰 만료 신호 수신 → 자동 갱신")
            self.oauth.refresh()
            return self._get(endpoint, params)   # 1회 재시도
        if rc != 1:
            raise BandAPIError(f"API 오류 (result_code={rc}): {data.get('result_data', data)}")

        return data.get("result_data", data)

    # ── 밴드 목록 ─────────────────────────────────────────────────────────────

    def get_bands(self) -> list[dict]:
        """
        사용자가 속한 밴드 목록 반환.

        Returns:
            [{"band_key": "...", "name": "...", "member_count": N, ...}, ...]
        """
        data = self._get("/v2.1/bands")
        bands = data.get("bands", [])
        logger.info(f"밴드 목록 {len(bands)}개 조회")
        return bands

    def find_band_key(self, band_name_contains: str) -> Optional[str]:
        """이름으로 밴드 키 검색"""
        for b in self.get_bands():
            if band_name_contains in b.get("name", ""):
                return b["band_key"]
        return None

    # ── 게시물 수집 ───────────────────────────────────────────────────────────

    def get_posts(
        self,
        band_key: str,
        item_count: int = 20,
        after_ts: Optional[int] = None,
    ) -> list[dict]:
        """
        밴드 게시물 수집.

        Args:
            band_key:   밴드 고유 키 (get_bands()로 조회)
            item_count: 한 번에 가져올 게시물 수 (최대 20)
            after_ts:   이 timestamp 이후 게시물만 (증분 동기화용)

        Returns:
            [{"post_key": "...", "content": "...", "created_at": ...,
              "author": {"name": "..."}, "photos": [...], ...}, ...]
        """
        params = {
            "band_key":   band_key,
            "item_count": min(item_count, 20),
        }
        if after_ts:
            params["after"] = after_ts

        data  = self._get("/v2/band/posts", params)
        items = data.get("items", [])
        logger.info(f"게시물 {len(items)}건 수집 (band_key={band_key[:8]}...)")
        return items

    def get_all_posts(
        self,
        band_key: str,
        max_posts: int = 50,
        after_ts: Optional[int] = None,
    ) -> list[dict]:
        """
        페이지네이션으로 max_posts 까지 모두 수집.
        after_ts 를 지정하면 증분(신규만) 수집.
        """
        all_posts = []
        current_ts = after_ts

        while len(all_posts) < max_posts:
            batch = self.get_posts(
                band_key,
                item_count=min(20, max_posts - len(all_posts)),
                after_ts=current_ts,
            )
            if not batch:
                break
            all_posts.extend(batch)
            # 다음 페이지: 마지막 게시물의 timestamp
            current_ts = batch[-1].get("created_at")
            if len(batch) < 20:
                break   # 더 이상 없음

        logger.info(f"총 {len(all_posts)}건 수집 완료")
        return all_posts

    def get_post_detail(self, band_key: str, post_key: str) -> dict:
        """게시물 본문 상세 조회 (긴 텍스트 포함)"""
        return self._get("/v2/band/post", {
            "band_key": band_key,
            "post_key": post_key,
        })

    # ── 게시물 파싱 헬퍼 ──────────────────────────────────────────────────────

    @staticmethod
    def parse_post(raw: dict) -> dict:
        """
        API 응답의 raw 게시물을 band_sync.py 에서 사용하는
        공통 포맷으로 변환합니다.

        Returns:
            {
              "post_id":  str,      # 고유 ID (post_key 해시)
              "post_key": str,      # 원본 API 키
              "url":      str,      # 밴드 게시물 직접 링크
              "date":     str,      # "YYYY-MM-DD"
              "content":  str,      # 게시물 텍스트
              "author":   str,      # 작성자 이름
            }
        """
        import hashlib
        post_key  = raw.get("post_key", "")
        content   = raw.get("content", "").strip()
        author    = raw.get("author", {}).get("name", "알 수 없음")
        ts        = raw.get("created_at", 0)
        date      = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else ""
        url       = raw.get("web_url", f"https://band.us/post/{post_key}")
        post_id   = hashlib.md5(post_key.encode()).hexdigest()[:8]

        return {
            "post_id":  post_id,
            "post_key": post_key,
            "url":      url,
            "date":     date,
            "content":  content,
            "author":   author,
        }


# ─────────────────────────────────────────────────────────────────────────────
# CLI — 인증 + 테스트
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Band API 관리 도구")
    parser.add_argument("--auth",      action="store_true", help="OAuth 인증 (최초 1회 또는 재인증)")
    parser.add_argument(
        "--auth-mode",
        choices=["auto", "local", "manual"],
        default="auto",
        help="OAuth 코드 수신 방식 (auto: redirect_uri에 따라 자동 선택)",
    )
    parser.add_argument(
        "--redirect-target",
        choices=["current", "local", "remote"],
        default="current",
        help="인증 시 사용할 redirect_uri 선택",
    )
    parser.add_argument("--redirect-uri", help="인증 시 사용할 redirect_uri 직접 지정")
    parser.add_argument("--code", help="수동 모드에서 code 또는 callback URL 전체")
    parser.add_argument("--test",      action="store_true", help="API 연결 테스트 + 밴드 목록 출력")
    parser.add_argument("--bands",     action="store_true", help="내 밴드 목록 + band_key 출력")
    parser.add_argument("--config",    default="band_config.yaml")
    args = parser.parse_args()

    client = BandAPIClient.from_config(args.config)

    if args.auth:
        print("\n[ Band OAuth 인증 시작 ]")
        redirect_uri = args.redirect_uri
        if not redirect_uri:
            if args.redirect_target == "local":
                redirect_uri = client.oauth.redirect_uri_local
            elif args.redirect_target == "remote":
                redirect_uri = client.oauth.redirect_uri_remote
            else:
                redirect_uri = client.oauth.redirect_uri
        client.oauth.authorize(
            auth_mode=args.auth_mode,
            redirect_uri=redirect_uri,
            code=args.code,
        )
        print("이후 모든 동기화는 자동으로 실행됩니다.")

    elif args.test:
        print("\n[ API 연결 테스트 ]")
        try:
            bands = client.get_bands()
            print(f"✅ 연결 성공 — 소속 밴드 {len(bands)}개:")
            for b in bands:
                print(f"   • {b.get('name','?'):<30} band_key: {b.get('band_key','?')}")
        except BandAuthError as e:
            print(f"❌ 인증 오류: {e}")
            sys.exit(1)
        except BandAPIError as e:
            print(f"❌ API 오류: {e}")
            sys.exit(1)

    elif args.bands:
        bands = client.get_bands()
        print("\n[ 내 밴드 목록 ]")
        print(f"{'이름':<30} {'band_key':<40} {'멤버수'}")
        print("-" * 80)
        for b in bands:
            print(f"{b.get('name','?'):<30} {b.get('band_key','?'):<40} {b.get('member_count','?')}")
        print("\n👉 band_config.yaml 의 band.band_key 에 복사하세요.")

    else:
        parser.print_help()
