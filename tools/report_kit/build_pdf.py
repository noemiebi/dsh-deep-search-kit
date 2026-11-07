#!/usr/bin/env python3
"""report_kit/build_pdf.py — HTML 보고서 -> PDF (Chrome headless), 목차 쪽번호 자동, 검사 요약.

사용:
  python3 build_pdf.py report.html [-o out.pdf] [--facts facts.md] [--preview 3,5] [--keep-html]
                       [--chrome-flag=--옵션 ...]

이 스크립트를 복사하거나 고친 사본(build_local.py 등)을 만들지 말 것.
Chrome 옵션을 더 넣어야 하면 --chrome-flag 로 넘긴다.

표준 라이브러리만 사용. 외부 프로그램:
  필수  /Applications/Google Chrome.app
  선택  pdftotext / pdffonts / pdftoppm (poppler). pdftotext 가 없으면 macOS PDFKit(osascript)로 대신 읽음.
"""
import argparse
import html
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent
KIT_HOME = Path("__DSH_TOOLS__/report_kit")   # install.sh 가 실제 경로로 바꿈. 사본에서 실행돼도 원본 CSS 를 찾음
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
]
# DSH 샌드박스(seatbelt, ~/Library 쓰기 금지) 안에서도 돌게 하는 옵션.
# --no-sandbox 가 없으면 Chrome 자체 샌드박스가 겹쳐 GPU 프로세스가 exit 6 으로 죽는다(2026-11-07 실측).
CHROME_FLAGS = [
    "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
    "--disable-crash-reporter", "--disable-breakpad",
    "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--hide-scrollbars",
    "--disable-background-networking", "--disable-sync", "--mute-audio",
    "--no-pdf-header-footer", "--print-to-pdf-no-header",
    "--virtual-time-budget=10000",
]
CHROME_RETRY_FLAGS = ["--in-process-gpu", "--use-angle=swiftshader"]   # 1차 실패 시 한 번 더 (--single-process 는 샌드박스에서 죽음)
RENDER_TIMEOUT = 120
NEAR_EMPTY_RATIO = 0.40     # 본문 쪽 글자 수 중앙값의 40% 미만이면 경고
NEAR_EMPTY_MIN = 150        # pdftotext -bbox 를 못 쓸 때만: 이 글자 수 미만이면 경고
HALF_EMPTY_Y = 0.50         # 마지막 글줄이 쪽 높이의 이 비율보다 위에서 끝나면 경고
FILLED_Y = 0.65             # 글자가 적어도 마지막 글줄이 이 비율보다 아래면 그림 쪽으로 보고 경고 안 함
MAX_PREVIEW = 4
PREVIEW_RUNS_OK = 2         # 같은 출력 PDF 에 --preview 를 이 횟수보다 많이 쓰면 경고
APPEND_MARK = "<!-- @@APPEND@@ -->"


def which(name):
    p = shutil.which(name)
    if p:
        return p
    for d in ("/opt/homebrew/bin", "/usr/local/bin"):
        c = os.path.join(d, name)
        if os.access(c, os.X_OK):
            return c
    return None


# ---------------------------------------------------------------- HTML 분석
class Scan(HTMLParser):
    """목차 항목(data-target), id 별 텍스트, 각주·참고문헌·이미지 수집."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.toc = []            # [(target, toc_text, is_sub)]
        self.id_text = {}        # id -> text
        self._cap = []           # [[id, tag, depth, parts]]
        self._toc_li = None      # [target, parts, is_sub, depth]
        self.depth = 0
        self.fn_refs = []        # 본문 각주 href 번호
        self.ref_ids = []        # 참고문헌 li id 순서
        self._in_refs = 0
        self._ref_li = None      # [id, parts, depth]
        self.ref_texts = {}
        self.imgs = []

    VOID = {"br", "img", "hr", "meta", "link", "input", "source", "col", "wbr"}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "img" and a.get("src"):
            self.imgs.append(a["src"])
        if tag in self.VOID:
            return
        self.depth += 1
        if tag == "li" and a.get("data-target"):
            self._toc_li = [a["data-target"], [], "sub" in (a.get("class") or "").split(), self.depth]
        if a.get("id"):
            self._cap.append([a["id"], tag, self.depth, []])
        if tag == "a" and "fn" in (a.get("class") or "").split():
            m = re.match(r"#ref-(\d+)$", a.get("href", ""))
            self.fn_refs.append(int(m.group(1)) if m else -1)
        if tag == "ol" and "refs" in (a.get("class") or "").split():
            self._in_refs = self.depth
        if self._in_refs and tag == "li" and self._ref_li is None:
            self._ref_li = [a.get("id", ""), [], self.depth]

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        d = self.depth
        if self._toc_li and self._toc_li[3] == d:
            t, parts, sub, _ = self._toc_li
            self.toc.append((t, norm_space("".join(parts)), sub))
            self._toc_li = None
        for c in list(self._cap):
            if c[2] == d:
                self.id_text[c[0]] = norm_space("".join(c[3]))
                self._cap.remove(c)
        if self._ref_li and self._ref_li[2] == d:
            self.ref_ids.append(self._ref_li[0])
            self.ref_texts[self._ref_li[0]] = "".join(self._ref_li[1])
            self._ref_li = None
        if self._in_refs == d:
            self._in_refs = 0
        self.depth -= 1

    def handle_data(self, data):
        if self._toc_li:
            self._toc_li[1].append(data)
        for c in self._cap:
            c[3].append(data)
        if self._ref_li:
            self._ref_li[1].append(data)


def norm_space(s):
    return re.sub(r"\s+", " ", s).strip()


def squash(s):
    return re.sub(r"[\s​ ]+", "", s)


# ---------------------------------------------------------------- 렌더
def find_chrome():
    for c in CHROME_CANDIDATES:
        if os.access(c, os.X_OK):
            return c
    sys.exit("오류: Google Chrome 을 찾지 못함 (/Applications/Google Chrome.app)")


NOISE = re.compile(r"crashpad|task_policy_set|process_memory_mac|mach_vm_read|"
                   r"DEPRECATED_ENDPOINT|fontconfig|Fontconfig|CVDisplayLink|allocator multiple times|V8 Proxy resolver", re.I)


def _run_chrome(cmd):
    """Chrome 실행. (returncode, stderr 텍스트, 시간초과 여부). 시간 초과면 프로세스 묶음을 통째로 끈다."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        _, err = p.communicate(timeout=RENDER_TIMEOUT)
        return p.returncode, err.decode("utf-8", "replace"), False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            p.kill()
        _, err = p.communicate()
        return None, err.decode("utf-8", "replace"), True


def _mk_profile(pdf_path):
    """임시 user-data-dir. TMPDIR 에 못 쓰면 출력 폴더 아래에 만든다."""
    for base in (None, str(pdf_path.parent)):
        try:
            return tempfile.mkdtemp(prefix="rk_chrome_", dir=base)
        except OSError:
            continue
    sys.exit("오류: 임시 폴더를 만들 수 없음 (TMPDIR, 출력 폴더 모두 쓰기 실패)")


def stderr_summary(err, n=6):
    keep, seen = [], set()
    for ln in err.splitlines():
        ln = ln.strip()
        if not ln or NOISE.search(ln):
            continue
        k = re.sub(r"^\[[^\]]*\]\s*", "", ln)[:160]
        if k in seen:
            continue
        seen.add(k)
        keep.append(k)
    return keep[-n:]


def render(chrome, html_path, pdf_path, extra_flags=()):
    tries = [[], CHROME_RETRY_FLAGS]
    logs = []
    for k, more in enumerate(tries, 1):
        prof = _mk_profile(pdf_path)
        try:
            cmd = [chrome] + CHROME_FLAGS + list(more) + list(extra_flags) + [
                "--user-data-dir=" + prof, "--crash-dumps-dir=" + prof,
                "--print-to-pdf=" + str(pdf_path), Path(html_path).resolve().as_uri()]
            if pdf_path.exists():
                pdf_path.unlink()
            rc, err, timed_out = _run_chrome(cmd)
        finally:
            shutil.rmtree(prof, ignore_errors=True)
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            if k > 1:
                print("참고: Chrome 1차 실패, 재시도 옵션(%s)으로 성공" % " ".join(more))
            return
        logs.append((k, more, rc, timed_out, err))
    out = ["오류: PDF 생성 실패 (Chrome %d회 시도)" % len(tries)]
    for k, more, rc, timed_out, err in logs:
        state = "시간 초과(%d초)" % RENDER_TIMEOUT if timed_out else "종료 코드 %s" % rc
        out.append("-- 시도 %d %s: %s" % (k, ("[" + " ".join(more) + "]") if more else "[기본 옵션]", state))
        summ = stderr_summary(err)
        out += ["   " + s for s in summ] or ["   (stderr 에 쓸 만한 내용 없음)"]
    allerr = "\n".join(l[4] for l in logs)
    out.append("다음에 시도할 것:")
    if "GPU process" in allerr:
        out.append("  - GPU 프로세스가 죽음: 샌드박스 충돌. --no-sandbox·--disable-gpu·--in-process-gpu 를 이미 썼으므로"
                   " 옵션을 더 바꾸지 말고, 위 오류 줄을 그대로 사용자에게 보고")
    if any(l[3] for l in logs):
        out.append("  - 시간 초과: 외부 URL 이미지·웹폰트(<link href=\"http...\">)를 지우고 재실행")
    if re.search(r"Operation not permitted|Permission denied|Read-only", allerr):
        out.append("  - 쓰기 권한 오류: -o 로 작업 폴더 안의 경로를 지정했는지 확인 (작업 폴더 밖·~/Library 는 못 씀)")
    out.append("  - 같은 명령을 한 번 더 실행 (일시적 실패일 수 있음)")
    out.append("  - 옵션 추가는 --chrome-flag=--옵션 으로. build_pdf.py 사본(build_local.py 등)은 만들지 말 것")
    out.append("  - 그래도 안 되면 HTML 을 반으로 줄여 어느 부분이 문제인지 확인")
    sys.exit("\n".join(out))


# ---------------------------------------------------------------- PDF 텍스트
JXA = r"""
ObjC.import('PDFKit');
function run(argv) {
  var d = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));
  var out = [];
  for (var i = 0; i < d.pageCount; i++) {
    var s = d.pageAtIndex(i).string;
    out.push(s.isNil() ? "" : ObjC.unwrap(s));
  }
  return JSON.stringify(out);
}
"""


def page_texts(pdf):
    """쪽별 텍스트 리스트와 사용한 방법."""
    pt = which("pdftotext")
    if pt:
        r = subprocess.run([pt, "-enc", "UTF-8", str(pdf), "-"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        pages = r.stdout.decode("utf-8", "replace").split("\f")
        if pages and pages[-1].strip() == "":
            pages = pages[:-1]
        return pages, "pdftotext"
    r = subprocess.run(["osascript", "-l", "JavaScript", "-e", JXA, str(pdf)],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode == 0:
        return json.loads(r.stdout.decode("utf-8")), "PDFKit(osascript)"
    return None, "없음"


def locate(pages, toc):
    """목차 항목 -> 쪽번호(1부터). 반환 (dict, toc_page_index)."""
    sq_pages = [squash(p) for p in pages]
    lines = [[squash(l) for l in p.splitlines() if l.strip()] for p in pages]
    titles = [squash(t) for _, t, _ in toc]
    # 목차 쪽 = 앞쪽 몇 장 중 목차 제목을 가장 많이 담은 쪽
    best, toc_idx = -1, 0
    for i, sp in enumerate(sq_pages[:6]):
        n = sum(1 for t in titles if t and t in sp)
        if n > best:
            best, toc_idx = n, i

    def line_hit(i, t):
        ls = lines[i]
        for k in range(len(ls)):
            acc = ""
            for j in range(k, min(k + 3, len(ls))):   # 제목이 2~3줄로 접힌 경우
                acc += ls[j]
                if acc == t:
                    return True
                if not t.startswith(acc):
                    break
        return False

    result, prev = {}, toc_idx + 1
    for (target, _, _), t in zip(toc, titles):
        found = None
        if t:
            for test in (line_hit, lambda i, t: t in sq_pages[i]):
                for i in list(range(prev, len(pages))) + list(range(toc_idx + 1, prev)):
                    if test(i, t):
                        found = i
                        break
                if found is not None:
                    break
        result[target] = None if found is None else found + 1
        if found is not None and found >= prev:
            prev = found
    return result, toc_idx + 1


def fill_toc(src, mapping):
    def rep(m):
        li_open, body = m.group(1), m.group(2)
        t = re.search(r'data-target="([^"]+)"', li_open).group(1)
        pn = mapping.get(t)
        val = "" if pn is None else str(pn)
        body = re.sub(r'(<span class="toc-pn">)(.*?)(</span>)',
                      lambda mm: mm.group(1) + val + mm.group(3), body, count=1, flags=re.S)
        return li_open + body
    return re.sub(r'(<li\b[^>]*data-target="[^"]+"[^>]*>)(.*?)(?=</li>)', rep, src, flags=re.S)


def page_bottoms(pdf):
    """pdftotext -bbox-layout 로 쪽마다 (마지막 본문 글줄 아래끝 / 쪽 높이) 비율. 바닥 쪽번호 줄은 뺀다."""
    pt = which("pdftotext")
    if not pt:
        return None
    r = subprocess.run([pt, "-bbox-layout", str(pdf), "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if r.returncode != 0:
        return None
    doc = r.stdout.decode("utf-8", "replace")
    res = []
    for pm in re.finditer(r'<page width="[\d.]+" height="([\d.]+)">(.*?)</page>', doc, re.S):
        h = float(pm.group(1))
        bottom = 0.0
        for lm in re.finditer(r'<line [^>]*yMin="([\d.]+)"[^>]*yMax="([\d.]+)">(.*?)</line>', pm.group(2), re.S):
            words = "".join(re.findall(r">([^<]*)</word>", lm.group(3)))
            if re.fullmatch(r"\d+/\d+", words.replace(" ", "")):      # 바닥 쪽번호 "n / N"
                continue
            bottom = max(bottom, float(lm.group(2)))
        res.append(bottom / h if h else 0.0)
    return res


def page_heading(p, toc, mapping):
    """p 쪽(1부터)의 첫 제목. 그 쪽에서 시작하는 제목이 없으면 앞 제목을 '…이어짐'으로."""
    prev = None
    for target, text, _ in toc:
        pn = mapping.get(target)
        if pn == p:
            return "'%s'" % text
        if pn and pn < p:
            prev = text
    return ("'%s' 이어짐" % prev) if prev else "제목 없음"


# ---------------------------------------------------------------- 수치 대조 (--facts)
NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
SCALE_KO = {"조": 1e12, "억": 1e8, "만": 1e4, "천": 1e3}
SCALE_EN = {"trillion": 1e12, "billion": 1e9, "bn": 1e9, "million": 1e6, "mn": 1e6}
AMT = (r"(?:(?:%(n)s)\s*(?:조|억|만|천)(?:\s*(?:%(n)s)\s*(?:억|만|천))*(?:\s*(?:%(n)s)(?![\d.,]|\s*(?:조|억|만|천)))?"
       r"|(?:%(n)s)(?:\s*(?:trillion|billion|million|bn|mn)\b)?)") % {"n": NUM}
CUR_PRE = r"(?:US\$|\$|€|CN¥|¥|RMB\s?|EUR\s?|USD\s?)"
UNIT = (r"(?:%\s*포인트|%p\b|%P\b|퍼센트포인트|percentage points?|%|퍼센트|percent\b|배|"
        r"(?:원|달러|유로|위안)|(?:대|units?\b|vehicles\b|cars\b))")
RANGE_SEP = r"\s*[~∼〜～–]\s*"
SINGLE_RE = re.compile(r"(?<![\d.,])(?P<cur>%s)?(?P<amt>%s)\s*(?P<unit>%s)?" % (CUR_PRE, AMT, UNIT))
RANGE_RE = re.compile(r"(?<![\d.,])(?P<cur>%s)?(?P<a>%s)\s*(?P<ua>%s)?%s(?P<b>%s)\s*(?P<ub>%s)"
                      % (CUR_PRE, AMT, UNIT, RANGE_SEP, AMT, UNIT))
VAGUE_RE = re.compile(r"(?<![\d.,])(?P<v>\d{1,2}0)\s*%\s*(?:대(?!비|상|해)|(?=\s*(?:초반|중반|후반|중후반|초중반)))"
                      r"(?:\s*(?P<q>초중반|중후반|초반|중반|후반))?")


def _unit_kind(unit, cur):
    u = (unit or "").replace(" ", "")
    if u.startswith("%포인트") or u in ("%p", "%P", "퍼센트포인트") or u.startswith("percentagepoint"):
        return "pct"          # %포인트도 % 와 같은 묶음으로 대조 (오탐 줄이기)
    if u in ("%", "퍼센트", "percent"):
        return "pct"
    if u == "배":
        return "mult"
    if u or cur:
        return "num"
    return None


def _amount(s):
    """'2,053만' -> (20530000.0, 단위크기 1e4, 소수자릿수 0). '7.334 million' -> (7334000, 1e6, 3)."""
    s = s.strip()
    m = re.match(r"(%s)\s*(trillion|billion|million|bn|mn)\b" % NUM, s)
    if m:
        v = m.group(1).replace(",", "")
        dec = len(v.split(".")[1]) if "." in v else 0
        sc = SCALE_EN[m.group(2)]
        return float(v) * sc, sc, dec
    total, last_sc, dec, rest = 0.0, 1.0, 0, s
    for m in re.finditer(r"(%s)\s*(조|억|만|천)?" % NUM, s):
        v = m.group(1).replace(",", "")
        sc = SCALE_KO.get(m.group(2), 1.0)
        total += float(v) * sc
        last_sc = sc
        dec = len(v.split(".")[1]) if "." in v else 0
    return total, last_sc, dec


def _has_scale(s):
    return bool(re.search(r"조|억|만|천|illion|bn|mn", s))


def extract_values(text, facts_mode=False):
    """텍스트에서 수치 표현 추출. 반환 [(kind, 값, 허용오차, 표기, 시작, 끝, 종류)] 종류 = single/range/vague.
    facts_mode 면 단위 없는 큰 수(1,647,988 / 4자리 이상)도 num 으로 받는다."""
    out, used = [], []

    def taken(a, b):
        return any(a < y and b > x for x, y in used)

    for m in VAGUE_RE.finditer(text):
        v = float(m.group("v"))
        q = m.group("q") or ""
        band = {"": (0, 10), "초반": (0, 4), "초중반": (0, 6), "중반": (3, 7), "중후반": (4, 10), "후반": (6, 10)}[q]
        out.append(("pct", (v + band[0], v + band[1]), 0, m.group(0).strip(), m.start(), m.end(), "vague"))
        used.append((m.start(), m.end()))
    for m in RANGE_RE.finditer(text):
        if taken(m.start(), m.end()):
            continue
        ub, ua = m.group("ub"), m.group("ua")
        kind = _unit_kind(ub, m.group("cur"))
        if kind is None or (ua and _unit_kind(ua, m.group("cur")) != kind):
            continue
        b, bsc, bdec = _amount(m.group("b"))
        a, asc, adec = _amount(m.group("a"))
        if not _has_scale(m.group("a")) and _has_scale(m.group("b")):
            a, asc = a * bsc, bsc                      # '35~40만 대' -> 35만
        if kind == "num" and not _has_scale(m.group("b")) and b < 1000 and (ub or "").strip() in ("대",):
            continue
        tol = 0.5 * max(asc * 10 ** -adec, bsc * 10 ** -bdec)
        out.append((kind, (a, b), tol, m.group(0).strip(), m.start(), m.end(), "range"))
        used.append((m.start(), m.end()))
    for m in SINGLE_RE.finditer(text):
        if taken(m.start(), m.end()):
            continue
        amt, unit, cur = m.group("amt"), m.group("unit"), m.group("cur")
        kind = _unit_kind(unit, cur)
        val, sc, dec = _amount(amt)
        if kind is None:
            if _has_scale(amt):
                kind = "num"                            # '120억', '35만'
            elif facts_mode and ("," in amt or val >= 1000):
                kind = "num"
            else:
                continue
        if kind == "num" and not _has_scale(amt) and not cur:
            u = (unit or "").strip()
            if u in ("대", "") and val < 1000 and not facts_mode:
                continue                                # '4대 중 1대', '3대 업체'
            if not facts_mode and u == "" :
                continue
            if not facts_mode and re.fullmatch(r"(19|20)\d\d", amt) and u in ("대", ""):
                continue
        tol = 0.5 * sc * 10 ** -dec
        out.append((kind, val, tol, m.group(0).strip(), m.start(), m.end(), "single"))
        used.append((m.start(), m.end()))
    return out


def load_facts(paths):
    singles, ranges, vagues = [], [], set()
    for p in paths:
        t = Path(p).read_text(encoding="utf-8", errors="replace")
        for kind, val, tol, raw, _, _, typ in extract_values(t, facts_mode=True):
            if typ == "vague":
                vagues.add(re.sub(r"\s+", "", raw))
            elif typ == "range":
                ranges.append((kind, val[0], val[1]))
                singles += [(kind, val[0]), (kind, val[1])]
            else:
                singles.append((kind, val))
    return singles, ranges, vagues


def _near(a, b, tol):
    return abs(a - b) <= tol + 1e-9 * max(1.0, abs(a))


def check_facts(pages, skip_pages, facts):
    """반환: [(종류, 표기, [쪽...], 문맥, 힌트)]"""
    singles, ranges, vagues = facts
    by_kind = {}
    for k, v in singles:
        by_kind.setdefault(k, []).append(v)
    found = {}
    for i, ptxt in enumerate(pages):
        pno = i + 1
        if pno in skip_pages:
            continue
        text = re.sub(r"[ \t]*\n[ \t]*", " ", ptxt)
        for kind, val, tol, raw, s, e, typ in extract_values(text):
            hint = ""
            if typ == "vague":
                if re.sub(r"\s+", "", raw) in vagues:
                    continue
                lo, hi = val
                near = sorted({v for v in by_kind.get("pct", []) if lo <= v < hi})
                hint = ("facts 의 이 구간 값: " + ", ".join("%g%%" % v for v in near[:5])) if near else "facts 에 이 구간 값 없음"
            elif typ == "range":
                lo, hi = val
                if any(k == kind and _near(lo, a, tol) and _near(hi, b, tol) for k, a, b in ranges):
                    continue
                pool = by_kind.get(kind, [])
                has = [any(_near(x, v, tol) for v in pool) for x in (lo, hi)]
                hint = "양 끝 값은 facts 에 따로 있음 — 범위로 합친 근거 확인" if all(has) else "facts 에 같은 범위 없음"
            else:
                pool = by_kind.get(kind, [])
                if any(_near(abs(val), abs(v), tol) for v in pool):
                    continue
            key = (typ, kind, re.sub(r"\s+", "", raw))
            ctx = text[max(0, s - 28):e + 28].strip()
            if key not in found:
                found[key] = [typ, raw, [pno], ctx, hint]
            elif pno not in found[key][2]:
                found[key][2].append(pno)
    order = {"vague": 0, "range": 1, "single": 2}
    return sorted(found.values(), key=lambda x: (order[x[0]], x[2][0]))


def kit_css():
    for d in (KIT_DIR, KIT_HOME):
        if (d / "report.css").exists():
            return (d / "report.css").read_text(encoding="utf-8")
    sys.exit("오류: report.css 를 찾지 못함 (%s, %s)" % (KIT_DIR, KIT_HOME))


def inline_css(src, html_dir):
    m = re.search(r'<link[^>]+href="report\.css"[^>]*>', src)
    if m and not (html_dir / "report.css").exists():
        src = src[:m.start()] + "<style>\n" + kit_css() + "\n</style>" + src[m.end():]
    return src


def merge_appended(src_path, src):
    """cat >> 로 </html> 뒤에 붙인 조각을 표시 지점(APPEND_MARK) 바로 위로 옮겨 report.html 에 저장."""
    masked = re.sub(r"<!--.*?-->", lambda c: " " * len(c.group(0)), src, flags=re.S)   # 주석 속 </html> 무시
    m = re.search(r"</html>\s*", masked, re.I)
    if not m or not src[m.end():].strip():
        return src, None
    tail = src[m.end():].rstrip() + "\n"
    head = src[:m.start()] + "</html>\n"
    if APPEND_MARK not in head:
        return src, ("</html> 뒤에 붙은 내용 %d자가 있는데 표시 지점 %s 이 없음 — "
                     "조각을 </body> 앞으로 옮길 것" % (len(tail), APPEND_MARK))
    new = head.replace(APPEND_MARK, tail + APPEND_MARK, 1)
    src_path.write_text(new, encoding="utf-8")
    print("참고: </html> 뒤에 cat >> 로 붙인 조각 %d자를 표시 지점으로 옮겨 %s 에 저장함" % (len(tail), src_path.name))
    return new, None


def count_preview(out):
    log = out.parent / (".%s_preview.log" % out.stem)
    try:
        n = int(log.read_text().strip() or 0) + 1
    except (OSError, ValueError):
        n = 1
    try:
        log.write_text(str(n))
    except OSError:
        pass
    return n


# ---------------------------------------------------------------- 메인
def main():
    ap = argparse.ArgumentParser(description="HTML 보고서를 PDF 로 만들고 검사 요약을 출력")
    ap.add_argument("html")
    ap.add_argument("-o", "--out", help="출력 PDF (기본: 입력과 같은 이름 .pdf)")
    ap.add_argument("--facts", action="append", metavar="FILE",
                    help="수치 출처 파일(facts.md 등). PDF 수치 중 이 파일에 없는 것을 경고. 여러 번 줄 수 있음")
    ap.add_argument("--preview", help="PNG 로 볼 쪽 번호, 예: 1,3 (최대 4쪽, 저해상도)")
    ap.add_argument("--dpi", type=int, default=60, help="미리보기 해상도 (기본 60)")
    ap.add_argument("--keep-html", action="store_true", help="쪽번호를 채운 중간 HTML 을 남김")
    ap.add_argument("--chrome-flag", action="append", default=[], metavar="FLAG",
                    help="Chrome 옵션 추가, 예: --chrome-flag=--in-process-gpu (스크립트 사본 대신 이것을 쓸 것)")
    a = ap.parse_args()

    src_path = Path(a.html).resolve()
    if not src_path.exists():
        sys.exit("오류: 입력 파일 없음: %s" % src_path)
    for f in a.facts or []:
        if not Path(f).exists():
            sys.exit("오류: --facts 파일 없음: %s" % f)
    out = Path(a.out).resolve() if a.out else src_path.with_suffix(".pdf")
    html_dir = src_path.parent
    warns = []
    src = src_path.read_text(encoding="utf-8")
    src, w = merge_appended(src_path, src)
    if w:
        warns.append(w)
    src = inline_css(src, html_dir)

    scan = Scan()
    scan.feed(src)
    chrome = find_chrome()
    build_html = html_dir / (".%s.build.html" % src_path.stem)

    def write_and_render(text):
        build_html.write_text(text, encoding="utf-8")
        render(chrome, build_html, out, a.chrome_flag)

    renders = 0
    mapping, toc_page, method = {}, None, None
    cur = fill_toc(src, {}) if scan.toc else src
    try:
        write_and_render(cur)
        renders += 1
        pages, method = page_texts(out)
        if scan.toc and pages is not None:
            for _ in range(3):
                new_map, toc_page = locate(pages, scan.toc)
                if new_map == mapping:
                    break
                mapping = new_map
                cur = fill_toc(src, mapping)
                write_and_render(cur)
                renders += 1
                pages, _ = page_texts(out)
            else:
                final_map, _ = locate(pages, scan.toc)
                if final_map != mapping:
                    warns.append("목차 쪽번호가 3회 재렌더 후에도 수렴하지 않음 — 목차 길이를 확인")
        elif scan.toc:
            warns.append("PDF 텍스트를 읽을 수 없어 목차 쪽번호를 채우지 못함")
    finally:
        if not a.keep_html and build_html.exists():
            build_html.unlink()

    # ---------------- 검사 요약
    print("== report_kit 검사 요약 ==")
    print("PDF: %s (%.0f KB, 렌더 %d회, 텍스트: %s)" % (out, out.stat().st_size / 1024, renders, method))
    if pages is None:
        print("쪽별 검사 생략: pdftotext 도 PDFKit 도 사용 불가")
        return 1
    n = len(pages)
    print("총 쪽수: %d" % n)
    counts = [len(squash(p)) for p in pages]
    print("쪽별 글자 수: " + "  ".join("p%d=%d" % (i + 1, c) for i, c in enumerate(counts)))

    # 빈 쪽: 표지·목차·마지막 쪽 제외, 본문 쪽 글자 수 중앙값 대비 + 마지막 글줄 위치
    skip = {1, n} | ({toc_page} if toc_page else set())
    refs_pn = next((mapping.get(t) for t, txt, _ in scan.toc if "참고문헌" in txt or t == "refs"), None)
    body = [counts[i] for i in range(n) if i + 1 not in skip]
    med = statistics.median(body) if body else 0
    bottoms = page_bottoms(out)
    if bottoms is not None and len(bottoms) != n:
        bottoms = None
    # 글줄 위치를 못 읽을 때만 절대 하한(150자)을 함께 쓴다
    limit = NEAR_EMPTY_RATIO * med if bottoms else max(NEAR_EMPTY_MIN, NEAR_EMPTY_RATIO * med)
    if body:
        print("빈 쪽 기준: 본문 쪽 중앙값 %d자의 %d%% = %d자 미만%s" % (
            med, NEAR_EMPTY_RATIO * 100, limit,
            ", 또는 마지막 글줄이 쪽 위쪽 %d%% 안에서 끝남" % (HALF_EMPTY_Y * 100) if bottoms else ""))
    for i in range(n):
        p = i + 1
        if p in skip:
            continue
        why = []
        low = counts[i] < limit
        if low and bottoms and bottoms[i] >= FILLED_Y:
            # 글자는 적지만 쪽 아래까지 차 있음 = 그림·표 위주 쪽. 경고 대신 참고로만.
            print("참고: p%d 글자 적음(%d자)이나 쪽 %d%% 지점까지 차 있음 — 그림 쪽이면 정상"
                  % (p, counts[i], 100 * bottoms[i]))
            low = False
        if low:
            why.append("%d자(중앙값의 %d%%)" % (counts[i], 100 * counts[i] / med if med else 0))
        if bottoms and bottoms[i] < HALF_EMPTY_Y and p + 1 != refs_pn:   # 참고문헌 바로 앞(본문 끝) 쪽은 짧아도 정상
            why.append("글이 쪽 높이 %d%% 지점에서 끝남" % (100 * bottoms[i]))
        if why:
            warns.append("p%d 반쯤 빈 쪽 [%s] — 첫 제목 %s. 불필요한 page-break, 다음 쪽으로 밀린 큰 표·그림 확인"
                         % (p, ", ".join(why), page_heading(p, scan.toc, mapping)))

    if scan.toc:
        print("목차 쪽: p%s" % toc_page)
        print("제목별 쪽:")
        for target, text, sub in scan.toc:
            pn = mapping.get(target)
            print("  %s%-40s p%s" % ("  " if sub else "", text, pn if pn else "?"))
            if pn is None:
                warns.append("목차 '%s' 의 쪽을 찾지 못함 — 본문 제목(id=%s) 글자가 목차와 같은지 확인" % (text, target))
            body_t = scan.id_text.get(target)
            if body_t is None:
                warns.append("목차 data-target='%s' 에 해당하는 id 가 본문에 없음" % target)
            elif squash(body_t) != squash(text):
                warns.append("목차 글자와 본문 제목이 다름: '%s' vs '%s'" % (text, body_t))

    bad = [(i + 1, p.count("�")) for i, p in enumerate(pages) if "�" in p]
    if bad:
        warns.append("깨진 글자(U+FFFD): " + ", ".join("p%d %d개" % b for b in bad))
    else:
        print("깨진 글자(U+FFFD): 없음")

    pf = which("pdffonts")
    if pf:
        r = subprocess.run([pf, str(out)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        fonts = sorted({ln.split()[0].split("+")[-1] for ln in
                        r.stdout.decode("utf-8", "replace").splitlines()[2:] if ln.strip()})
        print("포함 글꼴: " + ", ".join(fonts))
        if any("LastResort" in f for f in fonts):
            warns.append("LastResort 글꼴 포함 — 네모(□)로 보이는 글자가 있음. 지원 안 되는 문자/글꼴 확인")

    # 각주·참고문헌
    if scan.ref_ids or scan.fn_refs:
        nrefs = len(scan.ref_ids)
        print("각주: 본문 인용 %d곳, 참고문헌 %d개" % (len(scan.fn_refs), nrefs))
        for k, rid in enumerate(scan.ref_ids, 1):
            if rid != "ref-%d" % k:
                warns.append("참고문헌 %d번째 li 의 id 가 '%s' (ref-%d 이어야 함)" % (k, rid, k))
            txt = scan.ref_texts.get(rid, "")
            if "http" not in txt:
                warns.append("참고문헌 [%d] 에 URL 글자가 없음" % k)
            if re.match(r"\s*\[\d+\]", txt):
                warns.append("참고문헌 [%d] li 안에 번호를 직접 씀 — 번호가 두 번 찍힘" % k)
        cited = set(scan.fn_refs)
        for c in sorted(cited):
            if c < 1 or c > nrefs:
                warns.append("본문 각주 [%s] 에 해당하는 참고문헌 없음" % c)
        unused = [k for k in range(1, nrefs + 1) if k not in cited]
        if unused:
            warns.append("본문에서 인용 안 된 참고문헌: " + ", ".join("[%d]" % k for k in unused))

    for s in scan.imgs:
        if re.match(r"(https?:|data:)", s):
            continue
        if not (html_dir / html.unescape(s)).exists():
            warns.append("이미지 파일 없음: %s" % s)

    # 수치 대조
    if a.facts:
        skip_f = {1} | ({toc_page} if toc_page else set())
        if refs_pn:
            skip_f |= set(range(refs_pn, n + 1))
        facts = load_facts(a.facts)
        miss = check_facts(pages, skip_f, facts)
        print("수치 대조: facts %d개 값(%s) vs PDF 본문%s" % (
            len(facts[0]), ", ".join(Path(f).name for f in a.facts),
            " (참고문헌 p%d~ 제외)" % refs_pn if refs_pn else ""))
        if miss:
            label = {"vague": "어림 표현", "range": "범위", "single": "수치"}
            print("출처 파일에 없는 수치 %d건 (어림·범위 표현 먼저):" % len(miss))
            for typ, raw, pns, ctx, hint in miss[:40]:
                print("  - [%s] %s  p%s  …%s…%s" % (label[typ], raw, ",".join(map(str, pns)), ctx,
                                                  ("  (" + hint + ")") if hint else ""))
            if len(miss) > 40:
                print("  … 외 %d건" % (len(miss) - 40))
            warns.append("출처 파일에 없는 수치 %d건 (위 '수치 대조' 목록) — facts 에 근거를 넣거나 본문에서 지우거나 "
                         "'추정'임을 밝힐 것" % len(miss))
        else:
            print("출처 파일에 없는 수치: 없음")

    # 미리보기
    if a.preview:
        runs = count_preview(out)
        want = [int(x) for x in re.split(r"[,\s]+", a.preview.strip()) if x]
        if len(want) > MAX_PREVIEW:
            print("미리보기는 최대 %d쪽 — 앞 %d쪽만 만듦" % (MAX_PREVIEW, MAX_PREVIEW))
            want = want[:MAX_PREVIEW]
        if runs > PREVIEW_RUNS_OK:
            warns.append("이 PDF 의 미리보기 %d번째 — %d번을 넘김. 이미지를 더 보지 말고 검사 요약 경고(빈 쪽·수치 등)로 고칠 것"
                         % (runs, PREVIEW_RUNS_OK))
        tp = which("pdftoppm")
        if not tp:
            print("미리보기 생략: pdftoppm 없음")
        else:
            pdir = out.parent / (out.stem + "_preview")
            pdir.mkdir(exist_ok=True)
            for p in want:
                if not 1 <= p <= n:
                    print("미리보기 p%d: 범위 밖" % p)
                    continue
                prefix = pdir / ("p%d" % p)
                subprocess.run([tp, "-r", str(a.dpi), "-png", "-singlefile", "-f", str(p), "-l", str(p),
                                str(out), str(prefix)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("미리보기: %s.png (이 PDF 미리보기 %d번째)" % (prefix, runs))

    if warns:
        print("경고 %d건:" % len(warns))
        for w in warns:
            print("  - " + w)
        print("판정: 경고 확인 필요")
    else:
        print("판정: OK (경고 없음)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
