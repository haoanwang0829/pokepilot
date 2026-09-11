"""
校验 champions_roster 表 form_id 与 team_detail 表 form_ids 的一致性。

背景:
    team_detail.form_ids 来自 pokepast.es 的图片 URL（如 "0149-0" = 图鉴号-形态号），
    默认视为准确；champions_roster.form_id 入库时按游戏实际收录形态紧凑编号，
    可能与 pokepast 的形态序号不一致。

检查项:
    1. dex 校验 —— roster 每条 form_id 的图鉴号部分 vs team_detail 同名宝可梦的图鉴号
    2. 缺失校验 —— team_detail 引用了、但 roster 中不存在的 form_id（含同名 dex 的 roster 条目）
    3. 同串校验 —— 两边共有的 form_id 是否指向同一只宝可梦（同 id 不同宝）

输出: 错误项一律展示 roster 表中的 form_id。

用法:
    python -m pokepilot.debug_tools.check_roster_form_ids
    python -m pokepilot.debug_tools.check_roster_form_ids --db path/to/db.db
"""

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB_PATH = _ROOT / "db" / "db.db"

# 昵称污染: "taffy (mawile-mega)" → "mawile-mega"
_NICKNAME_RE = re.compile(r"^.*\(([^)]+)\)$")

# roster 的 form 命名与 pokepast 名称的差异，归一后用于同串校验
_NORM_RULES = [
    ("-variety", ""),      # gourgeist-small-variety ↔ gourgeist-small
    ("-pattern", ""),      # vivillon-fancy-pattern ↔ vivillon-fancy
    ("-breed", ""),        # tauros-paldea-blaze-breed ↔ tauros-paldea-blaze
    ("-flower", ""),       # floette-eternal-flower ↔ floette-eternal
    ("family-of-three", "three"),
    ("family-of-four", "four"),
    ("female", "f"),       # basculegion-female ↔ basculegion-f
]


def _norm_name(raw: str) -> str:
    """去掉昵称污染，取真正的宝可梦名（小写）。"""
    s = (raw or "").strip().lower()
    m = _NICKNAME_RE.match(s)
    if m:
        s = m.group(1).strip().lower()
    return s


def _norm_key(s: str) -> str:
    """归一化形态名，用于同一 form_id 是否指向同一只宝可梦的判断。"""
    s = _norm_name(s)
    for old, new in _NORM_RULES:
        s = s.replace(old, new)
    return s.strip("-")


def _load_roster(conn: sqlite3.Connection) -> list[dict]:
    return [
        {
            "form_id": r["form_id"],
            "id": r["id"],
            "name": r["name"],
            "form": r["form"],
            "slug": r["slug"],
        }
        for r in conn.execute(
            "SELECT form_id, id, name, form, slug FROM champions_roster"
        )
    ]


def _load_team_detail(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """返回 [(form_id, pokemon_name), ...]，跳过 dex 为 0 的占位条目。"""
    out = []
    for (paste_info,) in conn.execute(
        "SELECT paste_info FROM team_detail WHERE paste_info IS NOT NULL"
    ):
        try:
            data = json.loads(paste_info)
        except json.JSONDecodeError:
            continue
        for p in data.get("pokemon", []):
            dex_form = (p.get("dex_form") or "").strip()
            name = (p.get("name") or "").strip()
            if not dex_form or not name or "-" not in dex_form:
                continue
            dex = dex_form.split("-", 1)[0]
            if dex == "0000":  # pokepast dex 0 占位，非有效图鉴号
                continue
            out.append((dex_form, name))
    return out


def run_check(db_path: Path = _DEFAULT_DB_PATH) -> dict:
    """执行三项校验，返回 {dex_errors, missing_form_ids, conflict_form_ids}。"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    roster = _load_roster(conn)
    td = _load_team_detail(conn)

    # ── ground truth: team_detail ────────────────────────────────────────
    species_dex: dict[str, set] = defaultdict(set)   # 物种基础名 → dex
    name_dex: dict[str, set] = defaultdict(set)      # 完整归一名 → dex
    td_form_ids: dict[str, Counter] = defaultdict(Counter)  # form_id → 名字计数
    for dex_form, name in td:
        nm = _norm_name(name)
        species_dex[nm.split("-")[0]].add(dex_form.split("-", 1)[0])
        name_dex[nm].add(dex_form.split("-", 1)[0])
        td_form_ids[dex_form][nm] += 1

    roster_form_ids = {r["form_id"] for r in roster}
    roster_by_dex: dict[str, list[str]] = defaultdict(list)
    for r in roster:
        dex_part = r["form_id"].split("-")[0]
        roster_by_dex[dex_part].append(r["form_id"])

    # ── 1. dex 校验: roster form_id 图鉴号 vs team_detail ────────────────
    dex_errors = []
    for r in roster:
        base_name = (r["name"] or "").strip().lower()
        expected = species_dex.get(base_name)
        if not expected:
            continue  # team_detail 从未收录该物种，无法验证
        dex_part = r["form_id"].split("-")[0]
        if dex_part not in expected:
            dex_errors.append({
                "form_id": r["form_id"],
                "name": r["name"],
                "form": r["form"],
                "slug": r["slug"],
                "expected_dex": sorted(expected),
            })

    # ── 2. 缺失校验: team_detail 有、roster 无 ─────────────────────────────
    missing_form_ids = []
    for dex_form in sorted(td_form_ids):
        if dex_form in roster_form_ids:
            continue
        dex_part = dex_form.split("-")[0]
        missing_form_ids.append({
            "form_id": dex_form,
            "names": sorted(td_form_ids[dex_form]),
            "count": sum(td_form_ids[dex_form].values()),
            "roster_same_dex": sorted(roster_by_dex.get(dex_part, [])),
        })

    # ── 3. 同串校验: 两边共有的 form_id 是否指向同一只宝可梦 ───────────────
    conflict_form_ids = []
    roster_by_form_id: dict[str, list[str]] = defaultdict(list)
    for r in roster:
        roster_by_form_id[r["form_id"]].append(r["slug"])
    for dex_form in sorted(set(td_form_ids) & set(roster_form_ids)):
        roster_slugs = roster_by_form_id[dex_form]
        td_names = list(td_form_ids[dex_form])
        roster_keys = {_norm_key(s) for s in roster_slugs}
        td_keys = {_norm_key(n) for n in td_names}
        if not (roster_keys & td_keys):
            conflict_form_ids.append({
                "form_id": dex_form,
                "roster_slugs": sorted(roster_slugs),
                "team_names": sorted(td_names),
            })

    conn.close()
    return {
        "total_roster": len(roster),
        "total_team_detail": len(td),
        "dex_errors": dex_errors,
        "missing_form_ids": missing_form_ids,
        "conflict_form_ids": conflict_form_ids,
    }


def main():
    parser = argparse.ArgumentParser(description="校验 champions_roster.form_id 与 team_detail.form_ids")
    parser.add_argument("--db", default=str(_DEFAULT_DB_PATH), help="sqlite 路径（默认 db/db.db）")
    args = parser.parse_args()

    rep = run_check(Path(args.db))

    print(f"roster 行数: {rep['total_roster']}   team_detail 有效条目: {rep['total_team_detail']}")

    print("\n== 1. dex 校验（roster form_id 图鉴号 vs team_detail）==")
    if rep["dex_errors"]:
        for e in rep["dex_errors"]:
            print(f"  form_id={e['form_id']}  name={e['name']}  form={e['form']}  "
                  f"slug={e['slug']}  team_detail期望dex={e['expected_dex']}")
    else:
        print("  通过（0 错误）")

    print("\n== 2. 缺失校验（team_detail 有、roster 无的 form_id）==")
    if rep["missing_form_ids"]:
        for m in rep["missing_form_ids"]:
            print(f"  form_id={m['form_id']}  names={m['names']}  x{m['count']}")
            print(f"       roster 同 dex 条目: {m['roster_same_dex']}")
    else:
        print("  通过（0 缺失）")

    print("\n== 3. 同串校验（两边共有 form_id 指向不一致）==")
    if rep["conflict_form_ids"]:
        for c in rep["conflict_form_ids"]:
            print(f"  form_id={c['form_id']}")
            print(f"       roster:      {c['roster_slugs']}")
            print(f"       team_detail: {c['team_names']}")
    else:
        print("  通过（0 冲突）")

    n_err = len(rep["dex_errors"]) + len(rep["missing_form_ids"]) + len(rep["conflict_form_ids"])
    print(f"\n总计问题项: {n_err}")


if __name__ == "__main__":
    main()
