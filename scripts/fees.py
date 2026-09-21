"""증권신고서 본문에서 증권사별 청약수수료를 뽑는다.

수수료는 고객 등급별 표로 적혀 있어서 숫자가 여러 개 나온다.
일반 등급이 가장 비싸므로 최댓값을 일반 기준으로 보고, 0원이 섞여 있으면
우대 시 면제로 표시한다. 표에서 엉뚱한 숫자를 집는 일을 막으려고
실제로 쓰이는 금액대(ALLOWED)만 통과시킨다.

검증(2026-09, 공모 14건): 대신 2,000/3,000 · 미래에셋 2,000/5,000
하나 2,000/4,000 · 삼성 2,000/5,000 · 한국투자 2,000/5,000 — 같은 증권사는
종목이 달라도 같은 값이 나오고, 외부 정리 자료와도 일치한다.
"""
import re

MONEY = re.compile(r'(면제|무료|없음|0\s*원|[\d,]{3,7}\s*원)')
ON_KW = r'(?:온\s?라인|On\s?-?\s?[Ll]ine|HTS|MTS|WTS|홈페이지|ARS|모바일)'
OFF_KW = r'(?:영업점|지\s?점|내\s?점|유\s?선|Off\s?-?\s?[Ll]ine|고객지원|고객센터|창구|방문)'
KW = re.compile(f'({ON_KW})|({OFF_KW})')


# 실제로 쓰이는 청약수수료 금액대. 이 밖의 숫자는 표에서 잘못 집은 것으로 본다.
ALLOWED = {0, 1000, 1500, 2000, 2500, 3000, 4000, 5000}


def _won(s):
    s = s.strip()
    if re.match(r'면제|무료|없음|0\s*원', s):
        return 0
    n = re.sub(r'[^\d]', '', s)
    return int(n) if n else None


def _fmt(v):
    return "면제" if v == 0 else f"{v:,}원"


def _scan(seg):
    import re

MONEY = re.compile(r'(면제|무료|없음|0\s*원|[\d,]{3,7}\s*원)')
ON_KW = r'(?:온\s?라인|On\s?-?\s?[Ll]ine|HTS|MTS|WTS|홈페이지|ARS|모바일)'
OFF_KW = r'(?:영업점|지\s?점|내\s?점|유\s?선|Off\s?-?\s?[Ll]ine|고객지원|고객센터|창구|방문)'
KW = re.compile(f'({ON_KW})|({OFF_KW})')


# 실제로 쓰이는 청약수수료 금액대. 이 밖의 숫자는 표에서 잘못 집은 것으로 본다.
ALLOWED = {0, 1000, 1500, 2000, 2500, 3000, 4000, 5000}


def _won(s):
    s = s.strip()
    if re.match(r'면제|무료|없음|0\s*원', s):
        return 0
    n = re.sub(r'[^\d]', '', s)
    return int(n) if n else None


def _fmt(v):
    return "면제" if v == 0 else f"{v:,}원"


def _scan(seg):
    """구간을 온라인/오프라인 키워드로 쪼개고, 각 구간의 금액들을 모은다.

    수수료는 고객 등급별 표라서 한 줄에 여러 금액이 나온다.
    일반 등급이 가장 비싸므로 최댓값을 '일반 기준'으로, 0원이 섞여 있으면
    우대 시 면제로 본다.
    """
    hits = [(m.start(), m.end(), 'on' if m.group(1) else 'off')
            for m in KW.finditer(seg)]
    if not hits:
        return {}
    buckets = {'on': [], 'off': []}
    for i, (s, e, kind) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else min(len(seg), e + 120)
        for m in MONEY.finditer(seg[e:end]):
            v = _won(m.group(1))
            if v is not None and v in ALLOWED:
                buckets[kind].append(v)
    return buckets


def parse_fees(plain, brokers):
    """공시에서 증권사별 청약수수료를 뽑는다 -> {증권사: {online, offline, free, raw}}"""
    acc = {}
    for m in re.finditer(r'청\s?약\s?수\s?수\s?료', plain):
        seg = re.sub(r'\s+', ' ', plain[m.start(): m.start() + 500])
        back = plain[max(0, m.start() - 3000): m.start()]
        owner, pos = None, -1
        for b in brokers:
            p = back.rfind(b)
            if p > pos:
                owner, pos = b, p
        if not owner:
            continue
        b = _scan(seg)
        if not b or not (b['on'] or b['off']):
            continue
        cur = acc.setdefault(owner, {'on': [], 'off': [], 'raw': ''})
        cur['on'] += b['on']
        cur['off'] += b['off']
        if len(seg) > len(cur['raw']):
            cur['raw'] = seg[:300]

    out = {}
    for name, v in acc.items():
        rec = {'online': None, 'offline': None, 'free': False,
               'raw': v['raw'].strip()}
        for key, src in (('online', v['on']), ('offline', v['off'])):
            if not src or max(src) == 0:
                continue   # 전부 0원이면 '미배정 시 면제' 같은 문장을 집은 것
            rec[key] = _fmt(max(src))
            if 0 in src:
                rec['free'] = True
        if rec['online'] or rec['offline']:
            out[name] = rec
    return out
