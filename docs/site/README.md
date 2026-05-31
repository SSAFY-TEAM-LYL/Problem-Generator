# IPE 인터랙티브 사이트

GitHub Pages 호스팅용 정적 HTML 사이트. 사람용 요약 문서 (제출/외부 공유) 전용 — v1.0(anchor freeze) + Phase 3(v2) 현황 반영.

## 페이지

| 파일 | 내용 |
|---|---|
| `index.html` | 진입점 — hero + v1.0 anchor + 검증 해자 + v1 파이프라인 + Phase 3(v2) 요약 |
| `requirements.html` | FR 14 + NFR 10 + v1.0 인수 기준 + 알려진 한계 |
| `tech-stack.html` | 12 deps + 모델 tiering + 4-tier sandbox + 제외 기술 + 의존성 그래프 |
| `dashboard.html` | Gate 여정(v0 27%→v1.0 91.2%, Chart.js) + 카탈로그 성장 + v2 토폴로지 + 마일스톤 + 아카이브 |

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

측정 갱신 / PR·마일스톤 진행 시 `assets/data.js`의 `IPE_DATA` 객체만 수정. 모든 페이지가 자동 반영. 모든 수치는 측정/문서 근거가 있는 값만 적는다 (narrative honesty).

```javascript
// assets/data.js
window.IPE_DATA = {
  meta: { version, mainCommit, devCommit, gatePassPct, tests, coverage, ... },
  moat: [{ icon, title, desc }, ...],          // 검증 해자
  journey: [{ phase, algos, passPct, label, note }, ...],  // v0→v1.0 측정 여정
  v2Stages: [{ stage, nodes, parallel, desc }, ...],       // Phase 3 v2 토폴로지
  tiers: [{ tier, label, cls, desc }, ...],    // 검증 신뢰 tier A/B/C
  milestones: [{ id, title, status, ref, note }, ...],     // M0~M6
  recentPrs: [{ num, title, type, impact }, ...],
  // fr, nfr, stack, exclusions, principles, backlog ...
};
```

## 디자인 원칙

- **Dark theme** — 개발자 친화 + GitHub UI 톤
- **Minimalism** — Apple/Linear/Vercel 스타일
- **Korean-first** — 콘텐츠 한국어, 코드/식별자 영어
- **Responsive** — mobile-friendly (Tailwind utility)
- **인터랙티브** — Chart.js 시각화, 차트 hover detail
