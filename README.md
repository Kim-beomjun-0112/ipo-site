# 공모주 캘린더 (ipo.qjawnsl112.com)

금융감독원 전자공시(DART) 증권신고서를 자동으로 수집해
**공모주 청약 일정 · 공모가 · 증권사별 배정물량과 청약한도**를 보여주는 정적 사이트입니다.

서버도 데이터베이스도 없습니다. GitHub Actions가 데이터를 모아 커밋하고,
Netlify는 만들어진 `site/` 폴더를 그대로 올립니다. **운영비 0원.**

---

## 구조

```
scripts/dart.py      DART API 호출 + 증권신고서 파싱
scripts/collect.py   수집 → data/ipos.json
scripts/build.py     data/*.json → site/ (정적 HTML)

data/ipos.json       자동 수집 결과 (건드리지 마세요)
data/overrides.json  손으로 고친 값 — 자동 수집을 덮어씁니다
data/brokers.json    증권사 고정 정보 (앱 이름 등) — 직접 관리
data/_parsed.json    파싱 캐시. 매일 돌 때 이미 본 공시는 다시 안 받습니다

admin/index.html     검수 화면 (사이트의 /admin/ 으로 열림, 검색엔진 제외)
site/                빌드 결과. Actions가 자동으로 갱신합니다
```

## 데이터 흐름

```
DART 공시검색 API
  → 증권신고서(지분증권) 목록
  → 각 문서 XML 내려받아 파싱
      · 청약기일 / 납입기일
      · 희망공모가 밴드 / 확정공모가
      · 인수인 표 → 증권사별 인수물량
      · 일반청약자 배정물량 · 최고청약한도 · 증거금률
  → 같은 회사의 정정신고서를 하나로 병합
  → 유상증자 제외, 스팩은 따로 표시
  → data/overrides.json 수동값 덮어쓰기
  → data/ipos.json → site/
```

추출하지 못한 항목은 **"확인 불가"** 로 표시합니다. 틀린 값을 내보내지 않는 것이 원칙입니다.

## 자동 실행

`.github/workflows/collect.yml` 이 하루 두 번(한국시간 07시·18시) 돕니다.
`data/overrides.json` 을 고쳐 커밋하면 그때도 바로 다시 빌드됩니다.
Actions 탭에서 **Run workflow** 버튼으로 수동 실행도 됩니다.

필요한 설정: 저장소 Settings → Secrets and variables → Actions →
`DART_API_KEY` (OpenDART 인증키)

## 직접 돌려보기

```bash
pip install requests beautifulsoup4 lxml
export DART_API_KEY=발급받은키
python scripts/collect.py
python scripts/build.py
python -m http.server -d site 8000
```

## 검수 화면 쓰는 법

1. 사이트의 `/admin/` 을 엽니다
2. "검수 필요"로 뜬 종목의 빈 항목을 DART 원문을 보며 채웁니다
3. **GitHub에 저장** 을 누르면 `data/overrides.json` 에 커밋되고 사이트가 다시 빌드됩니다
   (처음 한 번만 저장소 이름과 토큰을 입력해두면 됩니다)

토큰이 부담스러우면 **파일로 내려받기** 를 눌러 `data/overrides.json` 에 직접 올려도 됩니다.

## 주의

- 이 사이트는 DART 공시 원문을 기계적으로 정리해 보여줍니다. 투자 권유가 아닙니다.
- 다른 공모주 사이트의 데이터는 쓰지 않습니다 (저작권·애드센스 정책).
- 상장일과 상장 후 시세는 증권신고서에 없어 아직 비어 있습니다. 추후 KRX 시세 연동 예정.
