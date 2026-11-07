# report_kit — 보고서 PDF 만들기

검증된 A4 한글 보고서 틀과 빌드 스크립트. WeasyPrint는 쓰지 않는다(pango 없음). Chrome headless로 렌더한다.
DSH 샌드박스 안에서도 그대로 돈다(Chrome 옵션 내장). **build_pdf.py 를 복사하거나 고친 사본(build_local.py 등)을 만들지 않는다.**
Chrome 옵션을 더 넣어야 하면 `--chrome-flag=--옵션` 을 쓴다.

## 순서 (이대로 따를 것)

0. **수치 모으기**: 조사하면서 쓸 수치를 `facts.md` 에 표로 적는다. `cp _tools/report_kit/facts_template.md <작업폴더>/facts.md`
   형식: `| 수치 | 시점 | 지역 | 정의 | 출처 URL |`. 본문에 쓰는 수치(%, 만 대, 억, 조, 배, 원·달러·유로 금액, 범위)는 모두 여기 있어야 한다.
   계산한 값(차이, 배수, 범위로 묶은 값)도 계산식과 함께 한 줄로 넣는다.
1. **틀 복사 → read 로 한 번 열기 → 채우기**:
   `cp _tools/report_kit/template.html <작업폴더>/report.html` 한 다음, **반드시 read 로 report.html 을 한 번 연 뒤** 고친다
   (read 없이 write/edit 하면 오류가 난다). report.css 는 복사하지 않아도 된다(없으면 build_pdf.py 가 자동으로 넣는다).
2. **내용 채우기**: report.html 의 표지·목차·본문·확인 못 한 것·참고문헌을 채운다. 레이아웃 CSS(@page, 표, 목차)는 고치지 않는다.
   - **본문이 길면 조각으로 이어 붙여도 된다. 다만 최종 파일은 report.html 하나.** 조각은 2만 자(이미지를 본 대화는 8천 자) 이하로.
     - edit: 표시 줄 `<!-- @@APPEND@@ -->` 를 old_str 로, new_str = 새 `<section>…</section>` + 줄바꿈 + 같은 표시 줄.
     - `cat >> report.html <<'EOF' … EOF`: 파일 맨 끝에 붙여도 된다. 빌드할 때 build_pdf.py 가 조각을 표시 지점으로 옮겨 report.html 에 저장한다.
     - 별도 HTML·마크다운 파일을 만들어 나중에 합치지 않는다. 표시 줄은 지우지 않는다.
   - 목차 `li` 의 `data-target` = 본문 제목 id, 글자는 본문 제목과 똑같이. 쪽번호 칸은 비워 둔다.
   - 새 쪽 시작: `<section class="page-break">` (큰 장 시작에만. 남발하면 반쯤 빈 쪽이 생긴다) / 나뉘면 안 되는 블록: `class="avoid"`
   - 각주: `<a class="fn" href="#ref-1">[1]</a>` — 참고문헌 `<li id="ref-1">` 순서와 번호 일치.
     li 안에 `[1]` 을 쓰지 않는다(CSS가 붙임). URL 은 `<a class="url" href="…">전체 URL</a>` 로 글자 그대로.
   - 표는 `<thead>` 필수(쪽 넘어가면 머리행 반복), 표 제목은 표 바로 위 `.table-caption`(표와 같은 쪽에 붙어 다닌다).
   - 그림은 `<figure>` + `<figcaption>`. 그림 위 제목이 필요하면 `<div class="figure-title">`.
   - 핵심 요약은 `.summary` 박스. **"확인 못 한 것 / 상충 정보" 박스(`.caveats`)는 지우지 않는다** — 없으면 "없음".
   - 시나리오·전망 수치를 지어내지 않는다. facts.md 에 없는 수치는 쓰지 않거나 "추정(근거: …, 계산: …)" 으로 밝힌다.
3. **빌드**: `python3 _tools/report_kit/build_pdf.py report.html -o 결과.pdf --facts facts.md`
   목차 쪽번호는 자동으로 채워진다(손으로 쓰지 말 것). 렌더 2~3회, 몇 초.
   `--facts` 는 선택이지만 권장. PDF 본문 수치 중 facts 파일에 없는 것을 쪽번호·앞뒤 문맥과 함께 경고한다
   (`--facts` 를 여러 번 주면 여러 파일을 함께 본다. 예: 출처 원문을 저장한 텍스트 파일).
4. **검사 요약으로 먼저 판단**: 마지막 줄이 `판정: OK` 면 끝. 경고가 있으면 경고 문구대로 HTML(또는 facts.md)을 고치고 3번 재실행.
   (반쯤 빈 쪽, 목차를 못 찾은 제목, 깨진 글자, LastResort 글꼴, 각주·참고문헌 불일치, 없는 이미지, 출처 파일에 없는 수치)
   - 반쯤 빈 쪽: 본문 쪽 글자 수 중앙값의 40% 미만이거나, 글이 쪽 높이 절반 위에서 끝나는 쪽(표지·목차·마지막 쪽 제외).
     경고에 쪽번호와 첫 제목이 나온다.
   - Chrome 이 실패하면 stderr 요약과 "다음에 시도할 것" 이 나온다. 그대로 따른다.
5. **이미지 확인은 마지막에 한 번만, 최대 4쪽**:
   `python3 build_pdf.py report.html -o 결과.pdf --facts facts.md --preview 2,5` → `결과_preview/p2.png` 등 (60dpi).
   같은 PDF 에 `--preview` 를 2번 넘게 쓰면 경고가 난다. 레이아웃 문제는 검사 요약으로 고친다. 확인이 끝나면 `_preview` 폴더는 지운다.

## 그림: SVG 를 직접 쓴다 (기본)

시스템 python3 에는 matplotlib 이 없다. 막대·선 그래프는 HTML 안에 SVG 를 직접 쓴다. 글꼴은 한글 글꼴로 지정.
값 → 좌표는 `y = 바닥y - 값 × 배율` 로 계산한다(아래: 바닥 150, 배율 1.5 → 값 60 = 높이 90).

```html
<figure>
<svg width="460" height="190" viewBox="0 0 460 190" xmlns="http://www.w3.org/2000/svg"
     font-family="Apple SD Gothic Neo" font-size="11" fill="#1f2633">
  <line x1="50" y1="150" x2="440" y2="150" stroke="#8a94a6"/>               <!-- x축 -->
  <!-- 막대: 2024=40, 2025=60, 2026=52 -->
  <rect x="80"  y="90"  width="50" height="60" fill="#2457a6"/><text x="105" y="84" text-anchor="middle">40</text>
  <rect x="200" y="60"  width="50" height="90" fill="#2457a6"/><text x="225" y="54" text-anchor="middle">60</text>
  <rect x="320" y="72"  width="50" height="78" fill="#2457a6"/><text x="345" y="66" text-anchor="middle">52</text>
  <text x="105" y="168" text-anchor="middle">2024</text><text x="225" y="168" text-anchor="middle">2025</text>
  <text x="345" y="168" text-anchor="middle">2026</text>
  <!-- 선: 같은 좌표계에 polyline + 점 -->
  <polyline points="105,120 225,96 345,105" fill="none" stroke="#c27c0e" stroke-width="2"/>
  <circle cx="105" cy="120" r="3" fill="#c27c0e"/><circle cx="225" cy="96" r="3" fill="#c27c0e"/>
  <circle cx="345" cy="105" r="3" fill="#c27c0e"/>
  <text x="440" y="20" text-anchor="end" font-size="10">■ 판매(만 대)  ― 점유율</text>
</svg>
<figcaption>그림 1. 연도별 판매와 점유율 (출처: …)</figcaption>
</figure>
```

## facts.md 와 `--facts`

- 틀: `facts_template.md`. 표 한 줄 = 수치 하나. 범위(`25~30%`)나 어림 표현(`60%대 중반`)을 본문에 쓰려면 그 표현 그대로 facts 에 근거와 함께 적는다.
- 대조 방식: 쉼표·공백·만/천/억/조·million 표기 차이는 맞춰 본다(`733만` = `7,330,000` = `7.33 million`, 반올림 허용).
  %와 %포인트는 같은 묶음으로 본다. 연도 단독, 쪽번호, 각주 번호, `1~4월` 같은 날짜, 1000 미만의 `N대` 는 보지 않는다.
  표지·목차·참고문헌 쪽은 보지 않는다.
- 경고는 어림 표현 → 범위 → 단일 수치 순. "양 끝 값은 facts 에 따로 있음" 은 두 값을 범위로 합친 근거를 확인하라는 뜻.

## 예시

`example/report.html` → `example/report.pdf` (표 쪽 넘김·그림·각주 3개). 막히면 이 파일을 본다.

## 한계

- 목차 쪽 찾기는 PDF 텍스트에서 제목 글자를 찾는 방식. 같은 제목이 두 번 나오면 앞쪽 것을 고를 수 있다.
- 쪽번호(바닥 `n / 전체`)와 목차 번호는 PDF 실제 쪽 기준(표지 = 1쪽).
- 수치 대조는 숫자 일치만 본다. 숫자가 facts 에 있어도 다른 맥락(다른 연도·지역)에 썼는지는 못 잡는다.
  계산한 차이·배수(예: 43km→100km = 132% 상향)는 facts 에 계산식과 함께 적지 않으면 경고된다.
