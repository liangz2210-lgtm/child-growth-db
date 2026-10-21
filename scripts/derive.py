#!/usr/bin/env python3
"""L0(events/*.jsonl, schema v2) → L1(events.csv) → L2(daily.csv / weekly.csv)

铁律：所有数字由本脚本算，LLM 不参与任何计算。
- 不插补：缺失留空
- 不推测：retract 的记录排除，corrects 取最新版本
- 可回溯：L2 输出 source_event_ids
"""
import csv
import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "events"
OUT = ROOT / "derived"
def load_birth():
    """从 profile/child-profile.md 的 frontmatter 读生日。读不到就返回 None（age 列留空，不猜）。"""
    p = ROOT / "profile" / "child-profile.md"
    if not p.exists():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("birthday:"):
            v = line.split(":", 1)[1].strip()
            try:
                return datetime.fromisoformat(v).date()
            except ValueError:
                return None
    return None


BIRTH = load_birth()

DAILY_METRICS = ["sleep.bedtime", "sleep.waketime", "sleep.nap_h", "emo.tantrum_lvl"]


def hhmm_to_min(s):
    h, m = str(s).split(":")
    v = int(h) * 60 + int(m)
    return v + 1440 if v < 720 else v


def min_to_hhmm(v):
    v %= 1440
    return f"{v // 60:02d}:{v % 60:02d}"


def load():
    evs = []
    for f in sorted(EVENTS.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                evs.append(json.loads(line))
    return evs


def resolve(evs):
    """处理 retract 与 corrects：同一逻辑记录只留最新有效版本。"""
    active = {}
    retracted = {e["id"] for e in evs if e.get("retract")}
    by_id = {e["id"]: e for e in evs}

    # 被 corrects 指向的旧版本作废
    superseded = {e["corrects"] for e in evs if e.get("corrects")}
    out = []
    for e in evs:
        if e["id"] in retracted or e.get("retract"):
            continue
        if e["id"] in superseded:
            continue
        out.append(e)
    return out


def main():
    if not OUT.exists():
        OUT.mkdir(parents=True)

    all_evs = load()
    evs = resolve(all_evs)
    evs.sort(key=lambda e: e["ts"])

    # ---- L1 ----
    cols = ["id", "ts", "date", "period", "age_days", "type", "dim_primary",
            "dim_secondary", "text", "observer", "channel", "evidence_type",
            "confidence", "observed", "metric", "value", "unit", "note"]
    with open(OUT / "events.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for e in evs:
            d = datetime.fromisoformat(e["ts"]).date()
            w.writerow({
                "id": e["id"],
                "ts": e["ts"],
                "date": d.isoformat(),
                "period": e.get("period", ""),
                "age_days": (d - BIRTH).days if BIRTH else "",
                "type": e["type"],
                "dim_primary": e["dim_primary"],
                "dim_secondary": "|".join(e.get("dim_secondary", [])),
                "text": e["text"],
                "observer": e["observer"],
                "channel": e["channel"],
                "evidence_type": e["evidence_type"],
                "confidence": e.get("confidence", ""),
                "observed": e["observed"],
                "metric": e.get("metric", ""),
                "value": e.get("value", ""),
                "unit": e.get("unit", ""),
                "note": e.get("note", ""),
            })

    # ---- 按日聚合（只取 observed=true 的 measurement） ----
    day_vals = defaultdict(dict)
    day_src = defaultdict(lambda: defaultdict(list))
    day_obs = defaultdict(set)
    day_n = defaultdict(int)

    for e in evs:
        d = datetime.fromisoformat(e["ts"]).date().isoformat()
        day_n[d] += 1
        day_obs[d].add(e["observer"])
        if e["type"] == "measurement" and e["observed"] and e.get("metric"):
            day_vals[d][e["metric"]] = e.get("value")
            day_src[d][e["metric"]].append(e["id"])

    days = sorted(day_n)
    if not days:
        print("没有事件，退出")
        return

    rows = []
    for d in days:
        day = datetime.fromisoformat(d).date()
        cur = day_vals.get(d, {})

        night, night_src = "", []
        prev = (day - timedelta(days=1)).isoformat()
        if "sleep.waketime" in cur and "sleep.bedtime" in day_vals.get(prev, {}):
            wk = hhmm_to_min(cur["sleep.waketime"])
            bt = hhmm_to_min(day_vals[prev]["sleep.bedtime"])
            night = round(((wk - bt) % 1440) / 60, 2)
            night_src = day_src[d]["sleep.waketime"] + day_src[prev]["sleep.bedtime"]

        src_all = sorted({i for m in day_src[d] for i in day_src[d][m]})

        rows.append({
            "date": d,
            "age_days": (day - BIRTH).days if BIRTH else "",
            "bedtime": cur.get("sleep.bedtime", ""),
            "waketime": cur.get("sleep.waketime", ""),
            "nap_h": cur.get("sleep.nap_h", ""),
            "tantrum_lvl": cur.get("emo.tantrum_lvl", ""),
            "night_sleep_h": night,
            "n_events": day_n[d],
            "observers": "|".join(sorted(day_obs[d])),
            "source_event_ids": "|".join(night_src or src_all),
        })

    with open(OUT / "daily.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- 周聚合 ----
    wk = defaultdict(lambda: {"bed": [], "night": [], "nap": [], "days": set()})
    for r in rows:
        k = datetime.fromisoformat(r["date"]).isocalendar()
        key = f"{k[0]}-W{k[1]:02d}"
        g = wk[key]
        g["days"].add(r["date"])
        if r["bedtime"]:
            g["bed"].append(hhmm_to_min(r["bedtime"]))
        if r["night_sleep_h"]:
            g["night"].append(float(r["night_sleep_h"]))
        if r["nap_h"]:
            g["nap"].append(float(r["nap_h"]))

    wrows = []
    for k in sorted(wk):
        g = wk[k]
        wrows.append({
            "week": k,
            "n_days": len(g["days"]),
            "bedtime_mean": min_to_hhmm(round(statistics.mean(g["bed"]))) if g["bed"] else "",
            "bedtime_sd_min": round(statistics.pstdev(g["bed"]), 1) if len(g["bed"]) > 1 else "",
            "night_sleep_avg": round(statistics.mean(g["night"]), 2) if g["night"] else "",
            "nap_avg": round(statistics.mean(g["nap"]), 2) if g["nap"] else "",
            "data_completeness": f"{len(g['days']) / 7:.0%}",
        })

    with open(OUT / "weekly.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(wrows[0].keys()))
        w.writeheader()
        w.writerows(wrows)

    print(f"✅ L0 {len(all_evs)} 条（有效 {len(evs)}）→ L1 events.csv")
    print(f"✅ {len(rows)} 天 → L2 daily.csv")
    print(f"✅ {len(wrows)} 周 → L2 weekly.csv")
    if len(all_evs) != len(evs):
        print(f"   （排除撤回/被更正 {len(all_evs) - len(evs)} 条）")
    for r in rows:
        print("  ", r)


if __name__ == "__main__":
    main()
