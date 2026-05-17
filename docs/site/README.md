# IPE 인터랙티브 사이트

GitHub Pages 호스팅용 정적 HTML 사이트. v0.2.0+ 사람용 문서 (제출/외부 공유) 전용.

## 페이지

| 파일 | 내용 |
|---|---|
| `index.html` | 진입점 — hero + 핵심 지표 + 아키텍처 + 최근 진행 |
| `requirements.html` | FR 14 + NFR 10 + 인수 기준 + 알려진 한계 |
| `tech-stack.html` | 11 deps + 4-tier sandbox + 제외 기술 + 의존성 그래프 |
| `dashboard.html` | e2e Run 1~12 timeline (Chart.js) + case matrix + duration + Sprint PR + backlog |

## 공통 asset

| 파일 | 역할 |
|---|---|
| `assets/style.css` | 다크 테마 + card / badge / table / flow-node / chart-wrap 등 |
| `assets/data.js` | `window.IPE_DATA` — 모든 페이지 공통 데이터 (RCA/CHANGES 미러) |

## 로컬 미리보기

```bash
# 단순 — 브라우저로 직접 열기 (file://...)
open docs/site/index.html

# 또는 가벼운 정적 서버
cd docs/site && python3 -m http.server 8000
# → http://localhost:8000
```

## GitHub Pages 활성화

1. GitHub repo → **Settings** → **Pages**
2. **Source**: `Deploy from a branch`
3. **Branch**: `main` / `/docs/site` (또는 `gh-pages` branch 분리)
4. Save → 1-2분 후 `https://lsmin124.github.io/IPE/` 활성화

`main` 머지 시 자동 deploy.

## 기술 스택

- Tailwind CSS CDN (no build)
- Chart.js CDN (dashboard 시각화)
- Vanilla HTML5 + JS (정적, build step 0)

## 데이터 갱신

새 e2e Run 결과 추가 / Sprint PR 갱신 시 `assets/data.js`의 `IPE_DATA` 객체만 수정. 모든 페이지가 자동 반영.

```javascript
// assets/data.js
window.IPE_DATA = {
  meta: { version, e2eSuccess, tests, ... },
  e2eRuns: [{ run, label, results: [...], total, durMin }, ...],
  recentPrs: [{ num, title, type, impact }, ...],
  // ...
};
```

## 디자인 원칙

- **Dark theme** — 개발자 친화 + GitHub UI 톤
- **Minimalism** — Apple/Linear/Vercel 스타일
- **Korean-first** — 콘텐츠 한국어, 코드/식별자 영어
- **Responsive** — mobile-friendly (Tailwind utility)
- **인터랙티브** — Chart.js 시각화, 차트 hover detail
