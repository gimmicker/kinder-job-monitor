# 청주 유치원 채용공고 알림

충북교육청 학교구인정보 게시판에서 청주 유치원 공고를 모아 휴대폰 앱(PWA)으로 알려준다. 설계는 [DESIGN.md](DESIGN.md).

```
GitHub Actions (평일 08:30·12:30·17:30) → 수집·분류(app.main) → data/*.json 커밋
  → GitHub Pages 배포(web/ + data) → 푸시 발송(app.push) → Cloudflare Worker에 등록된 폰
```

## 로컬 개발

```bash
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest -q          # 테스트
.venv/Scripts/python -m app.main           # 실제 수집 (data/ 갱신)
.venv/Scripts/python -m app.build_site     # _site/ 생성
```

분류 기준은 `config/settings.yaml`, 기관별 지역은 `config/places.yaml`.

## 최초 설정 (한 번만)

### 1. VAPID 키
```bash
.venv/Scripts/python scripts/gen_vapid.py
```
- `VAPID_PUBLIC_KEY` → GitHub **Variables**
- `VAPID_PRIVATE_KEY` → GitHub **Secrets**
- `VAPID_SUBJECT` → GitHub Variables, 예: `mailto:본인메일`

### 2. Cloudflare Worker (무료)
```bash
cd worker
npx wrangler login
npx wrangler kv namespace create SUBS        # 출력된 id를 wrangler.toml에
# wrangler.toml의 ALLOWED_ORIGIN을 https://<github아이디>.github.io 로
npx wrangler secret put REGISTER_CODE        # 아무 긴 문자열 (앱 주소의 ?code=)
npx wrangler secret put ADMIN_TOKEN          # 아무 긴 문자열
npx wrangler deploy                          # 출력된 https://...workers.dev 주소 = WORKER_URL
```
GitHub Secrets: `WORKER_URL`, `WORKER_ADMIN_TOKEN`(=ADMIN_TOKEN)

### 3. GitHub
- Settings → Pages → Source: **GitHub Actions**
- Secrets(선택, 관리자 메일): `MAIL_USER`, `MAIL_APP_PASSWORD`(Gmail 앱 비밀번호), `MAIL_ADMIN`
- Actions → monitor → Run workflow 로 첫 실행

### 4. 어머니 폰 (안드로이드)
1. Chrome으로 `https://<아이디>.github.io/kinder-job-monitor/?code=<REGISTER_CODE>` 열기
2. [홈 화면에 설치] → 설치된 아이콘으로 열기
3. [🔔 알림 켜기] → 허용
4. Actions → monitor → Run workflow → `테스트 알림만 보내기` 체크 → 알림 오는지 확인
5. 알림이 늦으면: 설정 → 애플리케이션 → Chrome → 배터리 → 제한 없음

### 5. 지역 판단 정확도 올리기 (선택)
NEIS 인증키(open.neis.go.kr, 무료)를 받아:
```bash
NEIS_KEY=... .venv/Scripts/python scripts/build_places.py
```
단설 유치원(예: 홍광유치원)은 `config/places.yaml`의 `유:` 아래에 직접 추가: `홍광: 청주`
