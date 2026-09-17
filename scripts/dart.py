"""DART 증권신고서(지분증권) 수집 · 파싱 모듈

검증 결과 (2026-09-17, 최근 3개월 증권신고서 184건 → 실제 공모주 18건)
  청약일 / 납입일 / 공모가밴드 / 인수인 / 증권사별 청약한도  모두 18/18 추출

주의해서 만든 부분
  · 상장사(stock_code 보유)의 증권신고서는 유상증자이므로 제외한다.
    본문 "구주주" 빈도만으로는 [발행조건확정] 같은 짧은 문서를 걸러내지 못한다.
  · 날짜 표기가 "2026년 9월 17일", "2026.09. 17 ~2026.09. 18",
    "2026.09.16(수)~09.17(목)" 등 제각각이다. 뒤 날짜는 연도가 빠지기도 한다.
  · 표의 머리글과 값이 별도 <TABLE>로 쪼개져 나오는 경우가 많다.

추출 실패한 필드는 None 으로 두고, 화면에서 "확인 불가" 로 표시한다.
틀린 값을 내보내는 것보다 비워두는 편이 낫다.
"""
import io
import os
import re
import time
import zipfile
import warnings
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

API_KEY = os.environ.get("DART_API_KEY", "")
LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DOC_URL = "https://opendart.fss.or.kr/api/document.xml"
VIEWER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"
CACHE_DIR = os.environ.get("DART_CACHE", "")


# ---------------------------------------------------------------- 유틸
def _txt(node):
    return re.sub(r"\s+", " ", node.get_text(" ")).strip()


def _norm(s):
    return re.sub(r"\s+", "", s or "")


def _num(s):
    digits = re.sub(r"[^\d]", "", s or "")
    return int(digits) if digits else None


_DATE_RE = re.compile(
    r"(?:(\d{4})\s*[년.\-/]\s*)?(\d{1,2})\s*[월.\-/]\s*(\d{1,2})\s*일?"
)


def _kdates(s, year=None):
    """공시에 나오는 날짜 표기를 모두 받아낸다.

    2026년 09월 17일 / 2026.09. 17 / 2026-09-17 / 2026.09.16(수)~09.17(목)
    뒤쪽 날짜에 연도가 빠진 경우 앞 날짜의 연도를 물려받는다.
    """
    out = []
    for ys, ms, ds in _DATE_RE.findall(s or ""):
        if ys:
            year = ys
        if not year:
            continue
        m, d = int(ms), int(ds)
        if not (1 <= m <= 12 and 1 <= d <= 31):
            continue
        out.append("%s-%02d-%02d" % (year, m, d))
    return out


def _clean_broker(name):
    """'대신증권㈜', '대신증권 주식회사' -> '대신증권'"""
    n = re.sub(r"\s+", "", name or "")
    n = n.replace("주식회사", "").replace("㈜", "").replace("(주)", "")
    n = re.sub(r"^(주)", "", n)
    return n.strip()


class NoDocument(Exception):
    """DART가 원본 파일을 제공하지 않는 공시 (정정 요구 등). 건너뛰면 된다."""


# ---------------------------------------------------------------- 수집
def fetch_list(days=90):
    """최근 days일치 증권신고서(지분증권) 목록. corp_code 없이는 3개월이 한도."""
    end = date.today()
    begin = end - timedelta(days=min(days, 88))
    items, page = [], 1
    while True:
        r = requests.get(
            LIST_URL,
            params={
                "crtfc_key": API_KEY,
                "bgn_de": begin.strftime("%Y%m%d"),
                "end_de": end.strftime("%Y%m%d"),
                "pblntf_detail_ty": "C001",
                "page_no": str(page),
                "page_count": "100",
            },
            timeout=30,
        )
        d = r.json()
        if d.get("status") != "000":
            if page == 1:
                raise RuntimeError(f"DART list 오류: {d.get('status')} {d.get('message')}")
            break
        items += d.get("list", [])
        if page >= int(d.get("total_page", 1)):
            break
        page += 1
        time.sleep(0.2)
    return [i for i in items if "증권신고서" in i["report_nm"]]


def fetch_doc(rcept_no):
    if CACHE_DIR:
        os.makedirs(CACHE_DIR, exist_ok=True)
        p = os.path.join(CACHE_DIR, rcept_no + ".xml")
        if os.path.exists(p):
            return open(p, encoding="utf-8", errors="replace").read()
    last = None
    for attempt in range(3):
        r = requests.get(
            DOC_URL, params={"crtfc_key": API_KEY, "rcept_no": rcept_no}, timeout=120
        )
        if r.content[:5] == b"<?xml":   # DART가 원본파일을 제공하지 않는 공시
            raise NoDocument(rcept_no)
        try:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            break
        except zipfile.BadZipFile as e:      # 동시 요청이 몰리면 에러 XML이 온다
            last = e
            time.sleep(1.5 * (attempt + 1))
    else:
        raise RuntimeError(f"문서 내려받기 실패({rcept_no}): {last}")
    s = z.read(z.namelist()[0]).decode("utf-8", errors="replace")
    if CACHE_DIR:
        open(p, "w", encoding="utf-8").write(s)
    time.sleep(0.05)
    return s


# ---------------------------------------------------------------- 파싱
def _rows(tb):
    out = []
    for tr in tb.find_all("tr"):
        cells = [_txt(td) for td in tr.find_all(["td", "th"])]
        if cells:
            out.append(cells)
    return out


def _allrows(tables, i):
    """DART는 머리글과 값이 별도 <TABLE>로 쪼개지는 경우가 많다. 뒤 2개까지 붙여서 본다."""
    r = _rows(tables[i])
    j = i + 1
    while len(r) < 2 and j < len(tables) and j < i + 3:
        r += _rows(tables[j])
        j += 1
    return r


def parse(rcept_no, corp_name, corp_code, rcept_dt, report_nm, stock_code=""):
    s = fetch_doc(rcept_no)
    soup = BeautifulSoup(s, "lxml")
    tbs = soup.find_all("table")
    plain = re.sub(r"<[^>]+>", " ", s)

    d = {
        "rcept_no": rcept_no,
        "corp_code": corp_code,
        "corp_name": corp_name,
        "rcept_dt": rcept_dt,
        "report_nm": report_nm,
        "stock_code": (stock_code or "").strip(),
        "dart_url": VIEWER.format(rcept_no),
        "price_band": None,
        "final_price": None,
        "shares": None,
        "par_value": None,
        "method": None,
        "sub_start": None,
        "sub_end": None,
        "pay_date": None,
        "underwriters": [],
        "retail": [],
        "demand_rate": None,
    }

    # 종류 판별 -------------------------------------------------
    d["is_spac"] = "기업인수목적" in corp_name
    # 상장사(종목코드 보유)가 내는 증권신고서는 유상증자다. 공모주는 아직 미상장이라 종목코드가 없다.
    d["is_rights"] = bool(d["stock_code"]) or plain.count("구주주") > 20
    if "코스닥시장" in plain and plain.count("코스닥시장") > plain.count("유가증권시장"):
        d["market"] = "코스닥"
    elif "유가증권시장" in plain:
        d["market"] = "코스피"
    else:
        d["market"] = None

    # 1) 공모 개요 ----------------------------------------------
    for i in range(len(tbs)):
        r = _allrows(tbs, i)
        if not r:
            continue
        h = _norm(" ".join(r[0]))
        if "증권의종류" in h and "모집(매출)방법" in h and len(r) > 1:
            m = dict(zip([_norm(x) for x in r[0]], r[1]))
            d["shares"] = _num(m.get("증권수량"))
            d["par_value"] = _num(m.get("액면가액"))
            d["method"] = m.get("모집(매출)방법") or None
            break

    mb = re.search(r"희망공모가(?:액|밴드)?[^\d]{0,20}([\d,]+)\s*원?\s*[~∼\-]\s*([\d,]+)\s*원", plain)
    if mb:
        d["price_band"] = [_num(mb.group(1)), _num(mb.group(2))]
    mf = re.search(r"확정공모가(?:액)?(?:인|은|:|\s)[^\d]{0,15}([\d,]+)\s*원", plain)
    if mf:
        d["final_price"] = _num(mf.group(1))

    # 2) 청약 일정 ----------------------------------------------
    HEAD = ("청약기일", "납입기일", "청약공고일", "배정공고일", "배정기준일")
    for i in range(len(tbs)):
        r = _allrows(tbs, i)
        if not r:
            continue
        head = [_norm(c) for c in r[0]]
        if "청약기일" not in head or "납입기일" not in head:
            continue
        # 머리글과 값의 칸 수가 맞으면 그대로 짝지어 읽는다 (가장 정확)
        pair = None
        for cand in r[1:]:
            if len(cand) == len(r[0]) and any(_kdates(c) for c in cand):
                pair = dict(zip(head, cand))
                break
        if pair is None:
            # 칸 수가 어긋나면: 머리글 뒤에 오는 날짜 칸들을 순서대로 본다
            cells = [c for row in r for c in row]
            try:
                k = max(j for j, c in enumerate(cells) if _norm(c) in HEAD)
            except ValueError:
                continue
            vals = [c for c in cells[k + 1:] if len(c) < 60 and _kdates(c)]
            if not vals:
                continue
            pair = {"청약기일": vals[0],
                    "납입기일": vals[1] if len(vals) > 1 else ""}
        ds = _kdates(pair.get("청약기일", ""))
        if not ds:
            continue
        d["sub_start"], d["sub_end"] = ds[0], ds[-1]
        pd_ = _kdates(pair.get("납입기일", ""), year=ds[0][:4])
        if pd_:
            d["pay_date"] = pd_[0]
        break

    # 3) 인수인 (증권사별 인수물량) -------------------------------
    for i in range(len(tbs)):
        r = _allrows(tbs, i)
        if not r:
            continue
        h = _norm(" ".join(r[0]))
        if ("인수인" in h or "인수(주선)인" in h) and "인수수량" in h:
            for row in r[1:]:
                row = [c for c in row if c]
                name = next((c for c in row if "증권" in c and len(c) < 20), None)
                qty = next((_num(c) for c in row if re.fullmatch(r"[\d,]{4,}", c)), None)
                role = row[0] if row and "증권" not in row[0] else "대표주관회사"
                if name:
                    d["underwriters"].append(
                        {"role": role, "name": _clean_broker(name), "qty": qty}
                    )
            if d["underwriters"]:
                break

    # 4) 증권사별 일반청약자 배정물량 / 최고청약한도 / 증거금률 ----
    for i in range(len(tbs)):
        r = _allrows(tbs, i)
        if not r:
            continue
        h = _norm(" ".join(r[0]))
        if "일반청약자배정물량" in h and "청약한도" in h:
            block = list(r[1:])
            # 표가 쪼개져 다음 표에 나머지 증권사 행이 이어지는 경우 보강
            for k in range(i + 1, min(i + 5, len(tbs))):
                for row in _rows(tbs[k]):
                    if row and "증권" in row[0] and len(row) >= 3:
                        block.append(row)
            seen = set()
            for row in block:
                if len(row) >= 3 and "증권" in row[0]:
                    nm = _clean_broker(row[0])
                    if nm in seen:
                        continue
                    seen.add(nm)
                    d["retail"].append({
                        "name": nm,
                        "alloc": row[1] or None,
                        "limit": row[2] or None,
                        "margin": row[3] if len(row) > 3 else None,
                    })
            if d["retail"]:
                break

    # 5) 수요예측 경쟁률 -----------------------------------------
    mc = re.search(r"수요예측\s*경쟁률[^\d]{0,20}([\d,\.]+)\s*[:대]", plain)
    if mc:
        d["demand_rate"] = mc.group(1)

    # 인수인에만 있고 청약한도 표에 없는 증권사도 목록에 채워둔다
    known = {x["name"] for x in d["retail"]}
    for u in d["underwriters"]:
        if u["name"] not in known:
            d["retail"].append({"name": u["name"], "alloc": None,
                                "limit": None, "margin": None})

    d["missing"] = [k for k in ("price_band", "sub_start", "sub_end", "pay_date")
                    if not d.get(k)]
    if not d["underwriters"]:
        d["missing"].append("underwriters")
    if not any(x["limit"] for x in d["retail"]):
        d["missing"].append("retail_limit")
    return d
