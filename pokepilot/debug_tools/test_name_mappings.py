"""中文名 → 英文名映射 回归测试 —— 只读数据库，不修改任何数据。

用法：
    python -m pokepilot.debug_tools.test_name_mappings

背景（2026-09-21 修复）：
1. 23 个冠军道具的 name_e 为 NULL → PokeDB 用空 slug 建键、后续同类行被静默丢弃，
   item_zh_to_en() 只能原样返回中文名，最终以中文道具名落进队伍 JSON，
   前端伤害引擎认不出（`toID('凸凸头盔')` 会剥成空串）→ 伤害静默算不出甚至抛异常。
2. 中文映射表用**原始**中文名建键，而查询侧做 NFKC 规范化，两侧不一致，
   导致含全角字符的中文名（『喷火龙进化石Ｘ』『纹理２』『Ｖ热焰』『ＡＲ系统』）
   永远查不到英文名，同样落中文原名。

覆盖：
1. 所有 in_champions='Y' 的道具都有非空 name_e
2. get_all_items() 条目数与冠军道具数一致（不含空键垃圾条目）
3. 冠军道具的中文名全都能反查回英文 slug（item_zh_to_en 不返回中文）
4. build_held_item 落盘的是规范英文名（name 英文 / name_zh 中文，不再是反的）
5. 含全角字符的中文名（items / moves / abilities）也能反查英文
"""

import sqlite3
import unicodedata

from pokepilot.common.pokemon_builder import PokemonBuilder
from pokepilot.data.pokedb import _DEFAULT_DB_PATH, _slugify, get_pokedb

_ZH_RE = lambda s: any("\u4e00" <= ch <= "\u9fff" for ch in (s or ""))
_has_wide = lambda s: bool(s) and unicodedata.normalize("NFKC", s) != s


def main():
    db = get_pokedb()
    failures = []

    def check(name, cond, extra=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"   <- {extra}"))
        if not cond:
            failures.append(name)

    conn = sqlite3.connect(_DEFAULT_DB_PATH)
    conn.row_factory = sqlite3.Row
    champions = conn.execute(
        "SELECT id, name, name_e FROM items WHERE in_champions='Y'").fetchall()
    all_moves = conn.execute("SELECT name, name_e FROM moves").fetchall()
    all_abilities = conn.execute("SELECT name, name_e FROM abilities").fetchall()

    print("== 1. 冠军道具 name_e 完整性 ==")
    blank = [f"{r['name']}(id={r['id']})" for r in champions if not (r["name_e"] or "").strip()]
    check(f"{len(champions)} 个冠军道具均有 name_e", not blank, "缺: " + "、".join(blank))

    print("== 2. get_all_items() 条目数 / 键 ==")
    items = db.get_all_items()
    check("无空 slug 键", "" not in items, "存在空键条目，说明有 name_e 缺失")
    check(f"条目数 {len(items)} == 冠军道具数 {len(champions)}",
          len(items) == len(champions), f"{len(items)} != {len(champions)}")
    check("每条都有非空 name", all(v.get("name") for v in items.values()))

    print("== 3. 冠军道具中文名 → 英文 slug 全覆盖 ==")
    bad = []
    for r in champions:
        got = db.item_zh_to_en(r["name"])
        if _ZH_RE(got) or got != _slugify(r["name_e"]):
            bad.append(f"{r['name']} -> {got!r}（期望 {_slugify(r['name_e'])!r}）")
    check("全部中文名都能反查英文 slug", not bad, "；".join(bad[:6]))
    check("凸凸头盔 → rocky-helmet", db.item_zh_to_en("凸凸头盔") == "rocky-helmet")

    print("== 4. build_held_item 落盘形状 ==")
    # build_held_item 只用到 self.db，跳过 PokemonBuilder 的重量级 __init__（roster/usage/相克表）
    builder = PokemonBuilder.__new__(PokemonBuilder)
    builder.db = db
    hi = builder.build_held_item(db.item_zh_to_en("凸凸头盔"))
    check("name 为规范英文名", hi.name == "Rocky Helmet", repr(hi.name))
    check("name_zh 为中文名", hi.name_zh == "凸凸头盔", repr(hi.name_zh))

    print("== 5. 含全角字符的中文名往返 ==")
    wide_items = [r for r in champions if _has_wide(r["name"])]
    wide_moves = [r for r in all_moves if _has_wide(r["name"])]
    wide_abilities = [r for r in all_abilities if _has_wide(r["name"])]
    print(f"  （items {len(wide_items)} / moves {len(wide_moves)} / abilities {len(wide_abilities)}）")
    for label, rows, translate in (
        ("道具", wide_items, db.item_zh_to_en),
        ("招式", wide_moves, db.move_zh_to_en),
        ("特性", wide_abilities, db.ability_zh_to_en),
    ):
        mism = [f"{r['name']} -> {translate(r['name'])!r}（期望 {_slugify(r['name_e'])!r}）"
                for r in rows if translate(r["name"]) != _slugify(r["name_e"])]
        check(f"全角{label}名能反查英文 slug", not mism, "；".join(mism[:4]))

    conn.close()
    print()
    if failures:
        print(f"共 {len(failures)} 项失败：" + "；".join(failures))
        return 1
    print("全部通过 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
