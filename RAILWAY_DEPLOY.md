# Railway 배포 가이드

## 1. 현재 코드 상태
- `app.py`는 Railway 방식(`0.0.0.0:$PORT`)으로 실행되도록 준비되어 있습니다.
- `Dockerfile`, `railway.toml`, `/health` 헬스체크가 포함되어 있습니다.
- OAuth 콜백 경로는 `/auth/callback` 입니다.

## 2. Railway에 전체 프로젝트 배포
1. GitHub에 현재 프로젝트를 push 합니다.
2. Railway에서 `New Project` → `Deploy from GitHub repo`를 선택합니다.
3. 이 저장소를 선택하면 `Dockerfile` 기반으로 자동 빌드/배포됩니다.
4. 배포 완료 후 `https://<railway-domain>` 형태의 Public Domain을 확인합니다.

## 3. BAND OAuth Redirect URI 설정
- BAND 개발자 콘솔에 아래를 등록하세요.
- Service Domain
  - `https://<railway-domain>`
  - `https://magicians7-korean-medicine-ai.hf.space`
- Redirect URI
  - `https://<railway-domain>/auth/callback`
  - `https://magicians7-korean-medicine-ai.hf.space/auth/callback`

## 4. Railway 환경변수(권장)
- `BAND_REDIRECT_URI_REMOTE=https://<railway-domain>/auth/callback`
- `BAND_CONFIG_PATH=/app/band_config.yaml`
- `PORT`는 Railway가 자동 주입하므로 수동 설정하지 않습니다.

## 5. BAND 동기화까지 같이 옮길 때
1. 저장소의 `band_config.example.yaml`을 참고해 실제 `band_config.yaml`을 만듭니다.
2. `band_config.yaml`은 민감정보가 있으므로 git에 올리지 말고 Railway 볼륨/런타임 파일로 관리합니다.
3. `BAND_CONFIG_PATH`를 실제 파일 경로로 맞춥니다.

## 6. 배포 후 확인
- `https://<railway-domain>/health`가 `{"status":"ok"}`를 반환하는지 확인
- `https://<railway-domain>/auth/callback` 접속 시 500이 아닌 안내 페이지가 보이는지 확인

## 7. 로컬에서 BAND 인증할 때
- 원격 콜백 URL을 직접 지정해서 인증할 수 있습니다.

```bash
python band_api.py --auth --auth-mode manual --redirect-uri "https://<railway-domain>/auth/callback"
```
