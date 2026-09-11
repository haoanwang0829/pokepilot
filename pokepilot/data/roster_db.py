"""
宝可梦参赛名单（roster）读侧访问层 —— 从 sqlite 读取，替代 champions_roster.json。

数据源: db/db.db 的 champions_roster 表
  form_id / id / name / form / slug / type1 / type2 / sprite / sprite_shiny / form_num

用法:
    from pokepilot.data.roster_db import RosterDB
    db = RosterDB()
    db.get_all()                     # → list[dict]，与旧 champions_roster.json 条目同构
    db.get_by_slug("charizard-mega-x")
    db.get_by_name("charizard")      # 按英文名取所有形态变体

注意:
    - 本模块是只读的，不做建表/播种/写库。表缺失或为空会直接抛错。
    - DB 路径可用环境变量 POKEPILOT_DB_PATH 覆盖（默认 <项目根>/db/db.db）。
"""

import os
import sqlite3
import threading
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
_env_db_path = os.environ.get("POKEPILOT_DB_PATH", "")
_DEFAULT_DB_PATH = Path(_env_db_path) if _env_db_path else _ROOT / "db" / "db.db"
_TABLE_NAME = "champions_roster"


class RosterDB:
    """从 sqlite 读取 champions_roster 的统一访问层（内存缓存）"""

    def __init__(self, db_path: Path = _DEFAULT_DB_PATH):
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._pokemon: list[dict] | None = None

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def _load(self) -> list[dict]:
        """从 DB 加载全部 roster，规范化为与旧 JSON 同构的 dict 列表"""
        if not self._db_path.exists():
            raise RuntimeError(f"数据库不存在: {self._db_path}（缺少 db/db.db，roster 数据从该库读取）")

        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            try:
                tables = [r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")]
                if _TABLE_NAME not in tables:
                    raise RuntimeError(
                        f"数据库缺少表 '{_TABLE_NAME}'（{self._db_path}），roster 数据无法读取")
                rows = conn.execute(
                    f"SELECT id, name, form, slug, type1, type2, sprite, sprite_shiny "
                    f"FROM {_TABLE_NAME}").fetchall()
            finally:
                conn.close()
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"读取 roster 数据库失败 ({self._db_path}): {e}")

        if not rows:
            raise RuntimeError(
                f"表 '{_TABLE_NAME}' 为空（{self._db_path}），roster 数据无法读取")

        pokemon = []
        for r in rows:
            types = [r["type1"]] if r["type1"] else []
            if r["type2"]:
                types.append(r["type2"])
            pokemon.append({
                "id": int(r["id"]) if str(r["id"]).isdigit() else r["id"],
                "name": r["name"],
                "form": r["form"],
                "slug": r["slug"],
                "types": types,
                "sprite": r["sprite"],
                "sprite_shiny": r["sprite_shiny"],
            })
        return pokemon

    def get_all(self) -> list[dict]:
        """返回全部 roster 条目（与旧 champions_roster.json 的 pokemon 数组同构）"""
        with self._lock:
            if self._pokemon is None:
                self._pokemon = self._load()
            return list(self._pokemon)

    def get_by_slug(self, slug: str) -> dict | None:
        """按 slug 查询单条，查不到返回 None"""
        for poke in self.get_all():
            if poke["slug"] == slug:
                return poke
        return None

    def get_by_name(self, name: str) -> list[dict]:
        """按英文名字查询所有形态变体"""
        return [p for p in self.get_all() if p["name"] == name]


# --------------------------------------------------------------------------
# 全局单例（避免每个消费方各自连库）
# --------------------------------------------------------------------------

_instance: RosterDB | None = None
_lock = threading.Lock()


def get_roster_db() -> RosterDB:
    """线程安全的 RosterDB 全局单例获取"""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = RosterDB()
    return _instance
