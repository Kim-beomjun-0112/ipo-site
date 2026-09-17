"""DART에서 공모주 정보를 수집해 data/ipos.json 으로 저장한다.

- 같은 회사의 최초신고서 / 기재정정 / 발행조건확정을 하나로 병합한다
  (최신 접수건 값을 우선하되, 비어 있으면 과거 값을 살린다)
- data/overrides.json 의 수동 수정값을 마지막에 덮어쓴다 (관리자 검수 결과)
- 유상증자는 제외, 스팩은 따로 표시해서 보관한다

실행: DART_API_KEY=xxx python scripts/collect.py
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))
import dart  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
KST = timezone(timedelta(hours=9))

MERGE_KEYS = ("price_band", "final_price", "shares", "par_value", "method",
              "sub_start", "sub_end", "pay_date", "demand_rate", "market")


def merge(base, newer):
    """newer(최신 접수건)를 우선하되, 비어 있는 필드는 base에서 살린다."""
    out = dict(newer)
    for k in MERGE_KEYS:
        if not out.get(k) and base.get(k):
            out[k] = base[k]
    for k in ("underwriters", "retail"):
        if not out.get(k) and base.get(k):
            out[k] = base[k]
    out["history"] = base.get("history", []) + [
        {"rcept_no": base["rcept_no"], "report_nm": base["report_nm"],
         "rcept_dt": base["rcept_dt"], "dart_url": base["dart_url"]}
    ]
    return out


def main():
    if not dart.API_KEY:
        sys.exit("DART_API_KEY 환경변수가 없습니다.")

    print("[1/4] 공시 목록 조회…")
    items = dart.fetch_list(days=88)
    print(f"      증권신고서(지분증권) {len(items)}건")

    # 접수일 오름차순 → 나중 건이 앞의 것을 덮어쓰도록
    items.sort(key=lambda x: x["rcept_no"])

    # 이미 파싱해둔 공시는 다시 받지 않는다 (매일 돌 때 대부분 재사용됨)
    pc_path = os.path.join(DATA, "_parsed.json")
    parsed = {}
    if os.path.exists(pc_path):
        try:
            parsed = json.load(open(pc_path, encoding="utf-8"))
        except Exception:
            parsed = {}
    reused = 0

    # 새로 받아야 할 공시는 병렬로 미리 내려받는다 (DART 문서가 커서 순차는 매우 느림)
    todo = [i["rcept_no"] for i in items if i["rcept_no"] not in parsed]
    if todo:
        print(f"      신규 공시 {len(todo)}건 내려받는 중...", flush=True)
        done = [0]

        def grab(rn):
            try:
                dart.fetch_doc(rn)
            except Exception:
                pass
            done[0] += 1
            if done[0] % 25 == 0:
                print(f"        {done[0]}/{len(todo)}", flush=True)

        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(grab, todo))

    by_corp = {}
    rights = set()
    fails = []
    skipped = []
    for n, it in enumerate(items, 1):
        try:
            if it["rcept_no"] in parsed:
                d = parsed[it["rcept_no"]]
                reused += 1
            else:
                d = dart.parse(it["rcept_no"], it["corp_name"], it["corp_code"],
                               it["rcept_dt"], it["report_nm"],
                               it.get("stock_code", ""))
                parsed[it["rcept_no"]] = d
        except dart.NoDocument:
            skipped.append(it["rcept_no"])
            continue
        except Exception as e:
            fails.append(f"{it['corp_name']} {it['rcept_no']}: {e}")
            continue
        if d.get("is_rights") or (it.get("stock_code") or "").strip():
            rights.add(it["corp_code"])   # 상장사 유상증자 — 공모주 아님
            continue
        key = it["corp_code"]
        by_corp[key] = merge(by_corp[key], d) if key in by_corp else d
        if n % 20 == 0:
            print(f"      {n}/{len(items)} 처리")

    # 3개월 창을 벗어난 공시는 캐시에서 정리
    live_ids = {i["rcept_no"] for i in items}
    parsed = {k: v for k, v in parsed.items() if k in live_ids}
    json.dump(parsed, open(pc_path, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"      캐시 재사용 {reused}건 / 신규 {len(items)-reused-len(fails)}건")

    rows = [v for k, v in by_corp.items() if k not in rights]

    # 수동 수정값 적용 -------------------------------------------------
    ov_path = os.path.join(DATA, "overrides.json")
    overrides = {}
    if os.path.exists(ov_path):
        overrides = json.load(open(ov_path, encoding="utf-8"))
    for r in rows:
        ov = overrides.get(r["corp_code"]) or overrides.get(r["corp_name"])
        if not ov:
            continue
        for k, v in ov.items():
            if v not in (None, "", []):
                r[k] = v
        r["manually_checked"] = True

    # 누락 필드 재계산 (수동 수정 반영 후)
    for r in rows:
        r["missing"] = [k for k in ("price_band", "sub_start", "sub_end", "pay_date")
                        if not r.get(k)]
        if not r.get("underwriters"):
            r["missing"].append("underwriters")
        if not any(x.get("limit") for x in r.get("retail", [])):
            r["missing"].append("retail_limit")

    rows.sort(key=lambda r: (r.get("sub_start") or "9999", r["corp_name"]))

    os.makedirs(DATA, exist_ok=True)
    out = {
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "count": len(rows),
        "items": rows,
    }
    json.dump(out, open(os.path.join(DATA, "ipos.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    ipo = [r for r in rows if not r["is_spac"]]
    clean = [r for r in ipo if not r["missing"]]
    print(f"\n[2/4] 저장 완료 — 전체 {len(rows)}건 (일반 공모주 {len(ipo)}, 스팩 {len(rows)-len(ipo)})")
    print(f"[3/4] 완전 추출 {len(clean)}/{len(ipo)}건, 검수 필요 {len(ipo)-len(clean)}건")
    if fails:
        print(f"[4/4] 파싱 실패 {len(fails)}건")
        for f in fails[:10]:
            print("      -", f)
    else:
        print("[4/4] 파싱 실패 없음")
    if skipped:
        print(f"      (DART가 원본을 제공하지 않아 건너뛴 공시 {len(skipped)}건 — 정상)")


if __name__ == "__main__":
    main()
