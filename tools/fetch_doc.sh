#!/bin/bash
# fetch_doc.sh — PDF·첨부파일·느린 페이지를 받아 글자로 바꾼다 (web_fetch 대신).
# web_fetch는 PDF를 못 읽고, 접속이 멈추는 서버(일부 정부·기관 서버)에서 30초 제한에 걸린다.
# 이 도구는 5초 안에 접속이 안 되면 끊고 다시 붙는다(최대 6번).
#
# 사용법:
#   fetch_doc.sh URL [-g 찾을말]... [-C 줄수] [-o 폴더] [-n 미리보기줄수]
# 예:
#   fetch_doc.sh "https://example.go.kr/files/notice.pdf" -g "제3조" -g "별표"
#   fetch_doc.sh "https://example.com/report.pdf" -n 80
# 결과:
#   원본과 .txt를 -o 폴더(기본 ./_downloads)에 저장하고 경로·쪽수·글자 수를 알려 준다.
#   -g를 주면 그 말이 있는 줄과 앞뒤 -C줄(기본 3)만 보여 준다(최대 150줄).
#   더 보려면 저장된 .txt를 grep -n / sed -n 으로 읽는다. 전체를 cat 하지 않는다.
# 지원: PDF(pdftotext -layout), HTML(태그 제거), 텍스트·JSON·XML, HWPX(zip 안 XML).
#       HWP(옛 한글 바이너리)·스캔 PDF(글자 없음)는 못 읽는다고 알려 준다.
set -u
URL=""; OUT="./_downloads"; CTX=3; PREVIEW=40; PATS=()
while [ $# -gt 0 ]; do
  case "$1" in
    -g) PATS+=("$2"); shift 2;;
    -C) CTX="$2"; shift 2;;
    -o) OUT="$2"; shift 2;;
    -n) PREVIEW="$2"; shift 2;;
    -h|--help) sed -n '2,17p' "$0"; exit 0;;
    *) URL="$1"; shift;;
  esac
done
[ -z "$URL" ] && { echo "사용법: fetch_doc.sh URL [-g 찾을말]... [-C 줄수] [-o 폴더] [-n 줄수]"; exit 2; }
mkdir -p "$OUT"
base=$(printf '%s' "$URL" | sed -E 's#[?#].*##; s#/+$##; s#.*/##')
[ -z "$base" ] && base="page"
base=$(printf '%s' "$base" | tr -c 'A-Za-z0-9._가-힣-' '_' | cut -c1-80)
raw="$OUT/$base"
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'

start=$(date +%s)
code=$(curl -sS -L -o "$raw" -w '%{http_code}' \
  --connect-timeout 5 --max-time 90 --retry 6 --retry-delay 1 --retry-all-errors \
  -A "$UA" -H 'Accept-Language: ko,en;q=0.8' "$URL" 2>"$raw.err")
rc=$?
secs=$(( $(date +%s) - start ))
if [ $rc -ne 0 ] || [ "${code:-000}" -ge 400 ]; then
  echo "받기 실패 (curl $rc, HTTP ${code:-?}, ${secs}초): $(tail -1 "$raw.err" 2>/dev/null)"
  echo "같은 주소를 계속 다시 시도하지 말고, 같은 자료의 다른 주소(게시판 첨부, 다른 연도판, 기관 보도자료)를 찾는다."
  rm -f "$raw.err" "$raw"; exit 1
fi
rm -f "$raw.err"
size=$(wc -c < "$raw" | tr -d ' ')
mime=$(file -b --mime-type "$raw")
txt="$raw.txt"; info=""

case "$mime" in
  application/pdf)
    pages=$(pdfinfo "$raw" 2>/dev/null | awk '/^Pages:/{print $2}')
    pdftotext -layout "$raw" "$txt" 2>/dev/null
    info="PDF ${pages:-?}쪽";;
  text/html|application/xhtml+xml)
    python3 -I - "$raw" "$txt" <<'PY'
import sys,re,html
b=open(sys.argv[1],'rb').read()
m=re.search(rb'charset=["\']?([A-Za-z0-9_-]+)',b[:4000])
enc=(m.group(1).decode() if m else 'utf-8')
try: s=b.decode(enc,'replace')
except LookupError: s=b.decode('utf-8','replace')
s=re.sub(r'(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>',' ',s)
s=re.sub(r'(?i)<br\s*/?>|</(p|div|tr|li|h[1-6]|table)>','\n',s)
s=re.sub(r'(?i)</t[dh]>',' | ',s)
s=html.unescape(re.sub(r'<[^>]+>',' ',s))
s=re.sub(r'[ \t ]+',' ',s); s=re.sub(r'\n\s*\n+','\n',s)
open(sys.argv[2],'w').write(s.strip()+'\n')
PY
    info="HTML";;
  application/zip|application/hwp+zip|application/x-hwpx|application/octet-stream)
    if unzip -l "$raw" 2>/dev/null | grep -q 'Contents/section'; then
      python3 -I - "$raw" "$txt" <<'PY'
import sys,zipfile,re,html
z=zipfile.ZipFile(sys.argv[1]); out=[]
for n in sorted(x for x in z.namelist() if re.match(r'Contents/section\d+\.xml',x)):
    s=z.read(n).decode('utf-8','replace')
    s=re.sub(r'</hp:p>','\n',s); s=re.sub(r'<[^>]+>','',s); out.append(html.unescape(s))
open(sys.argv[2],'w').write('\n'.join(out))
PY
      info="HWPX"
    elif head -c 8 "$raw" | xxd -p | grep -qi '^d0cf11e0'; then
      echo "저장: $raw (${size}B, ${secs}초) — 옛 HWP/DOC 바이너리라 글자를 뽑지 못한다. 같은 자료의 PDF·HWPX 첨부를 찾는다."; exit 1
    else
      echo "저장: $raw (${size}B, $mime, ${secs}초) — 글자로 바꿀 수 없는 형식."; exit 1
    fi;;
  text/*|application/json|application/xml|*+xml|*+json)
    cp "$raw" "$txt"; info="텍스트($mime)";;
  *)
    echo "저장: $raw (${size}B, $mime, ${secs}초) — 글자로 바꿀 수 없는 형식."; exit 1;;
esac

chars=$(wc -m < "$txt" 2>/dev/null | tr -d ' ')
echo "받음: $URL"
echo "원본: $raw (${size}B, $info, ${secs}초)"
echo "글자: $txt (${chars:-0}자, $(wc -l < "$txt" | tr -d ' ')줄)"
if [ "${chars:-0}" -lt 200 ] && [ "$mime" = application/pdf ]; then
  echo "주의: 글자가 거의 없다 — 스캔(그림) PDF일 수 있다. 필요한 쪽만 그림으로 바꿔 read_image로 본다: pdftoppm -f 쪽 -l 쪽 -r 150 -png \"$raw\" \"$OUT/page\""
fi
if [ ${#PATS[@]} -gt 0 ]; then
  args=(); for p in "${PATS[@]}"; do args+=(-e "$p"); done
  hits=$(grep -c -F "${args[@]}" "$txt")
  echo "찾기(${PATS[*]}): ${hits}줄 일치 — 앞뒤 ${CTX}줄씩, 최대 150줄"
  echo "----"
  grep -n -F -C "$CTX" "${args[@]}" "$txt" | head -150
else
  echo "---- 앞 ${PREVIEW}줄"
  head -n "$PREVIEW" "$txt"
fi
