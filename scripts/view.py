#!/usr/bin/env python3
"""矩阵检视器：从 L0 事件流生成四种视图。

  1. heatmap.csv   维度 × ISO周，值为记录数        → 看哪里断了
  2. status.csv    每个维度最新一次记录 + 距今天数  → 看现在什么样
  3. gaps.md       缺口报告（按 resolution 判定）   → 今天该问什么
  4. coverage.md   覆盖度汇总

用法：python3 scripts/view.py
"""
import csv
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "events"
TREE = ROOT / "schema" / "dimension-tree.json"
OUT = ROOT / "derived"

# resolution → 允许的最大静默天数
MAX_SILENT = {"T0": 2, "T1": 10, "T2": 40, "T3": 120}


def load_tree():
    t = json.loads(TREE.read_text(encoding="utf-8"))
    dims = {}
    for dom in t["domains"]:
        for ch in dom["children"]:
            dims[ch["id"]] = {
                "name": ch["name"],
                "resolution": ch.get("resolution", "T2"),
                "domain": dom["name"],
                "metrics": [m["id"] for m in ch.get("metrics", [])],
            }
    return dims


def load_events():
    evs = []
    for f in sorted(EVENTS.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                evs.append(json.loads(line))
    return evs


def main():
    if not OUT.exists():
        OUT.mkdir(parents=True)
    dims = load_tree()
    evs = load_events()
    today = date.today()

    # dim → [(date, metric)]
    hits = defaultdict(list)
    for e in evs:
        d = datetime.fromisoformat(e["ts"]).date()
        for dm in [e["dim_primary"]] + e.get("dim_secondary", []):
            if dm in dims:
                hits[dm].append(d)

    # 1) 热力图：ISO 周 × 维度
    weeks = sorted({datetime.fromisoformat(e["ts"]).date().isocalendar()[:2] for e in evs})
    week_keys = [f"{y}-W{w:02d}" for y, w in weeks]
    hm = defaultdict(lambda: defaultdict(int))
    for e in evs:
        y, w, _ = datetime.fromisoformat(e["ts"]).date().isocalendar()
        wk = f"{y}-W{w:02d}"
        for dm in [e["dim_primary"]] + e.get("dim_secondary", []):
            hm[dm][wk] += 1

    with open(OUT / "heatmap.csv", "w", newline="", encoding="utf-8-sig") as f:
        cols = ["dim", "name", "resolution"] + week_keys
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for dm, info in dims.items():
            row = {"dim": dm, "name": info["name"], "resolution": info["resolution"]}
            for wk in week_keys:
                row[wk] = hm[dm].get(wk) or ""
            w.writerow(row)

    # 2) 状态视图
    rows = []
    for dm, info in dims.items():
        ds = sorted(hits.get(dm, []))
        last = ds[-1] if ds else None
        silent = (today - last).days if last else None
        limit = MAX_SILENT[info["resolution"]]
        if last is None:
            state = "空"
        elif silent > limit:
            state = "超期"
        else:
            state = "在期"
        rows.append({
            "dim": dm, "name": info["name"], "domain": info["domain"],
            "resolution": info["resolution"], "n_obs": len(ds),
            "last": last.isoformat() if last else "",
            "silent_days": silent if silent is not None else "",
            "limit_days": limit, "state": state,
        })
    rows.sort(key=lambda r: (r["state"] != "空", r["state"] != "超期", r["dim"]))

    with open(OUT / "status.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # 3) 缺口报告
    empty = [r for r in rows if r["state"] == "空"]
    stale = [r for r in rows if r["state"] == "超期"]
    ok = [r for r in rows if r["state"] == "在期"]

    lines = ["# 矩阵缺口报告", "", f"生成时间：{today.isoformat()}　事件总数：{len(evs)}", "",
             f"## 覆盖度", "",
             f"- 在期：{len(ok)} / {len(rows)}",
             f"- 超期：{len(stale)}",
             f"- 从未记录：{len(empty)}", ""]
    if stale:
        lines += ["## 超期维度（该补了）", "",
                  "| 维度 | 名称 | 分辨率 | 最后记录 | 已静默 | 上限 |",
                  "|---|---|---|---|---|---|"]
        lines += [f"| {r['dim']} | {r['name']} | {r['resolution']} | {r['last']} | {r['silent_days']}天 | {r['limit_days']}天 |"
                  for r in stale]
        lines.append("")
    if empty:
        lines += ["## 从未记录", "",
                  "| 维度 | 名称 | 分辨率 |", "|---|---|---|"]
        lines += [f"| {r['dim']} | {r['name']} | {r['resolution']} |" for r in empty]
        lines.append("")
    lines += ["## 今日建议采集顺序", "",
              "按缺口严重度（T0 优先，其次静默天数）排序：", ""]
    prio = sorted(stale + empty,
                  key=lambda r: ({"T0": 0, "T1": 1, "T2": 2, "T3": 3}[r["resolution"]],
                                 -(r["silent_days"] or 9999)))
    for i, r in enumerate(prio[:6], 1):
        lines.append(f"{i}. **{r['dim']} {r['name']}**（{r['resolution']}）")
    lines.append("")

    (OUT / "gaps.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"事件 {len(evs)} 条，维度 {len(rows)} 个")
    print(f"  在期 {len(ok)} / 超期 {len(stale)} / 空 {len(empty)}")
    print("已生成：derived/heatmap.csv  status.csv  gaps.md")
    print("\n--- 状态 ---")
    for r in rows[:8]:
        print(f"  {r['dim']:4} {r['name']:8} {r['resolution']}  {r['state']:4} "
              f"n={r['n_obs']} last={r['last'] or '-'}")


if __name__ == "__main__":
    main()
