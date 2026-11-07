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
# 지원: PDF(pdftotext -layout), HTML(태그 제거), 텍스트·CSV·JSON·XML, HWPX(zip 안 XML),
#       XLSX(표준 라이브러리), XLS(xlrd 필요).
#       엑셀은 시트마다 "### 시트: 이름 (행 N, 열 M)" 줄 뒤에 "r행번호<탭>칸<탭>칸..." 으로 적는다
#       (행번호는 엑셀의 실제 행 번호, 날짜 칸은 엑셀 일련번호 숫자 그대로).
#       XLS를 읽을 python: 환경변수 FETCH_DOC_PYTHON → 이 스크립트 옆 ../.venv/bin/python → python3.
#       HWP·DOC(옛 바이너리)·스캔 PDF(글자 없음)는 못 읽는다고 알려 준다.
set -u
URL=""; OUT="./_downloads"; CTX=3; PREVIEW=40; PATS=()
while [ $# -gt 0 ]; do
  case "$1" in
    -g) PATS+=("$2"); shift 2;;
    -C) CTX="$2"; shift 2;;
    -o) OUT="$2"; shift 2;;
    -n) PREVIEW="$2"; shift 2;;
    -h|--help) sed -n '2,20p' "$0"; exit 0;;
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

# 엑셀을 먼저 가려낸다 (HWPX도 zip, HWP·DOC·XLS는 모두 OLE라서).
sig=$(head -c 8 "$raw" | xxd -p)
kind=""
case "$mime" in *spreadsheetml*) kind=xlsx;; esac
if [ -z "$kind" ] && printf '%s' "$sig" | grep -qi '^504b0304' && unzip -Z1 "$raw" 2>/dev/null | grep -qx 'xl/workbook.xml'; then
  kind=xlsx
elif [ -z "$kind" ] && printf '%s' "$sig" | grep -qi '^d0cf11e0'; then
  if [ "$mime" = application/vnd.ms-excel ] \
     || printf '%s' "$URL" | sed -E 's#[?#].*##' | grep -qi '\.xls$' \
     || python3 -I -c 'import sys;b=open(sys.argv[1],"rb").read();sys.exit(0 if ("Workbook".encode("utf-16-le") in b or "Book".encode("utf-16-le") in b) else 1)' "$raw" 2>/dev/null; then
    kind=xls
  else
    kind=ole
  fi
fi

# 엑셀 → 글자. 인자: 모드(xlsx|xls) 원본 출력. 시트 수를 stdout에 찍는다.
xl2txt() {
  "$1" -I - "$2" "$raw" "$txt" <<'PY'
import sys
mode,src,dst=sys.argv[1:4]
def num(x):
    try: f=float(x)
    except (TypeError,ValueError): return str(x)
    return '%.15g'%f
def clean(s):
    s=str(s)
    s=' '.join(s.split()) if any(c in s for c in '\t\r\n') else s
    # 일본·중국 통계표의 균등 배치 'ト　ヨ　タ' -> 'トヨタ' (한 글자씩 전각 공백으로 띄운 칸만)
    parts=s.strip().split('\u3000')
    if len(parts)>1 and all(len(x.strip(' '))==1 for x in parts if x): s=''.join(x.strip(' ') for x in parts)
    return s
def colnum(ref):
    n=0
    for ch in ref:
        if 'A'<=ch<='Z': n=n*26+ord(ch)-64
        else: break
    return n
def rownum(ref):
    d=''.join(ch for ch in ref if ch.isdigit())
    return int(d) if d else 0
sheets=[]  # (이름, {행: {열: 값}})
if mode=='xlsx':
    import zipfile, posixpath, xml.etree.ElementTree as ET
    z=zipfile.ZipFile(src); names=set(z.namelist())
    loc=lambda t: t.rsplit('}',1)[-1]
    def text_of(el):  # <si> 또는 <is>: t, r/t만 (rPh 읽기 안내는 뺀다)
        out=[]
        for ch in el:
            n=loc(ch.tag)
            if n=='t': out.append(ch.text or '')
            elif n=='r':
                for t in ch:
                    if loc(t.tag)=='t': out.append(t.text or '')
        return ''.join(out)
    sst=[]
    if 'xl/sharedStrings.xml' in names:
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')):
            if loc(si.tag)=='si': sst.append(text_of(si))
    rels={}
    if 'xl/_rels/workbook.xml.rels' in names:
        for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')):
            t=r.get('Target','')
            t=t.lstrip('/') if t.startswith('/') else posixpath.normpath(posixpath.join('xl',t))
            rels[r.get('Id')]=t
    order=[]
    for el in ET.fromstring(z.read('xl/workbook.xml')).iter():
        if loc(el.tag)=='sheet':
            rid=next((v for k,v in el.attrib.items() if loc(k)=='id'),None)
            order.append((el.get('name','?'),rels.get(rid)))
    for name,path in order:
        rows={}
        if path and path in names and 'worksheets/' in path:
            rcur=0
            for ev,row in ET.iterparse(z.open(path)):
                if loc(row.tag)!='row': continue
                rcur=int(row.get('r') or rcur+1); ccur=0; cells={}
                for c in row:
                    if loc(c.tag)!='c': continue
                    ref=c.get('r') or ''
                    ccur=colnum(ref) if ref else ccur+1
                    t=c.get('t','n'); v=None; isv=None
                    for ch in c:
                        n=loc(ch.tag)
                        if n=='v': v=ch.text
                        elif n=='is': isv=text_of(ch)
                    if t=='s':
                        try: val=sst[int(v)]
                        except (TypeError,ValueError,IndexError): val=''
                    elif t=='inlineStr': val=isv or ''
                    elif t=='b': val='TRUE' if v=='1' else ('FALSE' if v=='0' else (v or ''))
                    elif t in ('str','e','d'): val=v or ''
                    else: val=num(v) if v not in (None,'') else ''
                    if val!='': cells[ccur]=clean(val)
                if cells: rows[rcur]=cells
                row.clear()
        sheets.append((name,rows))
else:
    import xlrd
    bk=xlrd.open_workbook(src,on_demand=True)
    for i in range(bk.nsheets):
        sh=bk.sheet_by_index(i); rows={}
        for r in range(sh.nrows):
            cells={}
            for c,cell in enumerate(sh.row(r)):
                ct,v=cell.ctype,cell.value
                if ct in (xlrd.XL_CELL_EMPTY,xlrd.XL_CELL_BLANK): continue
                if ct in (xlrd.XL_CELL_NUMBER,xlrd.XL_CELL_DATE): val=num(v)
                elif ct==xlrd.XL_CELL_BOOLEAN: val='TRUE' if v else 'FALSE'
                elif ct==xlrd.XL_CELL_ERROR: val=xlrd.error_text_from_code.get(v,'#ERR')
                else: val=str(v)
                if val.strip()!='': cells[c+1]=clean(val)
            if cells: rows[r+1]=cells
        sheets.append((sh.name,rows)); bk.unload_sheet(i)
with open(dst,'w') as f:
    for name,rows in sheets:
        maxr=max(rows) if rows else 0
        maxc=max((max(c) for c in rows.values()),default=0)
        f.write('### 시트: %s (행 %d, 열 %d)\n'%(name,maxr,maxc))
        for r in sorted(rows):
            cells=rows[r]; last=max(cells)
            f.write('r%d\t%s\n'%(r,'\t'.join(cells.get(c,'') for c in range(1,last+1))))
print(len(sheets))
PY
}

case "$kind" in
  xlsx)
    n=$(xl2txt python3 xlsx) || { echo "저장: $raw (${size}B, ${secs}초) — XLSX를 읽다가 실패했다(깨졌거나 암호 걸린 파일). 같은 자료의 다른 형식(CSV·PDF)을 찾는다."; exit 1; }
    info="XLSX 시트 ${n}개";;
  xls)
    PY="${FETCH_DOC_PYTHON:-}"
    if [ -z "$PY" ]; then
      venv="$(cd "$(dirname "$0")" && pwd)/../.venv/bin/python"
      if [ -x "$venv" ]; then PY="$venv"; else PY=python3; fi
    fi
    if ! "$PY" -I -c 'import xlrd' 2>/dev/null; then
      echo "저장: $raw (${size}B, ${secs}초) — xls는 xlrd 필요: $PY -m pip install xlrd (다른 python은 FETCH_DOC_PYTHON=경로 로 지정)"; exit 1
    fi
    n=$(xl2txt "$PY" xls) || { echo "저장: $raw (${size}B, ${secs}초) — XLS를 읽다가 실패했다(깨졌거나 암호 걸린 파일). 같은 자료의 다른 형식(XLSX·CSV·PDF)을 찾는다."; exit 1; }
    info="XLS 시트 ${n}개";;
  ole)
    echo "저장: $raw (${size}B, ${secs}초) — 옛 HWP/DOC 바이너리라 글자를 뽑지 못한다. 같은 자료의 PDF·HWPX 첨부를 찾는다."; exit 1;;
esac

[ -z "$kind" ] && case "$mime" in
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
case "$kind" in xlsx|xls)
  echo "참고: 시트는 grep -n '^### 시트' \"$txt\" 로 찾고 sed -n 으로 필요한 줄만 본다. 날짜 칸은 엑셀 일련번호(1=1900-01-01, 46000=2025-12-09)로 나온다.";;
esac
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
