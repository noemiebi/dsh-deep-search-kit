#!/usr/bin/env bash
# dsh-deep-search-kit 설치 스크립트
#
# 하는 일
#   1. tools/(fetch_doc.sh, matplotlibrc, report_kit/)를 --tools-dir 에 복사한다.
#   2. profiles/web/*.patch.yml 의 __DSH_TOOLS__ 를 그 폴더의 절대경로로 바꿔 $DSH_HOME/profiles/<프로필>/ 에 둔다.
#   3. 기존 파일이 있고 내용이 다르면 물어본 뒤 .bak-<시각> 으로 백업하고 바꾼다. 거절하면 그 파일은 건너뛴다.
#   프로필의 cordis.patch.yml 은 건드리지 않는다. 패치는 dsh 실행 때 --patch 로 붙인다(끝에 안내).
#
# 사용법
#   ./install.sh [--tools-dir DIR] [--dsh-home DIR] [--profile NAME] [--with-exa] [--yes]
#     --tools-dir DIR   도구를 둘 폴더 (기본: ./_tools, 보통 DSH workspace 안)
#     --dsh-home DIR    DSH 홈 (기본: $DSH_HOME, 없으면 ~/.dsh)
#     --profile NAME    프로필 이름 (기본: web)
#     --with-exa        선택 패치 exa-search.patch.yml 도 설치
#     --yes             묻지 않고 진행 (기존 파일은 백업 후 바꿈)
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="./_tools"
DSH_HOME_DIR="${DSH_HOME:-$HOME/.dsh}"
PROFILE="web"
WITH_EXA=0
YES=0
STAMP="$(date +%Y%m%d-%H%M%S)"

usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --tools-dir) TOOLS_DIR="${2:?--tools-dir 값이 없음}"; shift 2;;
    --dsh-home)  DSH_HOME_DIR="${2:?--dsh-home 값이 없음}"; shift 2;;
    --profile)   PROFILE="${2:?--profile 값이 없음}"; shift 2;;
    --with-exa)  WITH_EXA=1; shift;;
    --yes|-y)    YES=1; shift;;
    -h|--help)   usage; exit 0;;
    *) echo "알 수 없는 옵션: $1" >&2; usage >&2; exit 2;;
  esac
done

# 절대경로로 바꾸기 (폴더가 없으면 만든 뒤)
abspath() { mkdir -p "$1" && (cd "$1" && pwd -P); }

confirm() {  # confirm "질문" → 0=예
  [ "$YES" -eq 1 ] && return 0
  if [ ! -t 0 ]; then echo "  (터미널이 아니라 물을 수 없음 → 건너뜀. --yes 로 진행 가능)"; return 1; fi
  local a; read -r -p "$1 [y/N] " a; [[ "$a" =~ ^[Yy] ]]
}

# 파일 하나 설치: install_file 원본 대상 [치환할 경로]
install_file() {
  local src="$1" dst="$2" sub="${3:-}" tmp
  tmp="$(mktemp)"
  if [ -n "$sub" ]; then
    local body; body="$(cat "$src"; printf x)"; body="${body%x}"
    printf '%s' "${body//__DSH_TOOLS__/$sub}" > "$tmp"
  else
    cp "$src" "$tmp"
  fi
  mkdir -p "$(dirname "$dst")"
  if [ -e "$dst" ]; then
    if cmp -s "$tmp" "$dst"; then echo "  같음, 건너뜀: $dst"; rm -f "$tmp"; return 0; fi
    if confirm "  이미 있음(내용 다름): $dst — 백업 후 바꿀까요?"; then
      cp -p "$dst" "$dst.bak-$STAMP"; echo "  백업: $dst.bak-$STAMP"
    else
      echo "  건너뜀: $dst"; rm -f "$tmp"; return 0
    fi
  fi
  cp "$tmp" "$dst"; rm -f "$tmp"
  [ -x "$src" ] && chmod +x "$dst"
  echo "  설치: $dst"
}

TOOLS_ABS="$(abspath "$TOOLS_DIR")"
PROFILE_DIR="$DSH_HOME_DIR/profiles/$PROFILE"

echo "도구 폴더 : $TOOLS_ABS"
echo "패치 폴더 : $PROFILE_DIR"
[ "$WITH_EXA" -eq 1 ] && echo "선택 패치 : exa-search.patch.yml 포함"
case "$TOOLS_ABS" in *[[:space:]]*)
  echo "경고: 도구 폴더 경로에 공백이 있다. 에이전트가 bash 명령에 경로를 그대로 쓰므로 공백 없는 경로를 권한다." >&2;;
esac
[ -d "$PROFILE_DIR" ] || echo "참고: $PROFILE_DIR 가 아직 없다(dsh --profile $PROFILE 를 한 번 실행하면 생긴다). 새로 만든다."
confirm "진행할까요?" || { echo "취소함"; exit 1; }

echo "[1/2] 도구 복사"
install_file "$SRC/tools/fetch_doc.sh" "$TOOLS_ABS/fetch_doc.sh"
install_file "$SRC/tools/matplotlibrc" "$TOOLS_ABS/matplotlibrc"
while IFS= read -r -d '' f; do
  rel="${f#"$SRC/tools/"}"
  case "$rel" in */.DS_Store|*/__pycache__/*) continue;; esac
  if [ "$rel" = "report_kit/build_pdf.py" ]; then
    install_file "$f" "$TOOLS_ABS/$rel" "$TOOLS_ABS"
  else
    install_file "$f" "$TOOLS_ABS/$rel"
  fi
done < <(find "$SRC/tools/report_kit" -type f -print0 | sort -z)
chmod +x "$TOOLS_ABS/fetch_doc.sh" "$TOOLS_ABS/report_kit/build_pdf.py" 2>/dev/null || true

echo "[2/2] 패치 설치"
install_file "$SRC/profiles/web/deep-search.patch.yml" "$PROFILE_DIR/deep-search.patch.yml" "$TOOLS_ABS"
[ "$WITH_EXA" -eq 1 ] && install_file "$SRC/profiles/web/exa-search.patch.yml" "$PROFILE_DIR/exa-search.patch.yml"

echo "의존 프로그램 확인"
for c in curl file python3 unzip pdftotext pdfinfo; do
  command -v "$c" >/dev/null 2>&1 && echo "  있음: $c" || echo "  없음: $c (fetch_doc.sh 에 필요; pdftotext·pdfinfo 는 poppler)"
done
for c in pdffonts pdftoppm; do
  command -v "$c" >/dev/null 2>&1 && echo "  있음: $c" || echo "  없음: $c (report_kit 선택 기능: 글꼴 검사·미리보기)"
done
if [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ] || \
   [ -x "$HOME/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
  echo "  있음: Google Chrome"
else
  echo "  없음: Google Chrome (report_kit PDF 빌드에 필요)"
fi

echo
echo "끝. 실행 예:"
p="--patch $PROFILE_DIR/deep-search.patch.yml"
[ "$WITH_EXA" -eq 1 ] && p="$p --patch $PROFILE_DIR/exa-search.patch.yml"
echo "  MATPLOTLIBRC=$TOOLS_ABS/matplotlibrc dsh --profile $PROFILE $p"
echo "(MATPLOTLIBRC: 에이전트가 그리는 matplotlib 차트의 한글·한자 글꼴. 쓰지 않으면 빼도 된다)"
echo "적용 확인: 위 명령 끝에 --dump-config 를 붙여 'name: Deep search' 가 보이는지 본다."
