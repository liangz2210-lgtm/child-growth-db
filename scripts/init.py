#!/usr/bin/env python3
"""首次使用引导。幂等，可重复运行。

  python3 scripts/init.py

做三件事：
  1. 若还没有 profile/child-profile.md，从模板创建
  2. 检查生日是否已填（age 全靠它算）
  3. 跑一遍校验 → 派生 → 视图，并告诉你下一步做什么
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def ok(msg):
    print(f"  \033[32m✓\033[0m {msg}")


def warn(msg):
    print(f"  \033[33m!\033[0m {msg}")


def die(msg):
    print(f"  \033[31m✗\033[0m {msg}")


def ensure_profile():
    tpl = ROOT / "profile" / "child-profile.template.md"
    dst = ROOT / "profile" / "child-profile.md"
    if dst.exists():
        ok("profile/child-profile.md 已存在")
        return dst, False
    if not tpl.exists():
        die("找不到 profile/child-profile.template.md，仓库可能不完整")
        return None, False
    shutil.copy(tpl, dst)
    ok("已从模板创建 profile/child-profile.md")
    return dst, True


def read_birthday(p):
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("birthday:"):
            v = line.split(":", 1)[1].strip()
            if v and v.upper() not in {"YYYY-MM-DD", ""}:
                return v
    return None


def run(script):
    r = subprocess.run([PY, str(ROOT / "scripts" / script)], cwd=ROOT,
                       capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def main():
    print("\n=== Child Growth Database · 初始化 ===\n")

    # 1. profile
    prof, created = ensure_profile()
    if prof is None:
        return 1

    # 2. 生日
    bday = read_birthday(prof)
    if bday:
        ok(f"生日已设置：{bday}")
    else:
        warn("生日还没填 —— 填之前 age_days 会一直是空（不会猜，这是设计）")
        print(f"      编辑 {prof.relative_to(ROOT)} 的第 3 行：birthday: YYYY-MM-DD")

    # 3. 自检
    print("\n--- 自检 ---")
    code, out = run("validate.py")
    (ok if code == 0 else die)("校验：" + out.splitlines()[-1].strip() if out else "校验")

    code, out = run("derive.py")
    (ok if code == 0 else die)("派生：" + (out.splitlines()[0].strip() if out else "-"))

    code, out = run("view.py")
    (ok if code == 0 else die)("视图：" + (out.splitlines()[1].strip() if len(out.splitlines()) > 1 else "-"))

    # 4. 下一步
    print("\n--- 下一步 ---")
    lines = (ROOT / "derived" / "gaps.md")
    if lines.exists():
        body = lines.read_text(encoding="utf-8")
        tail = body.split("## 今日建议采集顺序")[-1].strip().splitlines()
        picks = [l for l in tail if l.strip() and not l.strip().startswith("按")][:3]
        if picks:
            print("  按缺口优先级，先补：")
            for p in picks:
                print("   ", p)
    print("""
  日常用法只有一条：说一句话，让 Agent 抽成事件追加到 events/YYYY-MM.jsonl。
  格式见 schema/event.json；写完跑 scripts/validate.py。

  如果你是让 AI Agent 接手，先让它读 AGENTS.md。
""")
    print("=== 完成 ===\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
