"""
已收录队伍匹配 —— 根据识别出的对方 6 只宝可梦匹配 team_detail 中的队伍。

数据流：
    detect 出的 6 只 slug → champions_roster.form_id（升序逗号拼接）
    → team_detail.form_ids 精确匹配 → 按 Team.Date_Shared 降序（最多 5 个）
    → paste_info 逐只重建为完整 Pokemon（精确 EV/性格/道具/招式）。

注意：
    - 本模块只读 db/db.db（champions_roster / team_detail / Team 表）。
    - 匹配依赖 roster.form_id 与 team_detail.form_ids 一致；roster.form_id 由人工维护。
    - 匹配不到时返回空 teams，调用方退化为现有「对战数据组装队伍」逻辑。
"""

import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from pokepilot.common.pokemon_builder import PokemonBuilder
from pokepilot.tools.logger_util import setup_logger

logger = setup_logger(__name__)

_ROOT = Path(__file__).parent.parent.parent.parent
_env_db_path = os.environ.get("POKEPILOT_DB_PATH", "")
_DB_PATH = Path(_env_db_path) if _env_db_path else _ROOT / "db" / "db.db"

# 英文性格 → 前端展示用的箭头格式（与 parse_nature_string 的 "attack↑/speed↓" 对应）
_NATURE_ARROWS = {
    "hardy": "", "lonely": "attack↑/defense↓", "brave": "attack↑/speed↓",
    "adamant": "attack↑/sp_atk↓", "naughty": "attack↑/sp_def↓",
    "bold": "defense↑/attack↓", "docile": "", "relaxed": "defense↑/speed↓",
    "impish": "defense↑/sp_atk↓", "lax": "defense↑/sp_def↓",
    "timid": "speed↑/attack↓", "hasty": "speed↑/defense↓", "serious": "",
    "jolly": "speed↑/sp_atk↓", "naive": "speed↑/sp_def↓",
    "modest": "sp_atk↑/attack↓", "mild": "sp_atk↑/defense↓", "quiet": "sp_atk↑/speed↓",
    "bashful": "", "rash": "sp_atk↑/sp_def↓",
    "calm": "sp_def↑/attack↓", "gentle": "sp_def↑/defense↓", "sassy": "sp_def↑/speed↓",
    "careful": "sp_def↑/sp_atk↓", "quirky": "",
}

_STAT_KEYS = ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]


def _norm_key(s: str) -> str:
    """归一化字符串（小写、去非字母数字），用于名称/形态模糊匹配"""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _parse_date(s) -> Optional[datetime]:
    """解析 Date_Shared 日期，兼容 "2026-07-30" 与 "29th April 2026" 两种格式"""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    m = re.match(r"(\d{1,2})(?:st|nd|rd|th)\s+([A-Za-z]+)\s+(\d{4})", s)
    if m:
        try:
            return datetime.strptime(f"{m.group(2)} {m.group(1)} {m.group(3)}", "%B %d %Y")
        except ValueError:
            pass
    return None


def _load_roster_indexes() -> dict:
    """读 champions_roster，返回 slug→条目、form_id→条目 两个索引（含 form_id 字段）"""
    if not _DB_PATH.exists():
        raise RuntimeError(f"数据库不存在: {_DB_PATH}")

    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT form_id, id, name, form, slug, type1, type2, sprite "
            "FROM champions_roster").fetchall()
    finally:
        conn.close()

    by_slug, by_form_id = {}, {}
    for r in rows:
        types = [r["type1"]] if r["type1"] else []
        if r["type2"]:
            types.append(r["type2"])
        entry = {
            "form_id": r["form_id"],
            "id": int(r["id"]) if str(r["id"]).isdigit() else r["id"],
            "name": r["name"],
            "form": r["form"],
            "slug": r["slug"],
            "types": types,
            "sprite": r["sprite"],
        }
        by_slug[r["slug"]] = entry
        by_form_id[r["form_id"]] = entry
    return {"by_slug": by_slug, "by_form_id": by_form_id}


def form_ids_from_slugs(slugs: list) -> Optional[str]:
    """把识别出的 slug 列表转成升序逗号拼接的 form_id 字符串；任一未命中返回 None"""
    indexes = _load_roster_indexes()
    ids = []
    for slug in slugs:
        entry = indexes["by_slug"].get(slug)
        if not entry:
            logger.warning(f"匹配跳过：slug '{slug}' 不在 champions_roster")
            return None
        ids.append(entry["form_id"])
    ids.sort()
    return ",".join(ids)


def _resolve_by_name(name: str, by_slug: dict) -> Optional[dict]:
    """按英文名（含形态后缀）在 roster 中解析，作为 dex_form 未命中的回退"""
    target = _norm_key(name)
    for slug, entry in by_slug.items():
        if _norm_key(slug) == target:
            return entry

    candidates = [e for e in by_slug.values()
                  if _norm_key(e["name"]) == target
                  or target.startswith(_norm_key(e["name"]))]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # 多个候选时，用形态后缀进一步区分（如 "Maushold-Four" → form "family-of-four"）
    base_norm = _norm_key(candidates[0]["name"])
    suffix = target[len(base_norm):] if target.startswith(base_norm) else ""
    for e in candidates:
        if suffix and suffix in _norm_key(e.get("form") or ""):
            return e
    return None


def resolve_showdown_name(name: str, by_slug: dict) -> Optional[dict]:
    """把 Showdown 队伍文本里的宝可梦名（如 "Raichu-Alola"、"Maushold-Four"、
    "Floette-Eternal-Mega"）解析为 roster 条目。

    比 _resolve_by_name 更宽松：形态后缀做子串双向匹配（"floetteeternalmega"
    能对上 form "mega"），再按 token 重叠打分兜底；无法解析返回 None。
    """
    target = _norm_key(name)
    if not target:
        return None
    # 1) 精确 slug 匹配
    for slug, entry in by_slug.items():
        if _norm_key(slug) == target:
            return entry
    # 2) 物种名匹配（等于 或 目标名以物种名开头）
    base_matches = [e for e in by_slug.values()
                    if _norm_key(e["name"]) == target
                    or target.startswith(_norm_key(e["name"]))]
    if not base_matches:
        return None
    base_norm = _norm_key(base_matches[0]["name"])
    suffix = target[len(base_norm):] if target.startswith(base_norm) else ""
    # 3) 形态后缀子串匹配（双向：后缀含形态 或 形态含后缀）
    if suffix:
        for e in base_matches:
            fn = _norm_key(e.get("form") or "")
            if fn and (suffix == fn or suffix in fn or fn in suffix):
                return e
    # 4) 去掉同物种重复项后只剩一个 → 返回
    unique, seen = [], set()
    for e in base_matches:
        key = (e["form_id"].split("-", 1)[0], e.get("form") or "")
        if key not in seen:
            seen.add(key)
            unique.append(e)
    if len(unique) == 1:
        return unique[0]
    # 5) token 重叠打分兜底（如 "Maushold-Four" → 基础形态 family-of-four）
    tokens = set(re.findall(r"[a-z0-9]+", target))

    def _score(e):
        pool = _norm_key(e["name"]) + _norm_key(e.get("form") or "")
        return sum(1 for t in tokens if t in pool)

    return max(unique, key=_score)


def _build_pokemon_from_entry(entry: dict, builder: PokemonBuilder,
                              by_form_id: dict, by_slug: dict) -> Optional[dict]:
    """把 paste_info 的单只条目重建为完整 Pokemon.to_dict（我方队伍模式，精确 EV/性格）"""
    dex_form = entry.get("dex_form") or ""
    roster_entry = by_form_id.get(dex_form)
    if not roster_entry and entry.get("name"):
        roster_entry = _resolve_by_name(entry["name"], by_slug)
    if not roster_entry:
        logger.warning(f"匹配队伍构建跳过：无法解析 '{entry.get('name')}' (dex_form={dex_form})")
        return None

    slug = roster_entry["slug"]
    pokemon_info = builder.db.get_pokemon(slug) or {}
    base_stats = pokemon_info.get("base_stats", {}) or {}

    evs = entry.get("evs") or {}
    nature_arrow = _NATURE_ARROWS.get((entry.get("nature") or "").lower(), "")
    natures = builder.parse_nature_string(nature_arrow)

    # 用 base_stats + EV + 性格精确计算属性
    stats = {}
    for key in _STAT_KEYS:
        base = base_stats.get(key, 0)
        ev = evs.get(key, 0)
        if key == "hp":
            stats[key] = builder._calc_hp(base, ev)
        else:
            stats[key] = builder._calc_stat(base, ev, natures.get(key, 1.0))

    detect_data = {
        "id": roster_entry["id"],
        "name": roster_entry["name"],
        "slug": slug,
        "sprite_key": f"sprites/champions/{roster_entry['sprite']}" if roster_entry.get("sprite") else None,
        "types": roster_entry["types"],
    }
    moves_data = {
        "nickname": entry.get("name", roster_entry["name"]),
        "ability": entry.get("ability", ""),
        "held_item": entry.get("item", ""),
        "moves": entry.get("moves", []),
    }
    stats_data = {"stats": stats, "nature": nature_arrow}

    pokemon = builder.build_pokemon(
        detect_data=detect_data,
        moves_data=moves_data,
        stats_data=stats_data,
        language="en",
    )
    return pokemon.to_dict()


def _canon_form_ids(s: str) -> str:
    """把 form_ids 字符串规范化（拆开后升序重排），用于顺序无关的匹配。
    team_detail 里的 form_ids 是爬取时的队伍原始顺序（未排序），
    识别端按 detect 顺序拿到后排序，因此两侧都先排序再比较。"""
    parts = [p for p in (s or "").split(",") if p]
    parts.sort()
    return ",".join(parts)


def _query_teams(form_ids_str: str, limit: int = 5) -> list[dict]:
    """按 form_ids 匹配 team_detail（顺序无关），JOIN Team 取日期，按 Date_Shared 降序"""
    if not _DB_PATH.exists():
        raise RuntimeError(f"数据库不存在: {_DB_PATH}")

    canon = _canon_form_ids(form_ids_str)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        # 先只扫 form_ids 列（小），筛出命中队伍再取 paste_info（大）
        id_rows = conn.execute("SELECT team_id, form_ids FROM team_detail").fetchall()
        matched_ids = [r["team_id"] for r in id_rows
                       if _canon_form_ids(r["form_ids"] or "") == canon]
        rows = []
        if matched_ids:
            placeholders = ",".join("?" * len(matched_ids))
            rows = conn.execute(
                f"SELECT t.Team_ID, t.Date_Shared, t.Team_Description, d.paste_info "
                f"FROM team_detail d JOIN Team t ON t.Team_ID = d.team_id "
                f"WHERE d.team_id IN ({placeholders})", matched_ids).fetchall()
    finally:
        conn.close()

    teams = []
    for r in rows:
        date = _parse_date(r["Date_Shared"])
        try:
            paste = json.loads(r["paste_info"]) if r["paste_info"] else {}
        except (ValueError, TypeError):
            paste = {}
        teams.append({
            "team_id": r["Team_ID"],
            "date_shared": r["Date_Shared"] or "",
            "title": r["Team_Description"] or paste.get("title", ""),
            "paste": paste,
            "_date_key": (date is not None, date or datetime.min, r["Team_ID"] or ""),
        })

    # 有日期的排前面，日期新的排前面；无日期按 team_id 兜底
    teams.sort(key=lambda t: t["_date_key"], reverse=True)
    return teams[:limit]


def match_teams_from_slugs(slugs: list, limit: int = 5,
                           builder: Optional[PokemonBuilder] = None) -> dict:
    """
    核心入口：根据识别出的对方 6 只宝可梦 slug 匹配已收录队伍。

    Args:
        slugs: detect 出的 6 只 slug（顺序无关，函数内会升序排序）
        limit: 最多返回的匹配队伍数（默认 5，不含对战数据组装的第 0 个）
        builder: 可复用的 PokemonBuilder（默认新建）

    Returns:
        {"matched": bool, "form_ids": str|None, "teams": [
            {"team_id", "date_shared", "title", "team": {"trainer_name": "", "roster": [...]}}
        ]}
    """
    try:
        form_ids_str = form_ids_from_slugs(slugs)
    except Exception as e:
        logger.warning(f"匹配跳过（roster 读取失败）: {e}")
        return {"matched": False, "form_ids": None, "teams": []}
    if not form_ids_str:
        return {"matched": False, "form_ids": None, "teams": []}

    try:
        raw_teams = _query_teams(form_ids_str, limit)
    except Exception as e:
        logger.warning(f"匹配跳过（team_detail 查询失败）: {e}")
        return {"matched": False, "form_ids": form_ids_str, "teams": []}

    if not raw_teams:
        return {"matched": False, "form_ids": form_ids_str, "teams": []}

    indexes = _load_roster_indexes()
    builder = builder or PokemonBuilder()

    teams = []
    for raw in raw_teams:
        roster = []
        for entry in raw["paste"].get("pokemon", []):
            pokemon = _build_pokemon_from_entry(entry, builder,
                                                indexes["by_form_id"], indexes["by_slug"])
            if pokemon is not None:
                roster.append(pokemon)
        teams.append({
            "team_id": raw["team_id"],
            "date_shared": raw["date_shared"],
            "title": raw["title"],
            "team": {"trainer_name": "", "roster": roster},
        })
    return {"matched": len(teams) > 0, "form_ids": form_ids_str, "teams": teams}
