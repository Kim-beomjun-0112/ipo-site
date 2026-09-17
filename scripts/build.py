"""data/*.json → site/ 정적 HTML 생성.

빌드 도구 없음(파이썬 표준 + 없음). Netlify는 site/ 폴더를 그대로 배포하므로
빌드 시간이 들지 않는다.

실행: python scripts/build.py
"""
import json
import os
import re
import shutil
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "site")
SITE_URL = "https://ipo.qjawnsl112.com"
SITE_NAME = "공모주 캘린더"
ADSENSE_CLIENT = ""   # 승인 후 "ca-pub-XXXXXXXXXXXX" 넣으면 자동 삽입
NA = "확인 불가"

TODAY = date.today().isoformat()

# ------------------------------------------------------------------ 유틸
def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def slug(s):
    return re.sub(r"[^0-9A-Za-z가-힣]+", "-", str(s)).strip("-")


def won(n):
    return f"{n:,}원" if isinstance(n, int) else NA


def band(r):
    b = r.get("price_band")
    if r.get("final_price"):
        return f"{r['final_price']:,}원 <span class=tag-ok>확정</span>"
    if b and b[0] and b[1]:
        return f"{b[0]:,} ~ {b[1]:,}원"
    return f"<span class=na>{NA}</span>"


def period(r):
    a, b = r.get("sub_start"), r.get("sub_end")
    if not a:
        return f"<span class=na>{NA}</span>"
    if b and b != a:
        return f"{a[5:].replace('-', '.')} ~ {b[5:].replace('-', '.')}"
    return a[5:].replace("-", ".")


def dday(r):
    a, b = r.get("sub_start"), r.get("sub_end")
    if not a:
        return "", ""
    t = date.fromisoformat(TODAY)
    s = date.fromisoformat(a)
    e = date.fromisoformat(b or a)
    if t < s:
        n = (s - t).days
        return f"D-{n}", "soon" if n <= 7 else "later"
    if s <= t <= e:
        return "청약중", "live"
    return "마감", "done"


def val(x):
    return esc(x) if x else f'<span class="na">{NA}</span>'


# ------------------------------------------------------------------ 레이아웃
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
 --bg:#fbfbfd;--card:#fff;--tx:#16181d;--sub:#6b7280;--line:#e7e8ec;
 --pri:#1f5fd8;--pri-soft:#eaf1ff;--live:#0f9d58;--live-soft:#e6f5ed;
 --warn:#c2410c;--warn-soft:#fff1e8;--na:#9aa0aa;
}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
 --bg:#0e1015;--card:#171a21;--tx:#e8eaee;--sub:#9aa1ad;--line:#262a33;
 --pri:#79a6ff;--pri-soft:#18233a;--live:#4ade80;--live-soft:#16281f;
 --warn:#fb923c;--warn-soft:#2a1a10;--na:#6b7280;}}
:root[data-theme=dark]{
 --bg:#0e1015;--card:#171a21;--tx:#e8eaee;--sub:#9aa1ad;--line:#262a33;
 --pri:#79a6ff;--pri-soft:#18233a;--live:#4ade80;--live-soft:#16281f;
 --warn:#fb923c;--warn-soft:#2a1a10;--na:#6b7280;}
body{background:var(--bg);color:var(--tx);font-family:-apple-system,BlinkMacSystemFont,
 "Apple SD Gothic Neo","Pretendard","Malgun Gothic",sans-serif;line-height:1.6;
 -webkit-text-size-adjust:100%}
a{color:inherit;text-decoration:none}
.wrap{max-width:900px;margin:0 auto;padding:0 16px}
header{border-bottom:1px solid var(--line);background:var(--card);position:sticky;top:0;z-index:9}
.hd{display:flex;align-items:center;gap:18px;height:56px}
.logo{font-weight:800;font-size:17px;letter-spacing:-.02em}
.logo b{color:var(--pri)}
nav{display:flex;gap:14px;font-size:14px;color:var(--sub);overflow-x:auto}
nav a:hover,nav a.on{color:var(--pri);font-weight:600}
h1{font-size:22px;letter-spacing:-.03em;margin:26px 0 4px}
h2{font-size:17px;letter-spacing:-.02em;margin:30px 0 10px}
h3{font-size:15px;margin:22px 0 8px}
.lead{color:var(--sub);font-size:14px;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
 padding:16px;margin-bottom:12px}
.row{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.nm{font-weight:700;font-size:16px;letter-spacing:-.02em}
.meta{color:var(--sub);font-size:13px;margin-top:3px}
.badge{font-size:12px;font-weight:700;padding:3px 9px;border-radius:99px;white-space:nowrap}
.live{background:var(--live-soft);color:var(--live)}
.soon{background:var(--warn-soft);color:var(--warn)}
.later{background:var(--pri-soft);color:var(--pri)}
.done{background:var(--line);color:var(--sub)}
.na{color:var(--na);font-size:.94em}
.tag-ok{background:var(--live-soft);color:var(--live);font-size:11px;padding:1px 6px;border-radius:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:12px}
.kv{background:var(--bg);border-radius:8px;padding:9px 11px}
.kv dt{font-size:11.5px;color:var(--sub)}
.kv dd{font-size:14px;font-weight:650;margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:10px}
th,td{padding:9px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--sub);font-weight:600;font-size:12px;white-space:nowrap}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.pill{display:inline-block;background:var(--pri-soft);color:var(--pri);font-size:12.5px;
 font-weight:600;padding:5px 11px;border-radius:99px;margin:0 6px 6px 0}
.notice{background:var(--warn-soft);color:var(--warn);border-radius:9px;padding:11px 13px;
 font-size:13px;margin:14px 0}
footer{border-top:1px solid var(--line);margin-top:48px;padding:22px 0 40px;
 color:var(--sub);font-size:12.5px}
footer p{margin-bottom:6px}
.ad{margin:22px 0;min-height:1px}
@media(max-width:560px){.hd{gap:12px}h1{font-size:20px}}
"""

ADS = ('<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
       '?client={c}" crossorigin="anonymous"></script>')


def page(title, desc, body, path, nav_on="", extra_head=""):
    depth = path.count("/")
    up = "../" * depth
    ads = ADS.format(c=ADSENSE_CLIENT) if ADSENSE_CLIENT else ""
    navs = [("", "청약 캘린더"), ("brokers.html", "증권사별"),
            ("results.html", "상장 후 성적"), ("guide/", "가이드")]
    nv = "".join(
        f'<a href="{up}{h}" class="{"on" if h == nav_on else ""}">{t}</a>'
        for h, t in navs)
    return f"""<!doctype html><html lang=ko><head>
<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name=description content="{esc(desc)}">
<link rel=canonical href="{SITE_URL}/{path}">
<meta property=og:title content="{esc(title)}">
<meta property=og:description content="{esc(desc)}">
<meta property=og:type content=website>
<link rel=icon href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text y='26' font-size='26'>📈</text></svg>">
<style>{CSS}</style>{extra_head}{ads}
</head><body>
<header><div class="wrap hd">
<a href="{up}" class=logo>공모주 <b>캘린더</b></a><nav>{nv}</nav>
</div></header>
<main class=wrap>{body}</main>
<footer><div class=wrap>
<p><b>{SITE_NAME}</b> · 금융감독원 전자공시(DART) 증권신고서를 자동 수집해 제공합니다.</p>
<p>본 사이트의 정보는 투자 참고용이며 투자 권유가 아닙니다. 실제 청약 전 반드시
해당 증권사와 <a href="https://dart.fss.or.kr" style="color:var(--pri)">DART 원문 공시</a>를 확인하세요.</p>
<p>마지막 업데이트: {esc(UPDATED)}</p>
</div></footer></body></html>"""


def write(path, html):
    p = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(html)


# ------------------------------------------------------------------ 카드/표
def ipo_card(r, up=""):
    d, cls = dday(r)
    badge = f'<span class="badge {cls}">{d}</span>' if d else ""
    brokers = " ".join(f'<span class=pill>{esc(u["name"])}</span>'
                       for u in r.get("underwriters", [])[:4]) or \
        f'<span class="na">주관사 {NA}</span>'
    return f"""<a href="{up}ipo/{r['corp_code']}.html"><div class=card>
<div class=row><div>
 <div class=nm>{esc(r['corp_name'])}</div>
 <div class=meta>{esc(r.get('market') or '')} · 청약 {period(r)} · 공모가 {band(r)}</div>
</div>{badge}</div>
<div style="margin-top:10px">{brokers}</div>
</div></a>"""


def retail_table(r):
    rows = r.get("retail") or []
    if not rows:
        return f'<p class=na>증권사별 청약 정보 {NA} — DART 원문을 확인하세요.</p>'
    body = "".join(
        f"<tr><td><b>{esc(x['name'])}</b></td><td>{val(x.get('alloc'))}</td>"
        f"<td>{val(x.get('limit'))}</td><td>{val(x.get('margin'))}</td></tr>"
        for x in rows)
    return ('<div class=scroll><table><tr><th>증권사</th><th>일반청약자 배정물량</th>'
            f'<th>최고 청약한도</th><th>증거금률</th></tr>{body}</table></div>')


def uw_table(r):
    rows = r.get("underwriters") or []
    if not rows:
        return f'<p class=na>인수인 정보 {NA}</p>'
    body = "".join(
        f"<tr><td>{esc(x.get('role') or '')}</td><td><b>{esc(x['name'])}</b></td>"
        f"<td>{x['qty']:,}주</td></tr>" if x.get("qty") else
        f"<tr><td>{esc(x.get('role') or '')}</td><td><b>{esc(x['name'])}</b></td>"
        f"<td class=na>{NA}</td></tr>" for x in rows)
    return ('<div class=scroll><table><tr><th>구분</th><th>증권사</th>'
            f'<th>인수물량</th></tr>{body}</table></div>')


# ------------------------------------------------------------------ 페이지
def build_index(items):
    live, soon, later, done = [], [], [], []
    for r in items:
        if r.get("is_spac"):
            continue
        d, c = dday(r)
        (live if c == "live" else soon if c == "soon"
         else done if c == "done" else later).append(r)
    spacs = [r for r in items if r.get("is_spac")]

    def sec(title, rows, empty):
        if not rows:
            return f"<h2>{title}</h2><p class=na>{empty}</p>"
        return f"<h2>{title} <span class=na>{len(rows)}</span></h2>" + \
            "".join(ipo_card(r) for r in rows)

    body = f"""<h1>공모주 청약 일정</h1>
<p class=lead>금융감독원 전자공시(DART) 증권신고서에서 매일 자동 수집합니다.
증권사별 배정물량·청약한도까지 원문 그대로 보여드립니다.</p>
<div class=ad></div>
{sec("🔥 지금 청약 중", live, "현재 청약 진행 중인 종목이 없습니다.")}
{sec("⏰ 곧 시작 (7일 이내)", soon, "7일 이내 시작 예정인 종목이 없습니다.")}
{sec("📅 청약 예정", later, "예정된 종목이 없습니다.")}
<div class=ad></div>
{sec("✅ 청약 마감", done[-12:][::-1], "최근 마감된 종목이 없습니다.")}
{sec("🧪 스팩(SPAC)", spacs, "진행 중인 스팩 공모가 없습니다.")}
"""
    write("index.html", page(f"{SITE_NAME} — 공모주 청약 일정·증권사별 정보",
                             "공모주 청약 일정, 공모가, 주관사, 증권사별 배정물량과 청약한도를 "
                             "DART 공시 기준으로 매일 자동 업데이트합니다.", body, "index.html"))


def build_detail(r):
    d, cls = dday(r)
    badge = f'<span class="badge {cls}">{d}</span>' if d else ""
    warn = ""
    if r.get("missing"):
        warn = (f'<div class=notice>⚠️ 일부 항목이 공시에서 자동 추출되지 않아 '
                f'“{NA}”로 표시됩니다. 정확한 값은 아래 DART 원문을 확인하세요.</div>')
    hist = "".join(f'<li><a href="{h["dart_url"]}" style="color:var(--pri)">'
                   f'{esc(h["rcept_dt"])} {esc(h["report_nm"])}</a></li>'
                   for h in r.get("history", []))
    body = f"""<h1>{esc(r['corp_name'])} 공모주 청약 {badge}</h1>
<p class=lead>{esc(r.get('market') or '')} 상장 예정 · 최근 공시 {esc(r['rcept_dt'])}</p>
{warn}
<div class=card><div class=grid>
<dl class=kv><dt>청약일</dt><dd>{period(r)}</dd></dl>
<dl class=kv><dt>공모가</dt><dd>{band(r)}</dd></dl>
<dl class=kv><dt>납입일</dt><dd>{val(r.get('pay_date'))}</dd></dl>
<dl class=kv><dt>총 공모주식수</dt><dd>{f"{r['shares']:,}주" if r.get('shares') else f'<span class=na>{NA}</span>'}</dd></dl>
<dl class=kv><dt>액면가</dt><dd>{won(r.get('par_value'))}</dd></dl>
<dl class=kv><dt>수요예측 경쟁률</dt><dd>{val(r.get('demand_rate'))}</dd></dl>
</div></div>
<div class=ad></div>
<h2>증권사별 청약 조건</h2>
<p class=lead>내 계좌가 있는 증권사가 목록에 있어야 청약할 수 있습니다.</p>
{retail_table(r)}
<h2>인수인 (주관사·인수단)</h2>
{uw_table(r)}
<h2>공시 원문</h2>
<p class=lead>아래 링크에서 증권신고서 전문을 확인할 수 있습니다.</p>
<ul style="padding-left:18px;font-size:14px">
<li><a href="{r['dart_url']}" style="color:var(--pri)"><b>{esc(r['rcept_dt'])} {esc(r['report_nm'])}</b> (최신)</a></li>
{hist}</ul>
<div class=ad></div>"""
    title = f"{r['corp_name']} 공모주 청약일정·공모가·증권사 | {SITE_NAME}"
    desc = (f"{r['corp_name']} 공모주 청약 {period(r)}, 공모가 "
            f"{re.sub('<[^>]+>', '', band(r))}. 증권사별 배정물량과 청약한도를 확인하세요.")
    write(f"ipo/{r['corp_code']}.html", page(title, desc, body,
                                             f"ipo/{r['corp_code']}.html"))


def build_brokers(items, brokers):
    idx = {}
    for r in items:
        for x in r.get("retail", []):
            idx.setdefault(x["name"], []).append((r, x))
    names = sorted(idx, key=lambda n: -len(idx[n]))
    rows = "".join(
        f'<tr><td><a href="broker/{slug(n)}.html" style="color:var(--pri)"><b>{esc(n)}</b></a></td>'
        f'<td>{esc((brokers.get(n) or {}).get("app") or NA)}</td>'
        f'<td>{len([1 for r, _ in idx[n] if dday(r)[1] in ("live", "soon", "later")])}건</td>'
        f'<td>{len(idx[n])}건</td></tr>' for n in names)
    body = f"""<h1>증권사별 공모주 청약</h1>
<p class=lead>최근 3개월간 공모주 인수에 참여한 증권사 {len(names)}곳입니다.
증권사를 누르면 해당 증권사로 청약 가능한 종목을 볼 수 있습니다.</p>
<div class=notice>청약수수료·우대조건은 증권사 정책에 따라 자주 바뀌므로 현재 표시하지 않습니다.
청약 전 해당 증권사 공지를 확인하세요.</div>
<div class=scroll><table><tr><th>증권사</th><th>MTS 앱</th><th>진행·예정</th><th>최근 3개월</th></tr>
{rows}</table></div>
<div class=ad></div>"""
    write("brokers.html", page(f"증권사별 공모주 청약 가능 종목 | {SITE_NAME}",
                               "증권사별로 청약 가능한 공모주 종목과 배정물량, 청약한도를 정리했습니다.",
                               body, "brokers.html", "brokers.html"))

    for n in names:
        lst = idx[n]
        cards = "".join(
            f"""<div class=card><div class=row><div>
<div class=nm><a href="../ipo/{r['corp_code']}.html">{esc(r['corp_name'])}</a></div>
<div class=meta>청약 {period(r)} · 공모가 {band(r)}</div></div>
{f'<span class="badge {dday(r)[1]}">{dday(r)[0]}</span>' if dday(r)[0] else ''}</div>
<div class=grid>
<dl class=kv><dt>배정물량</dt><dd style="font-size:13px">{val(x.get('alloc'))}</dd></dl>
<dl class=kv><dt>최고 청약한도</dt><dd style="font-size:13px">{val(x.get('limit'))}</dd></dl>
<dl class=kv><dt>증거금률</dt><dd style="font-size:13px">{val(x.get('margin'))}</dd></dl>
</div></div>""" for r, x in sorted(lst, key=lambda t: t[0].get("sub_start") or "9999"))
        info = brokers.get(n) or {}
        body = f"""<h1>{esc(n)} 공모주 청약</h1>
<p class=lead>MTS 앱 {esc(info.get('app') or NA)} · 최근 3개월 {len(lst)}건 참여</p>
<div class=ad></div>{cards}"""
        write(f"broker/{slug(n)}.html",
              page(f"{n} 공모주 청약 가능 종목·청약한도 | {SITE_NAME}",
                   f"{n}에서 청약할 수 있는 공모주 종목, 배정물량, 최고 청약한도, 증거금률 정리.",
                   body, f"broker/{slug(n)}.html", "brokers.html"))


def build_results(items):
    done = [r for r in items if dday(r)[1] == "done" and not r.get("is_spac")]
    rows = "".join(
        f'<tr><td><a href="ipo/{r["corp_code"]}.html" style="color:var(--pri)">'
        f'<b>{esc(r["corp_name"])}</b></a></td><td>{period(r)}</td>'
        f'<td>{re.sub("<[^>]+>", "", band(r))}</td>'
        f'<td class=na>{NA}</td><td class=na>{NA}</td></tr>'
        for r in done[::-1][:40])
    body = f"""<h1>상장 후 성적표</h1>
<p class=lead>청약이 끝난 종목의 상장 당일 시초가와 현재 수익률입니다.</p>
<div class=notice>시세 연동은 준비 중입니다. 현재는 청약 마감 종목 목록만 제공합니다.</div>
<div class=scroll><table><tr><th>종목</th><th>청약일</th><th>공모가</th>
<th>시초가</th><th>수익률</th></tr>{rows}</table></div>
<div class=ad></div>"""
    write("results.html", page(f"공모주 상장 후 성적표 | {SITE_NAME}",
                               "공모주 상장일 시초가와 수익률 기록.", body,
                               "results.html", "results.html"))


GUIDES = [
    ("what-is-ipo", "공모주 청약이란? 처음부터 끝까지",
     "공모주가 무엇인지, 왜 사람들이 청약하는지, 전체 흐름을 순서대로 정리했습니다.",
     """<h2>공모주가 뭔가요</h2>
<p>회사가 주식시장에 처음 상장할 때, 일반 투자자에게 주식을 나눠주는 절차를 <b>공모(公募)</b>라고
합니다. 이때 정해지는 가격이 <b>공모가</b>이고, 이 주식을 사겠다고 신청하는 것이 <b>청약</b>입니다.</p>
<h2>전체 흐름</h2>
<ol style="padding-left:20px">
<li><b>증권신고서 제출</b> — 회사가 DART에 공시합니다. 이때 희망 공모가 밴드가 공개됩니다.</li>
<li><b>수요예측</b> — 기관투자자들이 얼마에 얼마나 살지 써냅니다. 경쟁률이 높으면 공모가가 밴드 상단에서 정해집니다.</li>
<li><b>확정 공모가 발표</b> — 수요예측 결과로 최종 가격이 정해집니다.</li>
<li><b>일반 청약</b> — 보통 이틀간 진행됩니다. 이 기간에 증거금을 넣습니다.</li>
<li><b>배정·환불</b> — 청약 마감 2영업일 뒤 배정 결과가 나오고 남은 증거금이 환불됩니다.</li>
<li><b>상장</b> — 보통 청약 마감 후 1~2주 안에 시장에서 거래가 시작됩니다.</li>
</ol>
<h2>청약하려면 무엇이 필요한가요</h2>
<p>해당 공모주의 <b>주관사·인수단으로 참여한 증권사</b>에 계좌가 있어야 합니다. 어떤 증권사가
참여하는지는 종목마다 다르고, 증권신고서에 명시됩니다. 이 사이트의 종목 상세 페이지에서
확인할 수 있습니다.</p>
<p>증권사에 따라 <b>청약 전에 일정 기간 계좌를 보유</b>하고 있어야 하거나, 자산 규모에 따라
청약 한도가 달라지기도 합니다.</p>"""),

    ("equal-allocation", "균등배정과 비례배정, 뭐가 다른가요",
     "공모주 물량을 나누는 두 가지 방식의 차이와 각각의 계산법을 정리했습니다.",
     """<h2>두 가지 배정 방식</h2>
<p>일반 청약자에게 돌아가는 물량은 <b>균등배정</b>과 <b>비례배정</b>으로 나뉩니다.
보통 각각 절반씩입니다.</p>
<h2>균등배정</h2>
<p>최소 청약 수량만 넣으면 <b>청약한 사람 수로 똑같이 나눠주는</b> 방식입니다.
많이 넣는다고 더 받지 않습니다. 그래서 여러 증권사에 계좌를 만들어 각각 최소 수량만
청약하는 전략이 나온 것입니다.</p>
<p>예를 들어 균등 물량이 10만 주인데 10만 명이 청약했다면 1인당 1주입니다.
20만 명이면 0.5주가 되고, 이때는 추첨으로 나눕니다.</p>
<h2>비례배정</h2>
<p>넣은 금액에 <b>비례해서</b> 나눠줍니다. 경쟁률이 500:1이면 500주를 청약해야 1주를 받습니다.
증거금률이 50%라면, 공모가 2만 원짜리 500주는 증거금 500만 원이 필요합니다.</p>
<h2>청약 한도</h2>
<p>증권사마다 <b>최고 청약한도</b>가 정해져 있습니다. 우대 등급이면 한도가 2~3배로 늘어나기도
합니다. 이 사이트의 종목 상세 페이지에 증권사별 한도가 공시 원문 그대로 표시됩니다.</p>"""),

    ("schedule-reading", "청약일·납입일·환불일 읽는 법",
     "공모주 일정에 나오는 날짜들이 각각 무엇을 뜻하는지 설명합니다.",
     """<h2>날짜별 의미</h2>
<table><tr><th>날짜</th><th>무슨 날인가</th></tr>
<tr><td><b>청약기일</b></td><td>실제로 청약을 넣는 기간. 보통 이틀. 증거금이 이때 빠져나갑니다.</td></tr>
<tr><td><b>배정공고일</b></td><td>몇 주를 받았는지 확정되는 날.</td></tr>
<tr><td><b>납입기일</b></td><td>배정된 주식 값이 최종 결제되는 날. 남은 증거금은 이날 환불됩니다.</td></tr>
<tr><td><b>상장일</b></td><td>시장에서 거래가 시작되는 날. 별도 공시로 정해집니다.</td></tr></table>
<h2>증거금은 언제 돌아오나요</h2>
<p>보통 <b>청약 마감 후 2영업일</b>에 환불됩니다. 배정받은 주식 값을 뺀 나머지가 계좌로
돌아옵니다. 이 기간 동안 돈이 묶이므로, 여러 종목이 겹칠 때는 일정을 미리 확인하는 게 좋습니다.</p>
<h2>주의</h2>
<p>정정신고서가 제출되면 일정이 바뀔 수 있습니다. 이 사이트는 최신 공시를 기준으로 매일
갱신하지만, 청약 직전에는 증권사 공지를 한 번 더 확인하시는 걸 권합니다.</p>"""),
]


def build_guides():
    lst = "".join(
        f'<a href="{s}.html"><div class=card><div class=nm>{esc(t)}</div>'
        f'<div class=meta>{esc(d)}</div></div></a>' for s, t, d, _ in GUIDES)
    write("guide/index.html", page(f"공모주 가이드 | {SITE_NAME}",
                                   "공모주 청약 방법, 균등배정·비례배정, 일정 읽는 법을 정리했습니다.",
                                   f"<h1>공모주 가이드</h1><p class=lead>처음이라면 위에서부터 읽어보세요."
                                   f"</p><div class=ad></div>{lst}", "guide/index.html", "guide/"))
    for i, (s, t, d, html) in enumerate(GUIDES):
        nxt = GUIDES[i + 1] if i + 1 < len(GUIDES) else None
        more = (f'<h2>다음 글</h2><a href="{nxt[0]}.html"><div class=card>'
                f'<div class=nm>{esc(nxt[1])}</div></div></a>') if nxt else ""
        body = (f"<h1>{esc(t)}</h1><p class=lead>{esc(d)}</p><div class=ad></div>"
                f"{html}<div class=ad></div>{more}")
        write(f"guide/{s}.html", page(f"{t} | {SITE_NAME}", d, body,
                                      f"guide/{s}.html", "guide/"))


def build_meta(items):
    urls = ["", "brokers.html", "results.html", "guide/"] + \
        [f"guide/{s}.html" for s, *_ in GUIDES] + \
        [f"ipo/{r['corp_code']}.html" for r in items]
    xml = "".join(f"<url><loc>{SITE_URL}/{u}</loc><lastmod>{TODAY}</lastmod></url>"
                  for u in urls)
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>'
          f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{xml}</urlset>')
    write("robots.txt", f"User-agent: *\nAllow: /\nDisallow: /admin/\n"
                        f"Sitemap: {SITE_URL}/sitemap.xml\n")


def main():
    global UPDATED
    d = json.load(open(os.path.join(DATA, "ipos.json"), encoding="utf-8"))
    UPDATED = d["updated_at"]
    items = d["items"]
    brokers = json.load(open(os.path.join(DATA, "brokers.json"),
                             encoding="utf-8"))["brokers"]

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    build_index(items)
    for r in items:
        build_detail(r)
    build_brokers(items, brokers)
    build_results(items)
    build_guides()
    build_meta(items)

    # 관리자 화면 + 원본 데이터 동봉 (robots.txt 로 색인 제외)
    adm = os.path.join(ROOT, "admin")
    if os.path.exists(adm):
        shutil.copytree(adm, os.path.join(OUT, "admin"))
    shutil.copy(os.path.join(DATA, "ipos.json"), os.path.join(OUT, "ipos.json"))

    n = sum(len(fs) for _, _, fs in os.walk(OUT))
    print(f"빌드 완료 — {n}개 파일, 종목 {len(items)}건")


if __name__ == "__main__":
    main()
