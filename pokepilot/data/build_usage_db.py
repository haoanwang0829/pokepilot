"""
从 data/raw/pokemon/*.json 构建 db/db.db 的使用率表（champions_usage + 6 张子表）。

原始数据：pokechamdb.com 每只宝可梦的全赛季×单双打快照（raw 文件含全部 variant）。
本脚本把全部 variant 平铺入库，名称在建表时用 pokecham_names.json 翻译成 en/zh
（复用 build_pokechamdb._resolve_name；未命中保留日文原文、name_zh 置空）。

表结构：
    champions_usage               每 (slug, season, format) 一行
    champions_usage_move/_item/_ability/_nature/_partner   子条目
        id, usage_id, rank, name_ja, name_en, name_zh, pct
    champions_usage_ev            EV 分布
        id, usage_id, rank, pct, hp, atk, def, sp_atk, sp_def, speed

用法:
    python -m pokepilot.data.build_usage_db            # 全量重建（upsert，幂等）
    python -m pokepilot.data.build_usage_db --wipe     # 先清空 usage 表再重建
    python -m pokepilot.data.build_usage_db --slug charizard
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

try:  # 控制台可能是 GBK，打印未命中日文名（含 ♥ 等）时避免 UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parent.parent.parent
_RAW_DIR = _ROOT / "data" / "raw" / "pokemon"
_DB_PATH = _ROOT / "db" / "db.db"

from .build_pokechamdb import _resolve_name  # noqa: E402

_TABLES = [
    "champions_usage",
    "champions_usage_move",
    "champions_usage_item",
    "champions_usage_ability",
    "champions_usage_nature",
    "champions_usage_partner",
    "champions_usage_ev",
]

_DDL = [
    """
    CREATE TABLE IF NOT EXISTS champions_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT NOT NULL,
        season TEXT NOT NULL,
        format TEXT NOT NULL,
        rank INTEGER,
        dex_no INTEGER,
        name_en TEXT,
        name_ja TEXT,
        name_zh TEXT,
        updated_at TEXT,
        UNIQUE(slug, season, format)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS champions_usage_move (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usage_id INTEGER NOT NULL REFERENCES champions_usage(id),
        rank INTEGER,
        name_ja TEXT,
        name_en TEXT,
        name_zh TEXT,
        pct REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS champions_usage_item (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usage_id INTEGER NOT NULL REFERENCES champions_usage(id),
        rank INTEGER,
        name_ja TEXT,
        name_en TEXT,
        name_zh TEXT,
        pct REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS champions_usage_ability (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usage_id INTEGER NOT NULL REFERENCES champions_usage(id),
        rank INTEGER,
        name_ja TEXT,
        name_en TEXT,
        name_zh TEXT,
        pct REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS champions_usage_nature (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usage_id INTEGER NOT NULL REFERENCES champions_usage(id),
        rank INTEGER,
        name_ja TEXT,
        name_en TEXT,
        name_zh TEXT,
        pct REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS champions_usage_partner (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usage_id INTEGER NOT NULL REFERENCES champions_usage(id),
        rank INTEGER,
        name_ja TEXT,
        name_en TEXT,
        name_zh TEXT,
        pct REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS champions_usage_ev (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usage_id INTEGER NOT NULL REFERENCES champions_usage(id),
        rank INTEGER,
        pct REAL,
        hp INTEGER,
        atk INTEGER,
        def INTEGER,
        sp_atk INTEGER,
        sp_def INTEGER,
        speed INTEGER
    )
    """,
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_usage_slug_season_format ON champions_usage(slug, season, format)",
    "CREATE INDEX IF NOT EXISTS idx_usage_move_uid ON champions_usage_move(usage_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_item_uid ON champions_usage_item(usage_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_ability_uid ON champions_usage_ability(usage_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_nature_uid ON champions_usage_nature(usage_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_partner_uid ON champions_usage_partner(usage_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_ev_uid ON champions_usage_ev(usage_id)",
]

_INSERT_USAGE = """
    INSERT INTO champions_usage (slug, season, format, rank, dex_no, name_en, name_ja, name_zh, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(slug, season, format) DO UPDATE SET
        rank=excluded.rank, dex_no=excluded.dex_no,
        name_en=excluded.name_en, name_ja=excluded.name_ja, name_zh=excluded.name_zh,
        updated_at=excluded.updated_at
"""

_CHILD_INSERT = {
    "champions_usage_move": "INSERT INTO champions_usage_move (usage_id, rank, name_ja, name_en, name_zh, pct) VALUES (?,?,?,?,?,?)",
    "champions_usage_item": "INSERT INTO champions_usage_item (usage_id, rank, name_ja, name_en, name_zh, pct) VALUES (?,?,?,?,?,?)",
    "champions_usage_ability": "INSERT INTO champions_usage_ability (usage_id, rank, name_ja, name_en, name_zh, pct) VALUES (?,?,?,?,?,?)",
    "champions_usage_nature": "INSERT INTO champions_usage_nature (usage_id, rank, name_ja, name_en, name_zh, pct) VALUES (?,?,?,?,?,?)",
    "champions_usage_partner": "INSERT INTO champions_usage_partner (usage_id, rank, name_ja, name_en, name_zh, pct) VALUES (?,?,?,?,?,?)",
}

_EV_INSERT = "INSERT INTO champions_usage_ev (usage_id, rank, pct, hp, atk, def, sp_atk, sp_def, speed) VALUES (?,?,?,?,?,?,?,?,?)"

_CHILD_FIELD = {
    "champions_usage_move": "moves",
    "champions_usage_item": "items",
    "champions_usage_ability": "abilities",
    "champions_usage_nature": "natures",
    "champions_usage_partner": "partners",
}


def _map_entries(kind: str, entries: list[dict]) -> list[tuple]:
    """子条目 → (rank, name_ja, name_en, name_zh, pct)，名称建表时翻译"""
    out = []
    for e in entries:
        en, ja, zh = _resolve_name(kind, e.get("name", ""))
        out.append((e.get("rank"), ja, en, zh, e.get("percentage", 0)))
    return out


def _map_evs(entries: list[dict]) -> list[tuple]:
    """EV 分布 → (rank, pct, hp, atk, def, sp_atk, sp_def, speed)"""
    return [
        (e.get("rank"), e.get("percentage", 0),
         e.get("hp", 0), e.get("atk", 0), e.get("def", 0),
         e.get("spAtk", 0), e.get("spDef", 0), e.get("speed", 0))
        for e in entries
    ]


def _ensure_schema(conn: sqlite3.Connection) -> None:
    for ddl in _DDL:
        conn.execute(ddl)
    for idx in _INDEXES:
        conn.execute(idx)


def _wipe(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM champions_usage_ev")
    conn.execute("DELETE FROM champions_usage_partner")
    conn.execute("DELETE FROM champions_usage_nature")
    conn.execute("DELETE FROM champions_usage_ability")
    conn.execute("DELETE FROM champions_usage_item")
    conn.execute("DELETE FROM champions_usage_move")
    conn.execute("DELETE FROM champions_usage")


def build(raw_dir: Path = _RAW_DIR, db_path: Path = _DB_PATH,
          slug_filter: str | None = None, season_filter: str | None = None,
          wipe: bool = False) -> dict:
    files = sorted(raw_dir.glob("*.json"))
    if not files:
        print(f"未找到原始数据: {raw_dir}/*.json")
        return {}

    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_schema(conn)
        if wipe:
            _wipe(conn)
            conn.commit()
            print("已清空 usage 表，开始重建")

        n_variants = 0
        n_files = 0
        unknown: dict[str, set[str]] = {}

        for fp in files:
            data = json.loads(fp.read_text(encoding="utf-8"))
            slug = data.get("slug", "")
            if slug_filter and slug_filter not in slug:
                continue

            variants = data.get("variants", {})
            with conn:  # 每文件一个事务
                for vk, v in variants.items():
                    season = v.get("seasonId")
                    fmt = v.get("format")
                    if not season or not fmt:
                        continue
                    if season_filter and season != season_filter:
                        continue

                    pokemon_ja = v.get("pokemonJa") or ""
                    name_en, name_ja, name_zh = _resolve_name("pokemon", pokemon_ja)
                    if name_en == pokemon_ja and name_zh == "":
                        unknown.setdefault("pokemon", set()).add(pokemon_ja)

                    conn.execute(_INSERT_USAGE, (
                        slug, season, fmt, v.get("rank"), v.get("dexNo"),
                        name_en, name_ja, name_zh, v.get("updatedAt"),
                    ))
                    usage_id = conn.execute(
                        "SELECT id FROM champions_usage WHERE slug=? AND season=? AND format=?",
                        (slug, season, fmt)).fetchone()[0]

                    # 子表：先删后插（幂等）
                    for table, kind in (("champions_usage_move", "moves"),
                                        ("champions_usage_item", "items"),
                                        ("champions_usage_ability", "abilities"),
                                        ("champions_usage_nature", "natures"),
                                        ("champions_usage_partner", "pokemon")):
                        conn.execute(f"DELETE FROM {table} WHERE usage_id=?", (usage_id,))
                        rows = _map_entries(kind, v.get(_CHILD_FIELD[table], []))
                        for r in rows:
                            # r = (rank, name_ja, name_en, name_zh, pct)；未命中：en==ja 且 zh 空
                            if r[2] == r[1] and r[3] == "":
                                unknown.setdefault(kind, set()).add(r[1])
                        conn.executemany(_CHILD_INSERT[table],
                                         [(usage_id, *r) for r in rows])

                    conn.execute("DELETE FROM champions_usage_ev WHERE usage_id=?", (usage_id,))
                    ev_rows = _map_evs(v.get("evs", []))
                    conn.executemany(_EV_INSERT, [(usage_id, *r) for r in ev_rows])

                    n_variants += 1
            n_files += 1

        print(f"完成: {n_files} 个文件, {n_variants} 个 variant 已写入 {db_path}")
        if unknown:
            for kind, names in sorted(unknown.items()):
                preview = ", ".join(sorted(names)[:20])
                print(f"  未命中映射 {kind} ({len(names)}): {preview}")
        return {"files": n_files, "variants": n_variants, "unknown": unknown}
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="从 data/raw/pokemon/*.json 构建使用率 DB")
    parser.add_argument("--slug", help="只处理匹配的 slug（子串匹配）")
    parser.add_argument("--season", help="只处理指定赛季（如 M-4, M-5）")
    parser.add_argument("--wipe", action="store_true", help="先清空 usage 表再重建")
    args = parser.parse_args()
    build(slug_filter=args.slug, season_filter=args.season, wipe=args.wipe)


if __name__ == "__main__":
    sys.exit(main())
