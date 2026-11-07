# dsh-deep-search-kit

**English summary.** A small kit for the Web profile of DSH (DeepSeek's agent harness, `@deepseek-ai/dsh`). It turns the built-in *Standard* mode (`id: standard`) into a **Deep search** research mode through a profile patch overlay: research rules in the system prompt (primary sources first, search/fetch budgets, cited numbers only, a facts file that survives compaction, chunked writes for long files). It also ships two helper tools the rules point to: `fetch_doc.sh` (reads PDF/HWPX/Excel attachments and slow servers that `web_fetch` cannot handle) and `report_kit` (A4 Korean PDF reports via headless Chrome, with automatic table-of-contents page numbers and a number-vs-facts check). The rules are written in Korean and tell the agent to answer in Korean. Web search is designed around **Exa** (`EXA_API_KEY` required; without it DSH falls back to its default search). macOS only (tested on macOS; Windows and Linux are not supported). Tested with DSH 0.2.1-rc.2.

---

DSH Web 프로필의 **Deep search 모드**용 설정 묶음입니다.

> **macOS 전용** · **웹 검색은 Exa 사용**(Exa API 키 `EXA_API_KEY` 필요). 검색 상한·읽기 방식은 검색 결과에 본문을 함께 주는 Exa 기준으로 맞췄습니다. 키가 없으면 DSH 기본 검색으로 동작하지만 결과가 달라질 수 있습니다.

- **시스템 지시문 패치** `profiles/web/deep-search.patch.yml` — 내장 Standard 모드를 깊은 조사용 "Deep search" 모드로 바꿉니다.
- **문서 받기 도구** `tools/fetch_doc.sh` — PDF·HWPX·엑셀(XLSX·XLS) 첨부, 느린 기관 서버 문서를 받아 글자로 바꿉니다.
- **PDF 보고서 키트** `tools/report_kit/` — 조사 결과를 A4 한글 보고서 PDF로 만듭니다.
- **Exa 검색 연결** `profiles/web/exa-search.patch.yml` — 권장. 설치법은 아래 [Exa 검색](#exa-검색-권장).
- **차트 글꼴** `tools/matplotlibrc` — matplotlib 차트에서 한글·일본어·중국어 한자가 빠지지 않게 합니다.

시험한 버전: `@deepseek-ai/dsh` **0.2.1-rc.2** (macOS). **macOS 전용**입니다.

## 구성요소와 해결한 문제

### deep-search.patch.yml

내장 `preset-standard` 행을 덮어씁니다. DSH patch에서 `config`는 통째로 교체되므로 `@deepseek-ai/dsh-web-app/presets/standard.patch.yml`을 그대로 옮기고 **이름·설명·persona(prefix·suffix)만** 바꿨습니다. 도구 목록(bash, 파일, 웹, subagent, workflow, plan mode 등)은 내장 Standard와 같습니다.

persona suffix에 넣은 조사 규칙 19개가 겨냥한 문제:

| 규칙 | 해결하려던 문제 |
|---|---|
| 1~3 | 결론이 뒤에 묻힘, 무엇을 찾을지 정하지 않고 검색만 반복, 2차 블로그 위주 출처 |
| 4, 12 | 검색·읽기를 끝없이 반복(web_search 15회·web_fetch 15회 상한, subagent 포함 전체 기준, subagent별 몫 배분). web_search는 호출 1번이 1회, fetch_doc.sh는 횟수에 넣지 않음 |
| 5 | 출처끼리 다른 수치를 가리려고 검색을 되풀이 |
| 6 | 조사 질문인데 파일 수정·설치 같은 실행을 함 |
| 7 | 긴 파일을 write 한 번에 쓰다 도구 인자가 너무 길어 연결이 끊김(이미지가 있는 대화는 더 짧게) |
| 8 | 진행 메시지가 영어로 나옴(한국어로 답하게 함 — 다른 언어가 필요하면 이 규칙을 고칩니다) |
| 9~11 | 보고서에 출처 없는 전망 수치를 만들어 넣음, 압축 뒤 요약만 보고 수치를 틀리게 옮김 → `facts.md`에 저장하고 대조 |
| 13 | 문자열 위치 자르기로 HTML을 고치다 문서가 깨짐 |
| 14 | PDF 도구를 매번 새로 찾고(WeasyPrint 설치 시도 등) 목차 쪽번호를 손으로 씀 → `report_kit` 사용 |
| 15 | `web_fetch`가 PDF를 못 읽음, 접속이 멈추는 서버에서 시간 초과 → `fetch_doc.sh` 사용 |
| 16 | 엑셀 구조를 python으로 매번 새로 파싱(한 세션에 15회 넘게 재시도), 차트에서 한자 글자 누락 → `fetch_doc.sh` 엑셀 변환, `matplotlibrc` |
| 17 | 작업 폴더에 쌓인 예전 파일을 확인 없이 근거로 씀, 시작할 때 폴더 전체 목록을 읽느라 문맥 낭비 → 작업마다 하위 폴더 |
| 18 | 막힌 페이지(401·403·로그인·유료)를 계속 다시 부름 → 다른 원천으로, 못 읽은 자료는 밝힘 |
| 19 | 브랜드 합이 전체와 안 맞거나 점유율 합이 100%가 아닌데 그대로 냄 → 다시 계산해 차이와 이유를 적음 |

상한 숫자는 폭주를 막기 위한 값이고 목표가 아닙니다. 환경(모델, 조사 규모, 요금)에 맞게 규칙 4(subagent 몫은 규칙 12)에서 조정합니다.

규칙 14·15에는 도구의 절대경로가 들어가며, 저장소에서는 `__DSH_TOOLS__` 자리표시자로 되어 있습니다(install.sh가 바꿉니다).

### tools/fetch_doc.sh

- `curl --connect-timeout 5 --retry 6 --retry-all-errors`: 접속이 멈추면 5초 만에 끊고 다시 붙습니다(최대 90초).
- PDF는 `pdftotext -layout`, HTML은 태그 제거, HWPX는 zip 안 XML에서 글자를 뽑습니다. 옛 HWP 바이너리·스캔 PDF는 못 읽는다고 알려 줍니다.
- 엑셀: XLSX는 표준 라이브러리로, XLS는 `xlrd`로 읽습니다(`FETCH_DOC_PYTHON`으로 쓸 python 지정 가능, 없으면 `../.venv/bin/python` → `python3`). 시트마다 `### 시트: 이름 (행 N, 열 M)` 뒤에 `r행번호<탭>칸...` 줄로 적어 `-g`·`grep -n`으로 필요한 행만 봅니다. 날짜 칸은 엑셀 일련번호 숫자 그대로입니다.
- 원본과 `.txt`를 `./_downloads/`에 저장하고, `-g 찾을말` 주변 줄만 보여 줘서 문맥 창을 아낍니다.

```
fetch_doc.sh "https://example.go.kr/files/notice.pdf" -g "제3조" -g "별표"
```

### tools/report_kit/

`template.html`을 채워 `build_pdf.py`로 빌드하면 목차 쪽번호를 자동으로 채우고, 반쯤 빈 쪽·깨진 글자·각주 불일치·`facts.md`에 없는 수치를 검사해 `판정: OK`/경고를 출력합니다. 자세한 순서는 `tools/report_kit/README.md`, 예시는 `tools/report_kit/example/`(가상 수치)에 있습니다. DSH 샌드박스 안에서도 돌도록 Chrome 옵션이 들어 있습니다.

## 요구 사항

- **macOS** (시험 환경), **Google Chrome** (`/Applications`), **poppler** (`brew install poppler`), `python3`, `curl`.

세부:

- DSH (`@deepseek-ai/dsh`, Web 프로필). 모델·공급자는 DSH 기본 DeepSeek 공급자를 그대로 씁니다. 다른 공급자를 쓰려면 각자 프로필에서 설정합니다(이 키트는 공급자 설정을 바꾸지 않습니다).
- `fetch_doc.sh`: `bash`, `curl`, `file`, `python3`(표준 라이브러리만, XLSX 포함), `unzip`, **poppler**의 `pdftotext`·`pdfinfo` (`brew install poppler`). XLS를 읽으려면 `xlrd`가 있는 python(`pip install xlrd`, `FETCH_DOC_PYTHON`으로 지정 가능).
- `report_kit/build_pdf.py`: `python3`(표준 라이브러리만, 별도 pip 패키지 없음), **Google Chrome** (`/Applications` 또는 `~/Applications`). 선택: poppler의 `pdftotext`(없으면 macOS PDFKit/`osascript`로 대신 읽음)·`pdffonts`(글꼴 검사)·`pdftoppm`(`--preview` 미리보기).
- 글꼴: `report.css`가 macOS 기본 한글 글꼴 `Apple SD Gothic Neo`를 씁니다.

## 설치 (install.sh)

```bash
git clone https://github.com/noemiebi/dsh-deep-search-kit.git
cd dsh-deep-search-kit
./install.sh --tools-dir ~/dsh-workspace/_tools          # Exa 없이
./install.sh --tools-dir ~/dsh-workspace/_tools --with-exa   # Exa 패치도
```

- 도구를 `--tools-dir`(기본 `./_tools`)에 복사하고, 패치의 `__DSH_TOOLS__`를 그 절대경로로 바꿔 `$DSH_HOME/profiles/web/`(기본 `~/.dsh/profiles/web/`)에 둡니다. `build_pdf.py`의 `KIT_HOME`도 같은 경로로 바꿉니다.
- 같은 이름의 파일이 있고 내용이 다르면 묻고, 승낙하면 `.bak-<시각>`으로 백업한 뒤 바꿉니다. 거절하면 건너뜁니다. `--yes`는 묻지 않고 백업 후 바꿉니다.
- 프로필의 `cordis.patch.yml`은 건드리지 않습니다. 실행할 때 overlay로 붙입니다.

```bash
dsh --profile web --patch ~/.dsh/profiles/web/deep-search.patch.yml
# 확인: 끝에 --dump-config 를 붙이면 'name: Deep search' 가 보입니다.
```

도구 폴더 경로에는 공백이 없는 편이 좋습니다(에이전트가 bash 명령에 경로를 그대로 씁니다). DSH 샌드박스를 쓰면 도구 폴더가 에이전트가 읽고 실행할 수 있는 곳(보통 workspace 안)이어야 합니다.

### Exa 검색 (권장)

```bash
dsh plugin --profile web add @deepseek-ai/dsh-web-search-exa
export EXA_API_KEY=...   # 키는 patch 파일에 적지 않습니다
dsh --profile web --patch ~/.dsh/profiles/web/deep-search.patch.yml --patch ~/.dsh/profiles/web/exa-search.patch.yml
```

`EXA_API_KEY`가 비어 있으면 기본 `deepseek-official` 검색으로 돌아갑니다.

### 차트 글꼴 (matplotlib)

에이전트가 쓰는 python에서 matplotlib 차트를 그릴 때 `tools/matplotlibrc`를 쓰게 합니다. 한글(Apple SD Gothic Neo) 다음에 일본어·중국어 한자 글꼴(Hiragino Sans 등)을 글자마다 찾아 씁니다.

```bash
export MATPLOTLIBRC=~/dsh-workspace/_tools/matplotlibrc   # DSH를 띄우는 환경에
```

## 수동 설치

1. `tools/`를 원하는 곳에 복사합니다.
2. `deep-search.patch.yml`의 `__DSH_TOOLS__`(2곳)와 `report_kit/build_pdf.py`의 `KIT_HOME` 안 `__DSH_TOOLS__`를 그 절대경로로 바꿉니다. (`build_pdf.py`는 자기 폴더의 `report.css`를 먼저 찾으므로 바꾸지 않아도 제자리에서는 동작합니다.)
3. 패치를 `--patch`로 붙이거나, 파일의 `- id: preset-standard` 항목 전체를 `$DSH_HOME/profiles/web/cordis.patch.yml` 목록에 붙여 넣습니다(빈 목록 `[]`이면 `[]`를 지우고 붙입니다).

## 되돌리기

- `--patch` 인자를 빼고 실행하면 내장 Standard 모드로 돌아갑니다. 붙여 넣었다면 그 항목을 지웁니다.
- 설치한 파일은 `$DSH_HOME/profiles/web/deep-search.patch.yml`, `exa-search.patch.yml`, 도구 폴더의 `fetch_doc.sh`·`report_kit/`입니다. 지우면 됩니다. 덮어쓴 파일은 같은 폴더의 `.bak-<시각>`에 있습니다.
- Exa 플러그인: `dsh plugin --profile web remove @deepseek-ai/dsh-web-search-exa`.

## 포함하지 않은 것

원래 설정에서 개인 취향이라 뺀 항목입니다. 필요하면 각자 `cordis.patch.yml`에 넣습니다.

- 내장 모드 숨기기: `- id: preset-ptc` / `preset-minimal` / `preset-cordis` 에 `disabled: true`.
- 새 세션 기본 모드 바꾸기: `- id: agent-preset-registry` 의 `config.default`.
- 모델별 압축 문턱(`compaction-basic`의 `modelPolicies`): 문맥 창이 작은 공급자에서 압축이 너무 잦을 때. 패치 안에 주석 예시가 있습니다.

## 한계

- 내장 Standard 프리셋 전체를 복사한 것이라, DSH 업데이트로 내장 `standard.patch.yml`이 바뀌면 이 패치를 다시 맞춰야 합니다(안 맞추면 새 도구·설정이 빠질 수 있습니다).
- 웹 조사 상한·규칙은 지시문이라 모델이 항상 지키지는 않습니다.
- Windows·Linux는 지원하지 않습니다. `report_kit`은 macOS의 Chrome 경로·`osascript`·한글 글꼴을 쓰고, `fetch_doc.sh`는 bash 스크립트이며, Windows의 DSH는 bash 대신 pwsh 도구를 씁니다. 목차 쪽 찾기·수치 대조의 한계는 `tools/report_kit/README.md`에 있습니다.
- `fetch_doc.sh`는 옛 HWP 바이너리, 스캔 PDF(글자 없음), 로그인·자바스크립트가 필요한 페이지를 읽지 못합니다.
- 규칙이 한국어이고 한국어 답을 전제로 합니다.

## License

MIT — [LICENSE](LICENSE)
