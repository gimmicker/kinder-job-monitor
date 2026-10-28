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
.venv/Scripts/python scripts/preview.py    # 화면 미리보기 http://localhost:8090 (폰도 보려면 --lan)
```

개발은 `dev` 브랜치에서 하고, 반영할 때 `main`에 합친다. `main`에 화면 파일이 올라가면 자동 배포된다.

분류 기준은 `config/settings.yaml`, 기관별 지역은 `config/places.yaml`.

### 공고 출처
- 충북교육청 학교구인정보 게시판 (`app/scraper.py`, `app/parser.py`)
- 청주교육지원청 구인정보: 학교 게시판(유치원) · 교육지원청 게시판 (`app/cheongju.py`).
  청주 유치원은 여기에만 올리는 공고가 많다. 마감일 칸이 없어서 첫 HWP 첨부에서 접수 마감일을 읽는다 (`app/docs.py`).
- 두 곳에 같은 공고가 있으면 충북교육청 쪽 하나만 남긴다 (제목·등록일 비교, 차수가 다르면 다른 공고).

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

### 5. 기관 지역·유치원 정보 갱신 (가끔)
인증키는 `.local/secrets.env`에 보관한다 (커밋 안 됨).

- 초등학교 목록 (병설유치원 지역 판단): NEIS 인증키(open.neis.go.kr)
  ```bash
  NEIS_KEY=... .venv/Scripts/python scripts/build_places.py
  ```
- 충북 유치원 공시 자료 (지역, 원아·학급 수, 주소, 전화): 유치원알리미 OPEN API 인증키
  (e-childschoolinfo.moe.go.kr → 자료실 → OPEN API). 공시가 바뀌는 때(연 2회쯤) 다시 실행해 커밋한다.
  ```bash
  CHILD_KEY=... .venv/Scripts/python scripts/build_kinders.py   # → config/kinders.json
  ```
- 위 두 자료에 없거나 틀린 기관은 `config/places.yaml`에 직접 적는다. 직접 적은 값이 우선한다.
