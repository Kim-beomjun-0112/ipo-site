"""data/*.json → site/ 정적 HTML 생성.

빌드 도구 없이 파이썬 표준 라이브러리만 쓴다. Netlify는 site/ 폴더를
그대로 배포하므로 빌드 시간이 거의 들지 않는다.

실행: python scripts/build.py
"""
import calendar as calmod
import json
import os
import re
import shutil
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import theme  # noqa: E402
from theme import NA, SITE_NAME, SITE_URL, ad, layout  # noqa: E402
from content import FAQ, GLOSSARY, GUIDES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "site")
TODAY = date.today()
WEEK = ["월", "화", "수", "목", "금", "토", "일"]

# 증권사 표기 통일 --------------------------------------------------
ALIAS = {
    "유진증권": "유진투자증권", "케이비증권": "KB증권", "케이비": "KB증권",
    "아이비케이투자증권": "IBK투자증권", "아이비케이": "IBK투자증권",
    "엔에이치투자증권": "NH투자증권", "에스케이증권": "SK증권",
    "하이투자증권": "아이엠증권", "아이엠투자증권": "아이엠증권",
    "디비금융투자": "DB증권", "디비증권": "DB증권",
    "엘에스증권": "LS증권", "이베스트투자증권": "LS증권",
    "한국투자증권주식회사": "한국투자증권", "대신증권주식회사": "대신증권",
    "다올투자증권주식회사": "다올투자증권",
}
PALETTE = ["#2b5ce6", "#0a9d5a", "#d9600b", "#7c4ded", "#d1365a",
           "#0891a6", "#b45309", "#4f46e5", "#be185d", "#047857"]


def canon(name):
    n = re.sub(r"\s+", "", name or "")
    n = n.replace("주식회사", "").replace("㈜", "").replace("(주)", "").strip()
    return ALIAS.get(n, n)


def avatar(name):
    c = PALETTE[sum(ord(ch) for ch in name) % len(PALETTE)]
    ch = name[0] if name else "?"
    return f'<span class=av style="background:{c}">{esc(ch)}</span>'


# 공통 유틸 ----------------------------------------------------------
def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def slug(s):
    return re.sub(r"[^0-9A-Za-z가-힣]+", "-", str(s)).strip("-")


def d(s):
    return date.fromisoformat(s) if s else None


def md(s):
    return s[5:].replace("-", ".") if s else ""


def na(v, fmt=None):
    if v in (None, "", []):
        return f'<span class=na>{NA}</span>'
    return esc(fmt % v if fmt else v)


def status(r):
    a, b = d(r.get("sub_start")), d(r.get("sub_end"))
    if not a:
        return ("일정 미정", "later", 99)
    b = b or a
    if TODAY < a:
        n = (a - TODAY).days
        return (f"D-{n}", "soon" if n <= 7 else "later", n)
    if a <= TODAY <= b:
        return ("청약 중", "live", 0)
    return ("마감", "done", -1)


def price(r, short=False):
    fp, band = r.get("final_price"), r.get("price_band")
    if fp:
        tag = ""
        if band and band[0] and fp < band[0]:
            tag = ' <span class=b-under>밴드 하회</span>'
        elif band and band[1] and fp >= band[1]:
            tag = ' <span class=b-fix>밴드 상단</span>'
        else:
            tag = ' <span class=b-fix>확정</span>'
        return f"{fp:,}원{'' if short else tag}"
    if band and band[0] and band[1]:
        return f"{band[0]:,}~{band[1]:,}원"
    return f'<span class=na>{NA}</span>'


def period(r):
    a, b = r.get("sub_start"), r.get("sub_end")
    if not a:
        return f'<span class=na>{NA}</span>'
    return f"{md(a)}~{md(b)}" if b and b != a else md(a)


def ipos(items):
    return [r for r in items if not r.get("is_spac")]


# 컴포넌트 ----------------------------------------------------------
def card(r, up=""):
    label, cls, _ = status(r)
    dot = "<i class=dot></i>" if cls == "live" else ""
    bs = [canon(u["name"]) for u in r.get("underwriters", [])]
    chips = "".join(f'<span class=chip>{avatar(b)}{esc(b)}</span>' for b in dict.fromkeys(bs))
    if not chips:
        chips = f'<span class=na>주관사 {NA}</span>'
    mkt = f'<span class=mkt>{esc(r["market"])}</span>' if r.get("market") else ""
    spac = '<span class=mkt>스팩</span>' if r.get("is_spac") else ""
    return f"""<a class="ipo s-{cls}" href="{up}ipo/{r['corp_code']}.html">
<div class=ipo-top>
 <div><div class=ipo-nm>{esc(r['corp_name'])}{mkt}{spac}</div>
 <div class=ipo-sub>청약 {period(r)} · 환불 {na(md(r.get('pay_date')))}</div></div>
 <span class="bdg b-{cls}">{dot}{label}</span>
</div>
<dl class=ipo-grid>
 <div><dt>공모가</dt><dd>{price(r)}</dd></div>
 <div><dt>공모주식수</dt><dd>{qty_cell(r.get('shares'))}</dd></div>
 <div><dt>주관사</dt><dd>{len(set(bs))}곳</dd></div>
</dl>
<div class=brokers>{chips}</div></a>"""


def month_cal(y, m, evs):
    cells, first = [], date(y, m, 1)
    lead = first.weekday()
    prev_last = (first - timedelta(days=1)).day
    for i in range(lead):
        cells.append(('<div class="cal-d out">%d</div>' % (prev_last - lead + i + 1)))
    days = calmod.monthrange(y, m)[1]
    for day in range(1, days + 1):
        cur = date(y, m, day)
        e = evs.get(cur.isoformat(), set())
        cls = "cal-d"
        if e:
            cls += " has"
        if cur == TODAY:
            cls += " today"
        dots = "".join(f'<i class="ev ev-{k}"></i>' for k in sorted(e))
        cells.append(f'<div class="{cls}">{day}<span class=cal-ev>{dots}</span></div>')
    while len(cells) % 7:
        cells.append('<div class="cal-d out"></div>')
    hdr = "".join(f'<div class="cal-w{" sun" if w == "일" else ""}">{w}</div>' for w in WEEK)
    return (f'<div class=cal><div class=cal-h>{y}년 {m}월</div>'
            f'<div class=cal-g>{hdr}{"".join(cells)}</div></div>')


def calendar_block(items):
    evs = {}
    for r in ipos(items):
        a, b = d(r.get("sub_start")), d(r.get("sub_end"))
        if a:
            cur = a
            while cur <= (b or a):
                evs.setdefault(cur.isoformat(), set()).add("sub")
                cur += timedelta(days=1)
        p = d(r.get("pay_date"))
        if p:
            evs.setdefault(p.isoformat(), set()).add("pay")
    y, m = TODAY.year, TODAY.month
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return (month_cal(y, m, evs) + month_cal(ny, nm, evs) +
            '<div class=cal-lg>'
            '<span><i style="background:var(--live)"></i>청약일</span>'
            '<span><i style="background:var(--pri)"></i>환불·납입일</span>'
            '<span><i style="background:var(--line);outline:2px solid var(--pri);'
            'outline-offset:-1px"></i>오늘</span></div>')


def timeline(r):
    steps = [("증권신고서", r.get("rcept_dt") and
              f"{r['rcept_dt'][4:6]}.{r['rcept_dt'][6:]}"),
             ("청약 시작", md(r.get("sub_start"))),
             ("청약 마감", md(r.get("sub_end"))),
             ("환불·납입", md(r.get("pay_date")))]
    dates = [None, d(r.get("sub_start")), d(r.get("sub_end")), d(r.get("pay_date"))]
    out = []
    for i, (t, v) in enumerate(steps):
        dt = dates[i]
        cls = "ok" if (i == 0 or (dt and dt < TODAY)) else ""
        if dt and dt == TODAY:
            cls = "now"
        out.append(f'<div class="tl-s {cls}"><b>{t}</b>'
                   f'<span>{v or NA}</span></div>')
    return f'<div class=tl>{"".join(out)}</div>'


def price_bar(r):
    band, fp = r.get("price_band"), r.get("final_price")
    if not (band and band[0] and band[1]):
        return ""
    lo, hi = band
    mark = ""
    if fp:
        pct = max(0, min(100, (fp - lo) / max(1, hi - lo) * 100))
        mark = f'<span class=pbar-m style="left:calc({pct:.1f}% - 1px)"></span>'
        note = ("희망 범위 아래에서 확정" if fp < lo else
                "희망 범위 위쪽에서 확정" if fp >= hi else "희망 범위 안에서 확정")
    else:
        note = "수요예측 후 확정 예정"
    return (f'<div class=pbar><div class=pbar-t><span>{lo:,}원</span>'
            f'<span style="color:var(--tx2)">{note}</span><span>{hi:,}원</span></div>'
            f'<div class=pbar-r><span class=pbar-f></span>{mark}</div></div>')


def retail_table(r):
    rows = r.get("retail") or []
    if not rows:
        return f'<div class=note>증권사별 청약 조건을 공시에서 읽어내지 못했습니다. DART 원문을 확인하세요.</div>'
    body = "".join(
        f'<tr><td><span style="display:inline-flex;align-items:center;gap:7px">'
        f'{avatar(canon(x["name"]))}<b>{esc(canon(x["name"]))}</b></span></td>'
        f'<td>{na(x.get("alloc"))}</td><td>{na(x.get("limit"))}</td>'
        f'<td>{na(x.get("margin"))}</td></tr>' for x in rows)
    return ('<div class=scroll><table><thead><tr><th>증권사</th><th>일반청약자 배정물량</th>'
            f'<th>최고 청약한도</th><th>증거금률</th></tr></thead><tbody>{body}</tbody></table></div>')


def qty_cell(q):
    return f"{q:,}주" if q else f'<span class=na>{NA}</span>'


def uw_table(r):
    rows = r.get("underwriters") or []
    if not rows:
        return f'<div class=note>인수인 정보를 읽어내지 못했습니다.</div>'
    body = "".join(
        f'<tr><td>{esc(x.get("role") or "-")}</td>'
        f'<td><span style="display:inline-flex;align-items:center;gap:7px">'
        f'{avatar(canon(x["name"]))}<b>{esc(canon(x["name"]))}</b></span></td>'
        f'<td>{qty_cell(x.get("qty"))}</td></tr>'
        for x in rows)
    return ('<div class=scroll><table><thead><tr><th>구분</th><th>증권사</th>'
            f'<th>인수물량</th></tr></thead><tbody>{body}</tbody></table></div>')


def faq_block(pairs):
    return "".join(f'<details class=faq><summary>{esc(q)}</summary>'
                   f'<div class=faq-b>{a}</div></details>' for q, a in pairs)


def write(path, html):
    p = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(html)


# 페이지 ------------------------------------------------------------
def build_index(items):
    groups = {"live": [], "soon": [], "later": [], "done": []}
    for r in ipos(items):
        groups[status(r)[1]].append(r)
    spacs = [r for r in items if r.get("is_spac")]
    for k in groups:
        groups[k].sort(key=lambda r: r.get("sub_start") or "9999")

    def sec(title, rows, empty, extra=""):
        if not rows:
            return f'<h2>{title}</h2><div class=card><span class=na>{empty}</span></div>'
        return (f'<h2>{title}<span class=cnt>{len(rows)}</span></h2>{extra}'
                + "".join(card(r) for r in rows))

    week = [r for r in ipos(items) if r.get("sub_start")
            and TODAY <= d(r["sub_start"]) <= TODAY + timedelta(days=7)]
    body = f"""<section class=hero>
<h1>공모주 청약 일정을<br>한눈에</h1>
<p>금융감독원 전자공시(DART)의 증권신고서를 매일 자동으로 읽어
청약일·공모가·증권사별 배정물량과 청약한도까지 원문 그대로 정리합니다.</p>
<div class=stats>
 <div class=stat><b>{len(groups['live'])}</b><span>청약 진행 중</span></div>
 <div class=stat><b>{len(week)}</b><span>이번 주 시작</span></div>
 <div class=stat><b>{len(groups['later']) + len(groups['soon'])}</b><span>청약 예정</span></div>
 <div class=stat><b>{len(ipos(items))}</b><span>최근 3개월</span></div>
</div></section>
{ad('display')}
{sec('🔥 지금 청약 중', groups['live'], '지금 청약을 받고 있는 종목이 없습니다. 아래 예정 목록을 확인해 보세요.')}
{sec('⏰ 일주일 안에 시작', groups['soon'], '일주일 안에 시작하는 종목이 없습니다.')}
{ad('infeed')}
{sec('📅 청약 예정', groups['later'], '예정된 종목이 없습니다.')}
<h2>이번 달과 다음 달</h2>
{calendar_block(items)}
{ad('display')}
{sec('✅ 최근 마감', groups['done'][::-1][:10], '최근 마감된 종목이 없습니다.')}
{sec('🧪 스팩(SPAC)', spacs, '진행 중인 스팩 공모가 없습니다.')}
<h2>자주 묻는 질문</h2>
{faq_block(FAQ)}
<h2>처음이라면</h2>
<div class=tiles>{"".join(f'<a class=tile href="guide/{s}.html"><b>{esc(t)}</b><span>{esc(dsc)}</span></a>' for s, t, dsc, _ in GUIDES[:3])}</div>
{ad('multiplex')}"""
    write("index.html", layout(
        f"{SITE_NAME} — 공모주 청약 일정·증권사별 배정물량",
        "오늘 청약 가능한 공모주와 앞으로의 일정, 공모가, 주관사, 증권사별 배정물량과 "
        "최고 청약한도를 DART 공시 기준으로 매일 자동 정리합니다.",
        body, "index.html", "", UPDATED))


def build_detail(r):
    label, cls, _ = status(r)
    warn = ""
    if r.get("missing"):
        warn = ('<div class=note>공시에서 자동으로 읽어내지 못한 항목이 있어 '
                f'“{NA}”로 표시됩니다. 정확한 값은 아래 DART 원문을 확인하세요.</div>')
    hist = "".join(
        f'<tr><td>{esc(h["rcept_dt"])}</td><td>{esc(h["report_nm"])}</td>'
        f'<td><a href="{h["dart_url"]}" rel=nofollow style="color:var(--pri);font-weight:600">'
        f'원문 ↗</a></td></tr>' for h in reversed(r.get("history", [])))
    nm = esc(r["corp_name"])
    detail_faq = [
        (f"{r['corp_name']} 청약은 어느 증권사에서 하나요?",
         "<p>아래 <b>증권사별 청약 조건</b> 표에 있는 증권사에 계좌가 있어야 청약할 수 "
         "있습니다. 인수단이 여러 곳이어도 중복 청약은 금지되므로 한 곳만 고르셔야 합니다.</p>"),
        ("증거금은 얼마나 필요한가요?",
         f"<p>증거금률은 아래 표에 증권사별로 나와 있습니다. 보통 50%이며, "
         f"<b>공모가 × 청약 수량 × 증거금률</b>로 계산합니다. 배정받지 못한 만큼은 "
         f"{na(md(r.get('pay_date')))}에 환불됩니다.</p>"),
        ("일정이 바뀔 수도 있나요?",
         "<p>정정 증권신고서가 제출되면 일정과 공모가가 바뀔 수 있습니다. 아래 "
         "<b>공시 이력</b>에서 가장 최근 문서를 확인하시고, 청약 직전에는 증권사 공지도 "
         "한 번 더 보시길 권합니다.</p>"),
    ]
    body = f"""<h1 style="margin-top:26px">{nm} 공모주 청약</h1>
<p class=lead>{esc(r.get('market') or '')} 상장 예정 · 최근 공시 {esc(r['rcept_dt'])}
· <span class="bdg b-{cls}">{label}</span></p>
{warn}
{timeline(r)}
<div class=kv style="margin-top:14px">
 <div><dt>청약일</dt><dd>{period(r)}</dd></div>
 <div><dt>공모가</dt><dd>{price(r)}</dd></div>
 <div><dt>환불·납입일</dt><dd>{na(md(r.get('pay_date')))}</dd></div>
 <div><dt>총 공모주식수</dt><dd>{f"{r['shares']:,}주" if r.get('shares') else f'<span class=na>{NA}</span>'}</dd></div>
 <div><dt>액면가</dt><dd>{f"{r['par_value']:,}원" if r.get('par_value') else f'<span class=na>{NA}</span>'}</dd></div>
 <div><dt>모집 방법</dt><dd>{na(r.get('method'))}</dd></div>
</div>
{price_bar(r)}
{ad('display')}
<h2>증권사별 청약 조건</h2>
<p class=lead>내 계좌가 있는 증권사가 이 목록에 있어야 청약할 수 있습니다.
수치는 공시 원문을 그대로 옮긴 것입니다.</p>
{retail_table(r)}
{ad('infeed')}
<h2>인수인 (주관사·인수단)</h2>
{uw_table(r)}
<h2>청약 전 확인할 것</h2>
<div class=card><div class=art style="font-size:14.5px">
<ul>
<li>위 증권사 중 <b>한 곳</b>에만 청약할 수 있습니다. 중복 청약은 금지입니다.</li>
<li>증권사에 따라 <b>청약 전 계좌 보유 기간</b>을 요구할 수 있습니다. 미리 확인하세요.</li>
<li>균등배정은 최소 수량만 넣어도 됩니다. 많이 넣어도 균등 몫은 늘지 않습니다.</li>
<li>증거금은 {na(md(r.get('pay_date')))}에 환불됩니다. 다른 종목 일정과 겹치는지 확인하세요.</li>
<li>확정 공모가와 일정은 정정신고서로 바뀔 수 있습니다.</li>
</ul></div></div>
<h2>자주 묻는 질문</h2>
{faq_block(detail_faq)}
<h2>공시 이력</h2>
<div class=scroll><table><thead><tr><th>접수일</th><th>보고서</th><th>원문</th></tr></thead><tbody>
<tr><td>{esc(r['rcept_dt'])}</td><td><b>{esc(r['report_nm'])}</b> (최신)</td>
<td><a href="{r['dart_url']}" rel=nofollow style="color:var(--pri);font-weight:600">원문 ↗</a></td></tr>
{hist}</tbody></table></div>
{ad('multiplex')}"""
    desc = (f"{r['corp_name']} 공모주 청약 {period(r)}, 공모가 "
            f"{re.sub('<[^>]+>', '', price(r, True))}. 증권사별 배정물량과 최고 청약한도, "
            f"증거금률을 DART 공시 기준으로 정리했습니다.")
    write(f"ipo/{r['corp_code']}.html", layout(
        f"{r['corp_name']} 공모주 청약일정·공모가·증권사 | {SITE_NAME}",
        re.sub("<[^>]+>", "", desc), body, f"ipo/{r['corp_code']}.html", "", UPDATED))


def build_brokers(items, binfo):
    idx = {}
    for r in items:
        seen = set()
        for x in r.get("retail", []) + [{"name": u["name"]} for u in r.get("underwriters", [])]:
            n = canon(x["name"])
            if n in seen:
                continue
            seen.add(n)
            row = next((y for y in r.get("retail", []) if canon(y["name"]) == n), {})
            idx.setdefault(n, []).append((r, row))
    names = sorted(idx, key=lambda n: (-len(idx[n]), n))
    rows = "".join(
        f'<tr><td><a href="broker/{slug(n)}.html" style="display:inline-flex;align-items:center;'
        f'gap:8px;color:var(--pri);font-weight:700">{avatar(n)}{esc(n)}</a></td>'
        f'<td>{esc((binfo.get(n) or {}).get("app") or NA)}</td>'
        f'<td><b>{len([1 for r, _ in idx[n] if status(r)[1] != "done"])}</b>건</td>'
        f'<td>{len(idx[n])}건</td></tr>' for n in names)
    body = f"""<h1 style="margin-top:26px">증권사별 공모주 청약</h1>
<p class=lead>최근 3개월간 공모주 인수에 참여한 증권사 {len(names)}곳입니다.
위쪽에 있을수록 청약 기회가 많다는 뜻이라, 계좌를 어디부터 열지 정할 때 참고하실 수 있습니다.</p>
{ad('display')}
<div class=scroll><table><thead><tr><th>증권사</th><th>MTS 앱</th>
<th>진행·예정</th><th>최근 3개월</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class=note>청약수수료와 우대조건은 증권사 정책에 따라 자주 바뀌므로 표시하지 않습니다.
청약 전 해당 증권사 공지를 확인하세요.</div>
<h2>계좌를 몇 개나 만들어야 할까</h2>
<div class=card><div class=art style="font-size:14.5px">
<p>균등배정은 청약자 수로 나누기 때문에 계좌가 많을수록 유리해 보이지만, 실제로는
<b>그 종목을 인수하는 증권사</b>에만 청약할 수 있습니다. 주관사가 한 곳뿐인 코스닥 중소형
공모주가 많아서, 계좌 개수보다 <b>어느 증권사에 계좌가 있는지</b>가 더 중요합니다.</p>
<p>위 표를 참여 건수가 많은 순서대로 보시고, 상위 증권사부터 계좌를 여는 편이 효율적입니다.</p>
</div></div>
{ad('multiplex')}"""
    write("brokers.html", layout(
        f"증권사별 공모주 청약 가능 종목 | {SITE_NAME}",
        "증권사별로 청약할 수 있는 공모주 종목과 배정물량, 최고 청약한도를 정리했습니다. "
        "어느 증권사에 계좌를 열지 정할 때 참고하세요.",
        body, "brokers.html", "brokers.html", UPDATED))

    for n in names:
        lst = sorted(idx[n], key=lambda t: t[0].get("sub_start") or "9999")
        cards = ""
        for r, x in lst:
            label, cls, _ = status(r)
            cards += f"""<div class="ipo s-{cls}" style="cursor:default">
<div class=ipo-top><div>
 <div class=ipo-nm><a href="../ipo/{r['corp_code']}.html">{esc(r['corp_name'])}</a></div>
 <div class=ipo-sub>청약 {period(r)} · 공모가 {price(r)}</div></div>
 <span class="bdg b-{cls}">{label}</span></div>
<dl class=ipo-grid>
 <div><dt>배정물량</dt><dd style="font-size:12.5px">{na(x.get('alloc'))}</dd></div>
 <div><dt>최고 청약한도</dt><dd style="font-size:12.5px">{na(x.get('limit'))}</dd></div>
 <div><dt>증거금률</dt><dd style="font-size:12.5px">{na(x.get('margin'))}</dd></div>
</dl></div>"""
        info = binfo.get(n) or {}
        live = len([1 for r, _ in lst if status(r)[1] != "done"])
        body = f"""<h1 style="margin-top:26px;display:flex;align-items:center;gap:10px">
{avatar(n)}{esc(n)} 공모주 청약</h1>
<p class=lead>MTS 앱 {na(info.get('app'))} · 최근 3개월 {len(lst)}건 참여 ·
현재 진행·예정 {live}건</p>
{ad('display')}
{cards or '<div class=card><span class=na>표시할 종목이 없습니다.</span></div>'}
{ad('multiplex')}"""
        write(f"broker/{slug(n)}.html", layout(
            f"{n} 공모주 청약 가능 종목·청약한도 | {SITE_NAME}",
            f"{n}에서 청약할 수 있는 공모주 종목과 일반청약자 배정물량, 최고 청약한도, "
            f"증거금률을 DART 공시 기준으로 정리했습니다.",
            body, f"broker/{slug(n)}.html", "brokers.html", UPDATED))


def build_results(items):
    done = [r for r in ipos(items) if status(r)[1] == "done"]
    done.sort(key=lambda r: r.get("sub_start") or "", reverse=True)
    rows = "".join(
        f'<tr><td><a href="ipo/{r["corp_code"]}.html" style="color:var(--pri);font-weight:700">'
        f'{esc(r["corp_name"])}</a></td><td>{period(r)}</td><td>{price(r)}</td>'
        f'<td>{esc(", ".join(dict.fromkeys(canon(u["name"]) for u in r.get("underwriters", []))) or "-")}</td>'
        f'<td class=na>{NA}</td></tr>' for r in done[:40])
    body = f"""<h1 style="margin-top:26px">청약 마감 종목</h1>
<p class=lead>최근 청약이 끝난 종목입니다. 확정 공모가가 희망 범위의 어디에서 정해졌는지
보면 기관들의 평가를 가늠할 수 있습니다.</p>
{ad('display')}
<div class=scroll><table><thead><tr><th>종목</th><th>청약일</th><th>공모가</th>
<th>주관사</th><th>시초가</th></tr></thead><tbody>{rows or '<tr><td colspan=5>아직 없습니다.</td></tr>'}</tbody></table></div>
<div class=note info>상장일 시초가와 수익률 연동은 준비 중입니다. 증권신고서에는 상장일이
담기지 않아, 별도 공시를 연결하는 작업이 필요합니다.</div>
<h2>확정 공모가 위치가 알려주는 것</h2>
<div class=card><div class=art style="font-size:14.5px">
<p><b>밴드 상단</b>에서 확정됐다면 기관 수요가 강했다는 뜻입니다. 반대로
<b>밴드 하회</b>는 기관들이 회사가 제시한 값어치를 인정하지 않았다는 신호라,
경쟁률 숫자보다 솔직한 지표로 보는 경우가 많습니다.</p>
<p>다만 공모가가 낮게 정해지면 그만큼 싸게 사는 것이므로, 상장 후 수익률이 오히려
좋은 사례도 있습니다. 하나의 지표로만 판단하지 마세요.</p>
</div></div>
{ad('multiplex')}"""
    write("results.html", layout(
        f"공모주 청약 마감 종목·확정 공모가 | {SITE_NAME}",
        "최근 청약이 끝난 공모주의 확정 공모가와 주관사를 정리했습니다.",
        body, "results.html", "results.html", UPDATED))


def build_guides():
    lst = "".join(
        f'<a class=tile href="{s}.html"><b>{esc(t)}</b><span>{esc(dsc)}</span></a>'
        for s, t, dsc, _ in GUIDES)
    body = f"""<h1 style="margin-top:26px">공모주 가이드</h1>
<p class=lead>청약이 처음이라면 위에서부터 차례로 읽어보세요.
용어가 막히면 <a href="../glossary.html" style="color:var(--pri);font-weight:600">용어사전</a>을
함께 보시면 됩니다.</p>
{ad('display')}
<div class=tiles>{lst}</div>
{ad('multiplex')}"""
    write("guide/index.html", layout(
        f"공모주 가이드 — 청약 방법부터 매도 시점까지 | {SITE_NAME}",
        "공모주 청약 방법, 균등배정과 비례배정의 차이, 수요예측 읽는 법, 증권사 선택 기준까지 "
        "처음 하는 사람을 위해 정리했습니다.",
        body, "guide/index.html", "guide/", UPDATED))

    for i, (s, t, dsc, html) in enumerate(GUIDES):
        others = [g for j, g in enumerate(GUIDES) if j != i][:3]
        more = "".join(f'<a class=tile href="{o[0]}.html"><b>{esc(o[1])}</b>'
                       f'<span>{esc(o[2])}</span></a>' for o in others)
        body = f"""<h1 style="margin-top:26px">{esc(t)}</h1>
<p class=lead>{esc(dsc)}</p>
{ad('display')}
<div class=art>{html}</div>
{ad('infeed')}
<h2>이어서 읽기</h2>
<div class=tiles>{more}</div>
{ad('multiplex')}"""
        write(f"guide/{s}.html", layout(
            f"{t} | {SITE_NAME}", dsc, body, f"guide/{s}.html", "guide/", UPDATED))


def build_glossary():
    items = "".join(f'<div class=gl><b>{esc(k)}</b><p>{esc(v)}</p></div>'
                    for k, v in GLOSSARY)
    half = len(GLOSSARY) // 2
    first = "".join(f'<div class=gl><b>{esc(k)}</b><p>{esc(v)}</p></div>'
                    for k, v in GLOSSARY[:half])
    second = "".join(f'<div class=gl><b>{esc(k)}</b><p>{esc(v)}</p></div>'
                     for k, v in GLOSSARY[half:])
    body = f"""<h1 style="margin-top:26px">공모주 용어사전</h1>
<p class=lead>증권신고서와 청약 화면에 나오는 말들을 짧게 정리했습니다.
{len(GLOSSARY)}개 용어.</p>
{ad('display')}
{first}
{ad('infeed')}
{second}
{ad('multiplex')}"""
    write("glossary.html", layout(
        f"공모주 용어사전 — 청약·배정·공시 용어 정리 | {SITE_NAME}",
        "공모가, 균등배정, 증거금률, 의무보유 확약 등 공모주 청약에 나오는 용어를 "
        "짧고 쉽게 정리했습니다.",
        body, "glossary.html", "glossary.html", UPDATED))


def build_meta(items):
    urls = [("", "1.0"), ("brokers.html", "0.8"), ("results.html", "0.6"),
            ("guide/", "0.7"), ("glossary.html", "0.7")]
    urls += [(f"guide/{s}.html", "0.6") for s, *_ in GUIDES]
    urls += [(f"ipo/{r['corp_code']}.html", "0.9") for r in items]
    xml = "".join(f"<url><loc>{SITE_URL}/{u}</loc>"
                  f"<lastmod>{TODAY.isoformat()}</lastmod>"
                  f"<priority>{p}</priority></url>" for u, p in urls)
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>'
          f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{xml}</urlset>')
    write("robots.txt", "User-agent: *\nAllow: /\nDisallow: /admin/\n"
                        f"Sitemap: {SITE_URL}/sitemap.xml\n")


def main():
    global UPDATED
    dd = json.load(open(os.path.join(DATA, "ipos.json"), encoding="utf-8"))
    UPDATED = dd["updated_at"]
    theme.UPDATED = UPDATED
    items = dd["items"]
    binfo = json.load(open(os.path.join(DATA, "brokers.json"),
                           encoding="utf-8"))["brokers"]
    binfo = {canon(k): v for k, v in binfo.items()}

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    build_index(items)
    for r in items:
        build_detail(r)
    build_brokers(items, binfo)
    build_results(items)
    build_guides()
    build_glossary()
    build_meta(items)

    adm = os.path.join(ROOT, "admin")
    if os.path.exists(adm):
        shutil.copytree(adm, os.path.join(OUT, "admin"))
    shutil.copy(os.path.join(DATA, "ipos.json"), os.path.join(OUT, "ipos.json"))

    n = sum(len(fs) for _, _, fs in os.walk(OUT))
    print(f"빌드 완료 — {n}개 파일 / 종목 {len(items)}건 / 가이드 {len(GUIDES)}편 "
          f"/ 용어 {len(GLOSSARY)}개")


if __name__ == "__main__":
    main()
