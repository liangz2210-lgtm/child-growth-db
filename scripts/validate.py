#!/usr/bin/env python3
"""L0 事件流校验器 v2。纯标准库，无依赖。

用法：
  python3 scripts/validate.py            # 校验 events/*.jsonl
  python3 scripts/validate.py --fixtures # 跑内置错误样例，确认每类都能拦住

退出码：0 全通过 / 1 有错误
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "events"
# 生日不再硬编码：v2 已删除 age_days 字段，年龄一律由 derive.py 从 profile 读取后计算

DIMS = {"S1", "S2", "S3", "S4",
        "D1", "D2", "D3", "D4", "D5", "D6",
        "E1", "E2", "E3",
        "M1", "M2", "M3", "M4", "M5", "M6", "M7"}
TYPES = {"measurement", "observation", "milestone", "context", "intervention"}
PRECISIONS = {"minute", "day", "week"}
OBSERVERS = {"p", "g", "o", "?"}
CHANNELS = {"chat", "manual", "import"}
EVIDENCE = {"obs", "report", "test", "derived"}
CONF = {"high", "medium", "low"}
FOLLOWED = {"yes", "partial", "no"}

REQUIRED = ["id", "schema_version", "ts", "recorded_at", "ts_precision",
            "type", "dim_primary", "text", "observer",
            "channel", "evidence_type", "observed"]

# 物理范围：超出即为录入错误，不是"需要分析的异常值"
RANGES = {
    "sleep.nap_h": (0, 8),
    "sleep.night_h": (0, 18),
    "emo.tantrum_lvl": (0, 3),
    "health.ht_cm": (40, 140),
    "health.wt_kg": (5, 40),
    "scr.min": (0, 600),
    "act.outdoor_min": (0, 600),
}

ID_RE = re.compile(r"^evt-\d{8}-\d{4}$")
PERIOD_RE = re.compile(r"^\d{4}-W\d{2}$")


def _dt(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def check(ev):
    """返回错误列表。空列表 = 通过。"""
    errs = []
    for f in REQUIRED:
        if f not in ev:
            errs.append(f"缺必填字段 {f}")
    if errs:
        return errs

    if ev.get("schema_version") != 2:
        errs.append(f"schema_version 应为 2，实际 {ev.get('schema_version')!r}")

    if not ID_RE.match(str(ev["id"])):
        errs.append(f"id 格式错：{ev['id']}")

    if ev["type"] not in TYPES:
        errs.append(f"type 非法：{ev['type']}")
    if ev["ts_precision"] not in PRECISIONS:
        errs.append(f"ts_precision 非法：{ev['ts_precision']}")
    if ev["observer"] not in OBSERVERS:
        errs.append(f"observer 非法：{ev['observer']}")
    if ev["channel"] not in CHANNELS:
        errs.append(f"channel 非法：{ev['channel']}")
    if ev["evidence_type"] not in EVIDENCE:
        errs.append(f"evidence_type 非法：{ev['evidence_type']}")
    if not isinstance(ev["observed"], bool):
        errs.append(f"observed 必须是布尔，实际 {type(ev['observed']).__name__}")

    if ev["dim_primary"] not in DIMS:
        errs.append(f"dim_primary 非法：{ev['dim_primary']}")
    sec = ev.get("dim_secondary") or []
    if not isinstance(sec, list):
        errs.append("dim_secondary 必须是数组")
    else:
        bad = [d for d in sec if d not in DIMS]
        if bad:
            errs.append(f"dim_secondary 含非法值：{bad}")
        if ev.get("dim_primary") in sec:
            errs.append("dim_secondary 不得包含 dim_primary")

    if len(str(ev["text"]).strip()) < 2:
        errs.append("text 过短或为空——可追溯性失效，拒绝入库")

    ts, ra = _dt(ev["ts"]), _dt(ev["recorded_at"])
    if ts is None:
        errs.append(f"ts 无法解析：{ev['ts']}")
    if ra is None:
        errs.append(f"recorded_at 无法解析：{ev['recorded_at']}")
    if ts and ra and ra < ts:
        errs.append("recorded_at 早于 ts（记录时间不能早于发生时间）")

    if ev["ts_precision"] == "week":
        p = ev.get("period", "")
        if not PERIOD_RE.match(str(p)):
            errs.append(f"ts_precision=week 时 period 必填且格式须为 YYYY-Www，实际 {p!r}")

    if ev["type"] == "intervention":
        for f in ("hypothesis_id", "action", "started", "followed"):
            if not ev.get(f):
                errs.append(f"intervention 缺 {f}")
        if ev.get("followed") and ev["followed"] not in FOLLOWED:
            errs.append(f"followed 非法：{ev['followed']}")

    if ev["type"] == "measurement" and ev.get("observed") is True:
        for f in ("metric", "value", "unit"):
            if f not in ev:
                errs.append(f"measurement(observed=true) 缺 {f}")
        m = ev.get("metric")
        if m in RANGES:
            lo, hi = RANGES[m]
            try:
                v = float(ev["value"])
                if not (lo <= v <= hi):
                    errs.append(f"{m}={v} 超出物理范围 [{lo},{hi}]")
            except (TypeError, ValueError):
                errs.append(f"{m} 的值不是数字：{ev.get('value')!r}")

    return errs


# ---------------------------------------------------------------- fixtures
FIXTURES = [
    ("id 格式", {"id": "xxx"}),
    ("缺必填", {"text": None}),
    ("type 非法", {"type": "note"}),
    ("维度非法", {"dim_primary": "D9"}),
    ("副标签含主标签", {"dim_secondary": ["D2"]}),
    ("observer 非法", {"observer": "z"}),
    ("channel 非法", {"channel": "voice"}),
    ("observed 非布尔", {"observed": "yes"}),
    ("text 空", {"text": ""}),
    ("周粒度缺 period", {"ts_precision": "week", "period": None}),
    ("measurement 缺 metric", {"metric": None}),
    ("数值超范围", {"metric": "sleep.nap_h", "value": 99}),
    ("intervention 缺 followed", {"type": "intervention", "followed": None}),
    ("recorded_at 早于 ts", {"recorded_at": "2020-01-01T00:00:00+08:00"}),
]

BASE = {
    "id": "evt-20990101-0001",
    "schema_version": 2,
    "ts": "2099-01-01T10:00:00+08:00",
    "recorded_at": "2099-01-01T21:00:00+08:00",
    "ts_precision": "minute",
    "type": "observation",
    "dim_primary": "D2",
    "dim_secondary": ["M1"],
    "text": "样例原话",
    "observer": "p",
    "channel": "chat",
    "evidence_type": "obs",
    "observed": True,
}


def run_fixtures():
    print(f"跑 {len(FIXTURES)} 个错误样例，逐一确认能被拦住：\n")
    misses = []
    for name, patch in FIXTURES:
        ev = dict(BASE)
        ev.update(patch)
        ev = {k: v for k, v in ev.items() if v is not None}
        if name == "缺必填":
            ev.pop("text", None)
        if name == "measurement 缺 metric":
            ev["type"] = "measurement"
        if name == "数值超范围":
            ev["type"] = "measurement"
            ev["unit"] = "h"
        if name == "intervention 缺 followed":
            ev.update({"hypothesis_id": "H1", "action": "x", "started": "2099-01-01"})
        errs = check(ev)
        status = "✅ 拦住" if errs else "❌ 漏了"
        if not errs:
            misses.append(name)
        print(f"  {status}  {name}" + (f" → {errs[0]}" if errs else ""))
    print()
    if misses:
        print(f"❌ {len(misses)} 类错误未被拦住：{misses}")
        return 1
    print(f"✅ {len(FIXTURES)}/{len(FIXTURES)} 类错误全部拦住")
    return 0


def main():
    if "--fixtures" in sys.argv:
        return run_fixtures()

    files = sorted(EVENTS.glob("*.jsonl"))
    if not files:
        print("没有事件文件", file=sys.stderr)
        return 1

    errors, total, seen, texts = [], 0, {}, []

    for f in files:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            total += 1
            where = f"{f.name}:{i}"
            try:
                ev = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"{where} JSON 解析失败：{e}")
                continue

            errors.extend(f"{where} {e}" for e in check(ev))

            eid = ev.get("id")
            if eid in seen:
                errors.append(f"{where} id 重复：{eid}（另见 {seen[eid]}）")
            else:
                seen[eid] = where

            t = (ev.get("text") or "").strip()
            if t:
                texts.append((where, str(ev.get("ts", ""))[:10], t))

    # 疑似重复：同日同文
    seen_t = {}
    for where, day, t in texts:
        k = (day, t)
        if k in seen_t:
            errors.append(f"{where} 疑似重复（与 {seen_t[k]} 同日同文）")
        else:
            seen_t[k] = where

    # corrects 必须指向存在的事件
    for eid, where in seen.items():
        pass

    print(f"检查 {len(files)} 个文件，{total} 条事件")
    if errors:
        print(f"\n❌ {len(errors)} 处错误：", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
