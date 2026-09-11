"""
UsageDB 访问层 —— 从 sqlite (db/db.db) 读取宝可梦各赛季/格式的使用率数据。

数据源: db/db.db 的 champions_usage + champions_usage_{move,item,ability,nature,partner,ev} 表
（由 pokepilot/data/build_usage_db.py 从 data/raw/pokemon/*.json 构建，建表时已翻译 en/zh）。

输出形状与旧 data/pokechamdb_cache.json 条目同构，消费方按字段名取值即可：
    {
        "slug": "charizard", "rank": 8,
        "name_en": "Charizard", "name_ja": "リザードン", "name_zh": "喷火龙",
        "moves":     [{"name": "Protect", "name_j": "まもる", "name_zh": "守住", "pct": 92.4}, ...],
        "items":     [...], "abilities": [...], "natures": [...],
        "teammates": [...],
        "evs":       [{"hp": 2, "atk": 0, "def": 0, "spA": 32, "spD": 0, "spe": 32, "pct": 27.5}, ...],
    }

用法:
    from pokepilot.data.usage_db import get_usage_db
    db = get_usage_db()
    db.get_all()                            # 默认 M-4 / double → {slug: entry}
    db.get_all(season="M-2", format="single")
    db.get_pokemon_usage("charizard")       # → entry | None
    db.get_seasons(); db.get_formats()      # 可选赛季/格式清单

注意:
    - 本模块只读，不建表/写库；表缺失直接抛 RuntimeError（先跑 build_usage_db.py）。
    - 默认生效赛季/格式由 DEFAULT_SEASON / DEFAULT_FORMAT 常量控制（暂固定，后续可调）。
    - 与旧 pokechamdb_cache.json 无回退：表在但某 (season, format) 无数据时返回空 dict。
"""

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
_env_db_path = os.environ.get("POKEPILOT_DB_PATH", "")
_DEFAULT_DB_PATH = Path(_env_db_path) if _env_db_path else _ROOT / "db" / "db.db"
_LATEST_SEASON_PATH = _ROOT / "data" / "raw" / "latest_season.json"

# 缓存 TTL（秒）：DB 外部改动后，最多 _CACHE_TTL 秒内自动重新读库
_CACHE_TTL = 300.0

# 子表 → 输出字段名（partner 表在输出时叫 teammates，与旧缓存一致）
_CHILD_SPECS = [
    ("champions_usage_move", "moves"),
    ("champions_usage_item", "items"),
    ("champions_usage_ability", "abilities"),
    ("champions_usage_nature", "natures"),
    ("champions_usage_partner", "teammates"),
]


def _read_latest_season() -> str:
    """从 data/raw/latest_season.json 读取最新赛季 ID，不存在则返回 M-4。"""
    if _LATEST_SEASON_PATH.exists():
        try:
            data = json.loads(_LATEST_SEASON_PATH.read_text(encoding="utf-8"))
            return data.get("season", "M-4")
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            pass
    return "M-4"


class UsageDB:
    """从 sqlite 读取各赛季/格式使用率数据的访问层（惰性加载 + TTL 缓存）"""

    DEFAULT_SEASON = _read_latest_season()
    DEFAULT_FORMAT = "double"

    def __init__(self, db_path: Path = _DEFAULT_DB_PATH, ttl: float = _CACHE_TTL):
        self._db_path = Path(db_path)
        self._ttl = ttl
        self._lock = threading.Lock()
        self._cache: dict[tuple, tuple[float, object]] = {}

    # ------------------------------------------------------------------
    # 缓存
    # ------------------------------------------------------------------

    def _cached(self, key: tuple, loader):
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None and time.monotonic() - hit[0] < self._ttl:
                return hit[1]
        value = loader()
        with self._lock:
            self._cache[key] = (time.monotonic(), value)
        return value

    def clear_cache(self) -> None:
        """清空全部缓存，下次访问立即重新读库"""
        with self._lock:
            self._cache.clear()

    def refresh(self) -> None:
        """同 clear_cache，供外部 DB 数据更新后手动刷新"""
        self.clear_cache()

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------

    def _open(self) -> sqlite3.Connection:
        if not self._db_path.exists():
            raise RuntimeError(
                f"数据库不存在: {self._db_path}（缺少 db/db.db，使用率数据从该库读取）")
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def _load(self, season: str, fmt: str) -> dict:
        """读取某 (season, format) 的全部使用率数据 → {slug: entry}"""
        conn = self._open()
        try:
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='champions_usage'"
            ).fetchone()
            if not exists:
                raise RuntimeError(
                    "champions_usage 表不存在（先运行 python -m pokepilot.data.build_usage_db 建库）")

            rows = conn.execute(
                "SELECT id, slug, rank, dex_no, name_en, name_ja, name_zh "
                "FROM champions_usage WHERE season=? AND format=? ORDER BY rank",
                (season, fmt)).fetchall()
            if not rows:
                return {}
            ids = [r["id"] for r in rows]
            placeholders = ",".join("?" * len(ids))

            children: dict[str, dict[int, list]] = {}
            for table, field in _CHILD_SPECS:
                cr = conn.execute(
                    f"SELECT usage_id, rank, name_ja, name_en, name_zh, pct "
                    f"FROM {table} WHERE usage_id IN ({placeholders}) ORDER BY rank",
                    ids).fetchall()
                agg: dict[int, list] = {}
                for row in cr:
                    agg.setdefault(row["usage_id"], []).append({
                        "name": row["name_en"],
                        "name_j": row["name_ja"],
                        "name_zh": row["name_zh"],
                        "pct": row["pct"],
                    })
                children[field] = agg

            ev_rows = conn.execute(
                f"SELECT usage_id, rank, pct, hp, atk, def, sp_atk, sp_def, speed "
                f"FROM champions_usage_ev WHERE usage_id IN ({placeholders}) ORDER BY rank",
                ids).fetchall()
            ev_agg: dict[int, list] = {}
            for row in ev_rows:
                ev_agg.setdefault(row["usage_id"], []).append({
                    "hp": row["hp"], "atk": row["atk"], "def": row["def"],
                    "spA": row["sp_atk"], "spD": row["sp_def"], "spe": row["speed"],
                    "pct": row["pct"],
                })
        finally:
            conn.close()

        result: dict[str, dict] = {}
        for r in rows:
            result[r["slug"]] = {
                "slug": r["slug"],
                "rank": r["rank"],
                "name_en": r["name_en"],
                "name_ja": r["name_ja"],
                "name_zh": r["name_zh"],
                "moves": children["moves"].get(r["id"], []),
                "items": children["items"].get(r["id"], []),
                "abilities": children["abilities"].get(r["id"], []),
                "natures": children["natures"].get(r["id"], []),
                "teammates": children["teammates"].get(r["id"], []),
                "evs": ev_agg.get(r["id"], []),
            }
        return result

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    def get_all(self, season: str | None = None, format: str | None = None) -> dict:
        """全部使用率数据 → {slug: entry}。season/format 缺省用 DEFAULT_SEASON/DEFAULT_FORMAT。"""
        season = season or self.DEFAULT_SEASON
        fmt = format or self.DEFAULT_FORMAT
        return self._cached((season, fmt), lambda: self._load(season, fmt))

    def get_pokemon_usage(self, slug: str, season: str | None = None,
                          format: str | None = None) -> dict | None:
        """按 slug 查单只使用率数据，查不到返回 None"""
        return self.get_all(season, format).get(slug)

    def get_seasons(self) -> list[str]:
        """可选赛季清单（如 ['M-1','M-2','M-3','M-4']）"""
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT DISTINCT season FROM champions_usage ORDER BY season").fetchall()
        finally:
            conn.close()
        return [r["season"] for r in rows]

    def get_formats(self) -> list[str]:
        """可选格式清单（如 ['double','single']）"""
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT DISTINCT format FROM champions_usage ORDER BY format").fetchall()
        finally:
            conn.close()
        return [r["format"] for r in rows]


# --------------------------------------------------------------------------
# 全局单例（避免每个消费方各自连库）
# --------------------------------------------------------------------------

_instance: UsageDB | None = None
_lock = threading.Lock()


def get_usage_db() -> UsageDB:
    """线程安全的 UsageDB 全局单例获取"""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = UsageDB()
    return _instance


if __name__ == "__main__":
    import json
    db = get_usage_db()
    print("可用赛季:", db.get_seasons())
    print("可用格式:", db.get_formats())
    all_data = db.get_all()
    print(f"默认赛季/格式 {db.DEFAULT_SEASON}/{db.DEFAULT_FORMAT} 共 {len(all_data)} 只")
    e = db.get_pokemon_usage("charizard")
    print("charizard:", json.dumps(e, ensure_ascii=False) if e else None)
