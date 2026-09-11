"""
采集卡视频预览服务器 —— 用浏览器 getUserMedia 打开摄像头 + API 服务

用法：
    python -m pokepilot.ui.ui_server --port 8765
"""

import argparse
import io
import json
import re
import shutil
import sqlite3
import threading
from datetime import datetime
from math import floor
from pathlib import Path
from flask import Flask, send_file, request, jsonify, send_from_directory
from flask_cors import CORS
from PIL import Image
from pokepilot.detect_team.my_team.parse_team import parse_team_init
from pokepilot.detect_team.opponent_team.detect_opponents import (
    detect_opponents_team, detect_opponents_team_with_cards)
from pokepilot.detect_team.opponent_team.team_matcher import (
    match_teams_from_slugs, _load_roster_indexes,
    _parse_date as _parse_team_date, resolve_showdown_name)
from pokepilot.data.build_team_detail import _parse_pre_text as _parse_showdown_pre
from pokepilot.common.pokemon_detect import get_detector as _get_detector
from pokepilot.common.pokemon_builder import PokemonBuilder
from pokepilot.common.pokemon import Pokemon
from pokepilot.data.roster_db import get_roster_db
from pokepilot.data.pokedb import get_pokedb
from pokepilot.data.usage_db import get_usage_db

_ROOT = Path(__file__).parent
PROJECT_ROOT = _ROOT.parent.parent
POKEPILOT_DIR = _ROOT.parent  # pokepilot/ 目录
CONFIG_DIR = POKEPILOT_DIR / "config"
SCREENSHOTS_DIR = PROJECT_ROOT / "screenshots" / "team"
OPP_SCREENSHOTS_DIR = PROJECT_ROOT / "screenshots" / "opp_team"
SPRITES_DIR = PROJECT_ROOT / "sprites"
TEAM_DIR = PROJECT_ROOT / "data" / "my_team"
OPP_TEAM_DIR = PROJECT_ROOT / "data" / "opp_team"
DB_PATH = PROJECT_ROOT / "db" / "db.db"

_NATURE_ZH = {
    "Hardy": "勤奋", "Lonely": "寂寞", "Brave": "勇敢", "Adamant": "固执",
    "Naughty": "调皮", "Bold": "大胆", "Docile": "坦率", "Relaxed": "悠闲",
    "Impish": "淘气", "Lax": "乐天", "Timid": "胆小", "Hasty": "急躁",
    "Serious": "认真", "Jolly": "爽朗", "Naive": "天真", "Modest": "内敛",
    "Mild": "慢吞吞", "Quiet": "冷静", "Bashful": "害羞", "Rash": "马虎",
    "Calm": "温和", "Gentle": "温顺", "Sassy": "自大", "Careful": "慎重",
    "Quirky": "浮躁",
}

_DAMAGE_LEVEL = 50


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_matched_teams_payload(match_result: dict) -> tuple:
    """把 match_teams_from_slugs 的结果转成 API 用的 (form_ids, matched_teams)"""
    matched_teams = []
    for mt in match_result.get("teams", []):
        matched_teams.append({
            "team_id": mt.get("team_id", ""),
            "date_shared": mt.get("date_shared", ""),
            "title": mt.get("title", ""),
            "team": {
                "trainer_name": "",
                "roster": [p if isinstance(p, dict) else p.to_dict()
                           for p in mt.get("team", {}).get("roster", [])],
            },
        })
    return match_result.get("form_ids"), matched_teams


# --------------------------------------------------------------------------
# 队伍库（/team 页面）数据访问
# --------------------------------------------------------------------------

def _slugify_name(s: str) -> str:
    """招式/道具/特性名 → 小写连字符 slug（与 PokeDB 键一致）"""
    return (s or "").lower().replace(" ", "-").replace("'", "").replace(".", "").replace("é", "e")


def _norm_name(s: str) -> str:
    """归一化名称（小写、去非字母数字），用于物种级匹配"""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _resolve_species_dexes(name: str, roster_rows: list, pokedb) -> list[int]:
    """把中文/英文宝可梦名解析为该物种的全部 dex 号；解析不到返回 None。

    roster_rows: by_slug 索引的 values（含 name/id），name 为英文小写物种名。
    """
    raw = (name or "").strip()
    if not raw:
        return None
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in raw)
    en = pokedb.name_zh_to_en(raw) if has_cjk else raw
    target = _norm_name(en)
    if not target:
        return None
    dexes = sorted({int(r["id"]) for r in roster_rows if _norm_name(r["name"]) == target})
    if not dexes:
        # 英文前缀兜底（如 "drag" → Dragonite）
        dexes = sorted({int(r["id"]) for r in roster_rows
                        if _norm_name(r["name"]).startswith(target)})
    return dexes or None


def _dexes_in_form_ids(form_ids: str) -> set:
    """把 form_ids（"0149-0,0478-0,..."）拆成队伍含有的 dex 号集合（int）"""
    out = set()
    if not form_ids:
        return out
    for part in form_ids.split(","):
        if "-" in part:
            try:
                out.add(int(part.split("-", 1)[0]))
            except ValueError:
                continue
    return out


def _team_date_key(date_str: str, team_id: str):
    """按分享时间降序的排序键：有日期的排前，日期新的排前，无日期按 team_id 兜底"""
    d = _parse_team_date(date_str)
    return (d is not None, d or datetime.min, team_id or "")


def _build_team_library_item(row, roster_by_form: dict, name_zh_map: dict,
                             move_map: dict, item_map: dict, ability_map: dict) -> dict:
    """把 Team+team_detail 的一行组装成前端展示用的队伍条目"""
    paste = {}
    if row["paste_info"]:
        try:
            paste = json.loads(row["paste_info"])
        except (ValueError, TypeError):
            paste = {}

    def _zh(mp, raw):
        md = mp.get(_slugify_name(raw)) or {}
        return md.get("name_zh") or raw

    roster = []
    for p in paste.get("pokemon", []):
        re_ = roster_by_form.get(p.get("dex_form") or "")
        if not re_:
            continue
        slug = re_["slug"]
        moves = [{
            "name": m,
            "name_zh": _zh(move_map, m),
            "type": (move_map.get(_slugify_name(m)) or {}).get("type", "Normal"),
        } for m in p.get("moves", [])]
        roster.append({
            "name": p.get("name", re_["name"]),
            "name_zh": name_zh_map.get(slug) or slug,
            "slug": slug,
            "form": re_.get("form") or "",
            "sprite": f"sprites/champions/{re_['sprite']}" if re_.get("sprite") else "",
            "types": re_.get("types", []),
            "item": p.get("item", ""),
            "item_zh": _zh(item_map, p.get("item", "")),
            "ability": p.get("ability", ""),
            "ability_zh": _zh(ability_map, p.get("ability", "")),
            "nature": p.get("nature", ""),
            "moves": moves,
            "evs": p.get("evs", {}),
        })

    return {
        "team_id": row["Team_ID"] or "",
        "title": row["Team_Description"] or paste.get("title", ""),
        "replica_code": row["Replica_Code"] or "",
        "date_shared": row["Date_Shared"] or "",
        "owner": row["Owner"] or "",
        "event": row["Tournament_Event"] or "",
        "rank": row["Rank"] or "",
        "link": row["Link_to_Source"] or "",
        "roster": roster,
    }


def _query_team_library(filters: list[str], page: int, page_size: int) -> dict:
    """队伍库筛选：宝可梦名（物种级）AND 过滤，按 Date_Shared 降序分页。

    filters: 非空的宝可梦名（中文/英文），每一项都需被队伍包含。
    """
    pokedb = get_pokedb()
    indexes = _load_roster_indexes()
    roster_rows = list(indexes["by_slug"].values())

    # 名称 → 物种 dex 集合；解析不到直接报错，避免静默忽略输入
    resolved, unresolved = [], []
    for f in filters:
        dexes = _resolve_species_dexes(f, roster_rows, pokedb)
        if not dexes:
            unresolved.append(f)
        else:
            resolved.append(set(dexes))
    if unresolved:
        return {"success": False, "error": "未找到宝可梦: " + "、".join(unresolved)}

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT t.Team_ID, t.Team_Description, t.Replica_Code, t.Date_Shared,"
            "       t.Owner, t.Tournament_Event, t.Rank, t.Link_to_Source,"
            "       d.form_ids, d.paste_info"
            "  FROM Team t JOIN team_detail d ON t.Team_ID = d.team_id"
        ).fetchall()
    finally:
        conn.close()

    matched = []
    for r in rows:
        present = _dexes_in_form_ids(r["form_ids"])
        if not present:
            continue
        if any(not (ds & present) for ds in resolved):
            continue
        matched.append(r)

    matched.sort(key=lambda r: _team_date_key(r["Date_Shared"], r["Team_ID"]), reverse=True)

    total = len(matched)
    start = (page - 1) * page_size
    page_rows = matched[start:start + page_size]

    name_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get_all_pokemon().items()}
    move_map = pokedb.get_all_moves()
    item_map = pokedb.get_all_items()
    ability_map = pokedb.get_all_abilities()

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "teams": [_build_team_library_item(r, indexes["by_form_id"], name_zh_map,
                                           move_map, item_map, ability_map)
                  for r in page_rows],
    }


# --------------------------------------------------------------------------
# 队伍库新增（/team/add 页面）数据访问
# --------------------------------------------------------------------------

def _parse_paste_entries(text: str):
    """把 Showdown 队伍文本按空行分块逐只解析。

    返回 (entries, resolved, unresolved)
      entries:    解析出的原始条目列表
      resolved:   [(entry, roster_entry), ...]（名字能对上 roster 的）
      unresolved: [entry, ...]（名字无法解析到 roster 的）
    """
    blocks = re.split(r"\n\s*\n", (text or "").strip())
    entries = []
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        e = _parse_showdown_pre(b)
        if e.get("name"):
            entries.append(e)
    if not entries:
        return [], [], []
    indexes = _load_roster_indexes()
    by_slug = indexes["by_slug"]
    resolved, unresolved = [], []
    for e in entries:
        r = by_slug.get(_slugify_name(e["name"])) or resolve_showdown_name(e["name"], by_slug)
        if r:
            resolved.append((e, r))
        else:
            unresolved.append(e)
    return entries, resolved, unresolved


def _parse_paste_preview(resolved) -> list[dict]:
    """把解析结果转成前端预览条目（带中文名/精灵图/属性）。"""
    pokedb = get_pokedb()
    poke_zh = {k: v.get("name_zh", "") for k, v in pokedb.get_all_pokemon().items()}
    out = []
    for e, r in resolved:
        out.append({
            "name": e.get("name", r["name"]),
            "name_zh": poke_zh.get(r["slug"], r["name"]),
            "slug": r["slug"],
            "form_id": r["form_id"],
            "form": r.get("form") or "",
            "sprite": f"sprites/champions/{r['sprite']}" if r.get("sprite") else "",
            "types": r.get("types", []),
            "item": e.get("item", ""),
            "ability": e.get("ability", ""),
            "nature": e.get("nature", ""),
            "level": e.get("level", 0),
            "evs": e.get("evs", {}),
            "moves": e.get("moves", []),
            "gender": e.get("gender", ""),
        })
    return out


_EV_ZH_LABELS = {
    "hp": "HP", "attack": "攻击", "defense": "防御",
    "sp_atk": "特攻", "sp_def": "特防", "speed": "速度",
}


def _build_teaminfo_block(meta: dict, resolved: list, zh_maps: dict) -> str:
    """生成追加到 teaminfo.txt 的可读队伍信息文本块。"""
    def _zh(mp, raw):
        return (mp.get(_slugify_name(raw)) or {}).get("name_zh", "") or raw

    lines = [
        f"==================== {meta['team_id']} ====================",
        f"队伍ID: {meta['team_id']}",
        f"队伍名称: {meta['name'] or '-'}",
        f"队伍描述: {meta['description'] or '-'}",
        f"来源连接: {meta['source_link'] or '-'}",
        f"冠军队伍码: {meta['replica_code'] or '-'}",
        f"所有者: {meta['owner'] or '-'}",
        f"赛事: {meta['event'] or '-'}",
        f"名次: {meta['rank'] or '-'}",
        f"分享日期: {meta['date_shared']}",
        f"Pokepaste: {meta['pokepaste'] or '-'}",
        "────────────────────────────────────",
    ]
    for i, (e, r) in enumerate(resolved, 1):
        lines.append(f"【{i}】{_zh(zh_maps['pokemon'], r['name'])} {r['name']}")
        if e.get("item"):
            lines.append(f"  道具: {_zh(zh_maps['item'], e['item'])} {e['item']}")
        if e.get("ability"):
            lines.append(f"  特性: {_zh(zh_maps['ability'], e['ability'])} {e['ability']}")
        if e.get("nature"):
            lines.append(f"  性格: {_NATURE_ZH.get(e['nature'], e['nature'])} {e['nature']}")
        evs = e.get("evs") or {}
        if evs:
            ev_txt = " / ".join(
                f"{_EV_ZH_LABELS.get(k, k)} {v}" for k, v in evs.items() if v)
            lines.append(f"  EV: {ev_txt}")
        moves = e.get("moves") or []
        if moves:
            lines.append(f"  招式: {_zh(zh_maps['move'], moves[0])} {moves[0]}")
            for m in moves[1:]:
                lines.append(f"        {_zh(zh_maps['move'], m)} {m}")
    return "\n".join(lines)


def _write_teaminfo(block: str) -> None:
    """把队伍信息块追加到项目根目录 teaminfo.txt。"""
    path = PROJECT_ROOT / "teaminfo.txt"
    with open(path, "a", encoding="utf-8") as f:
        f.write(block + "\n\n")


def _upsert_team_row(conn, team_id: str, col_vals: dict) -> bool:
    """写入/覆盖 Team 表的一行（Team 表无主键，先查后写），返回是否已存在。"""
    exists = conn.execute(
        'SELECT COUNT(*) FROM "Team" WHERE "Team_ID" = ?', (team_id,)).fetchone()[0]
    if exists:
        keys = list(col_vals)
        sets = ", ".join(f'"{k}" = ?' for k in keys)
        conn.execute(
            f'UPDATE "Team" SET {sets} WHERE "Team_ID" = ?',
            [col_vals[k] for k in keys] + [team_id])
    else:
        cols = ", ".join(f'"{k}"' for k in list(col_vals) + ["Team_ID"])
        ph = ", ".join("?" for _ in list(col_vals) + ["Team_ID"])
        conn.execute(
            f'INSERT INTO "Team" ({cols}) VALUES ({ph})',
            [col_vals[k] for k in col_vals] + [team_id])
    return bool(exists)


def _stat_min_max(value):
    """将属性值统一为 (min, max) 区间。"""
    if isinstance(value, list) and value:
        values = [_to_int(v, 0) for v in value]
        return min(values), max(values)
    scalar = _to_int(value, 0)
    return scalar, scalar


def _attacker_stat_value(value):
    """攻击方属性取最大值，兼容对方队伍的区间属性。"""
    if isinstance(value, list) and value:
        return max(_to_int(v, 0) for v in value)
    return _to_int(value, 0)


def _compute_damage_with_roll(power, atk, defense, stab, type_multiplier, roll):
    if power <= 0 or atk <= 0 or defense <= 0 or type_multiplier <= 0:
        return 0
    base = floor(floor((2 * _DAMAGE_LEVEL) / 5 + 2) * power * atk / defense / 50) + 2
    return max(1, floor(base * stab * type_multiplier * roll / 100))

## 该方法已弃用
def _compute_damage_range(attacker, defender, move):
    """计算某技能对目标的极限伤害范围（对方属性取极限值）。"""
    power = _to_int(move.get("power"), 0)
    if power <= 0:
        return None

    category = (move.get("category") or "").lower()
    if category == "physical":
        atk_stat = _attacker_stat_value(attacker.get("stats", {}).get("attack"))
        def_min, def_max = _stat_min_max(defender.get("stats", {}).get("defense"))
    elif category == "special":
        atk_stat = _attacker_stat_value(attacker.get("stats", {}).get("sp_atk"))
        def_min, def_max = _stat_min_max(defender.get("stats", {}).get("sp_def"))
    else:
        return None

    if atk_stat <= 0 or def_max <= 0:
        return None

    hp_min, hp_max = _stat_min_max(defender.get("stats", {}).get("hp"))
    hp_min = max(hp_min, 1)
    hp_max = max(hp_max, 1)

    move_type = move.get("type", "")
    effectiveness = defender.get("type_effectiveness", {})
    type_multiplier = float(effectiveness.get(move_type.lower(), 1.0))
    if type_multiplier <= 0:
        return {
            "damage_min": 0,
            "damage_max": 0,
            "hp_pct_min": 0.0,
            "hp_pct_max": 0.0,
            "type_multiplier": type_multiplier,
        }

    stab = 1.5 if move_type in attacker.get("types", []) else 1.0
    # 最低伤害：最低 roll + 对方最大防御
    damage_min = _compute_damage_with_roll(power, atk_stat, def_max, stab, type_multiplier, 85)
    # 最高伤害：最高 roll + 对方最小防御
    damage_max = _compute_damage_with_roll(
        power, atk_stat, max(def_min, 1), stab, type_multiplier, 100
    )
    hp_pct_min = round(damage_min * 100 / hp_max, 2)
    hp_pct_max = round(damage_max * 100 / hp_min, 2)

    return {
        "damage_min": damage_min,
        "damage_max": damage_max,
        "hp_pct_min": hp_pct_min,
        "hp_pct_max": hp_pct_max,
        "type_multiplier": type_multiplier,
    }


def _is_guaranteed_critical_move(move):
    """识别“必定击中要害”技能（不含仅提高要害率）。"""
    move_name_raw = (move.get("name") or "").lower().strip()
    move_name = move_name_raw.replace(" ", "-").replace("_", "-")
    short_effect = (move.get("short_effect") or "").lower()
    short_effect_zh = move.get("short_effect_zh") or ""
    guaranteed_critical_move_names = {
        "frost-breath",
        "storm-throw",
        "wicked-blow",
        "surging-strikes",
        "flower-trick",
    }
    if move_name in guaranteed_critical_move_names:
        return True
    guaranteed_tokens_en = [
        "always results in a critical hit",
        "always scores a critical hit",
    ]
    if any(token in short_effect for token in guaranteed_tokens_en):
        return True
    return "必定会击中要害" in short_effect_zh


def _apply_guaranteed_critical_modifier(range_info, is_guaranteed_critical):
    """必定要害修正：当前简化按 1.5 倍处理。"""
    if not is_guaranteed_critical:
        return range_info
    crit_modifier = 1.5
    return {
        "damage_min": 0 if range_info["damage_min"] <= 0 else max(1, floor(range_info["damage_min"] * crit_modifier)),
        "damage_max": 0 if range_info["damage_max"] <= 0 else max(1, floor(range_info["damage_max"] * crit_modifier)),
        "hp_pct_min": round(range_info["hp_pct_min"] * crit_modifier, 2),
        "hp_pct_max": round(range_info["hp_pct_max"] * crit_modifier, 2),
        "type_multiplier": range_info["type_multiplier"],
    }


def _is_spread_move(move):
    """轻量识别双打范围招式（命中多个目标时会有伤害修正）。"""
    move_name_raw = (move.get("name") or "").lower().strip()
    move_name = move_name_raw.replace(" ", "-").replace("_", "-")
    short_effect = (move.get("short_effect") or "").lower()
    short_effect_zh = move.get("short_effect_zh") or ""
    spread_move_names = {
        "heat-wave",
        "rock-slide",
        "blizzard",
        "earthquake",
        "surf",
        "discharge",
        "dazzling-gleam",
        "muddy-water",
        "snarl",
        "icy-wind",
        "electroweb",
        "eruption",
        "water-spout",
        "hyper-voice",
        "boomburst",
        "sludge-wave",
        "brutal-swing",
        "lava-plume",
        "bulldoze",
        "breaking-swipe",
    }
    if move_name in spread_move_names:
        return True
    spread_tokens_en = [
        "all adjacent foes",
        "all adjacent pokemon",
        "hits both opponents",
        "all other pokemon",
    ]
    spread_tokens_zh = ["全体", "所有", "双方", "除自己以外"]
    if any(token in short_effect for token in spread_tokens_en):
        return True
    if any(token in short_effect_zh for token in spread_tokens_zh):
        return True
    return False


def _apply_spread_modifier(range_info, battle_mode, is_spread_move):
    """双打下范围技能伤害修正。"""
    if battle_mode != "double" or not is_spread_move:
        return range_info
    modifier = 0.75
    damage_min = 0 if range_info["damage_min"] <= 0 else max(1, floor(range_info["damage_min"] * modifier))
    damage_max = 0 if range_info["damage_max"] <= 0 else max(1, floor(range_info["damage_max"] * modifier))
    return {
        "damage_min": damage_min,
        "damage_max": damage_max,
        "hp_pct_min": round(range_info["hp_pct_min"] * modifier, 2),
        "hp_pct_max": round(range_info["hp_pct_max"] * modifier, 2),
        "type_multiplier": range_info["type_multiplier"],
    }


def _is_multi_hit_move(move):
    """基于技能描述做轻量识别：是否可能为多段伤害技能。"""
    short_effect = (move.get("short_effect") or "").lower()
    short_effect_zh = move.get("short_effect_zh") or ""
    multi_hit_tokens = [
        "2 to 5 times",
        "hits 2 times",
        "hits twice",
        "two to five times",
    ]
    if any(token in short_effect for token in multi_hit_tokens):
        return True
    if "连续" in short_effect_zh and "攻击" in short_effect_zh:
        return True
    return False


def create_app():
    app = Flask(__name__, static_folder=str(_ROOT), static_url_path="")
    CORS(app)

    # 确保截图目录存在
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    @app.route("/", methods=["GET"])
    def index():
        html_file = _ROOT / "index.html"
        response = send_file(html_file, mimetype="text/html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    _data_prewarmed = False

    @app.route("/data", methods=["GET"])
    def data_page():
        nonlocal _data_prewarmed
        if not _data_prewarmed:
            _data_prewarmed = True
            def _warm():
                try:
                    get_usage_db().get_all()
                    get_pokedb().get_all_pokemon()
                except Exception:
                    pass
            threading.Thread(target=_warm, daemon=True).start()
        html_file = _ROOT / "data" / "index.html"
        response = send_file(html_file, mimetype="text/html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.route("/data/<slug>", methods=["GET"])
    def data_detail_page(slug):
        html_file = _ROOT / "data" / "detail.html"
        response = send_file(html_file, mimetype="text/html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.route("/team", methods=["GET"])
    def team_library_page():
        html_file = _ROOT / "team" / "index.html"
        response = send_file(html_file, mimetype="text/html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.route("/team/add", methods=["GET"])
    def team_add_page():
        html_file = _ROOT / "team" / "add.html"
        response = send_file(html_file, mimetype="text/html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.route("/teamAnalysis", methods=["GET"])
    def team_analysis_page():
        html_file = _ROOT / "teamAnalysis.html"
        response = send_file(html_file, mimetype="text/html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.route("/api/data/pokemon-detail/<slug>", methods=["GET"])
    def pokemon_data_detail(slug):
        try:
            season = request.args.get("season")
            fmt = request.args.get("format")
            pokechamdb = get_usage_db().get_all(season=season, format=fmt)
            raw = pokechamdb.get(slug)
            if not raw:
                return jsonify({"success": False, "error": f"slug '{slug}' not found"}), 404

            pokedb = get_pokedb()
            roster_by_slug = {p["slug"]: p for p in get_roster_db().get_all()}
            name_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get_all_pokemon().items()}
            move_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get_all_moves().items()}
            item_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get_all_items().items()}
            ability_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get_all_abilities().items()}

            entry = roster_by_slug.get(slug)
            sprite = ""
            if entry and entry.get("sprite"):
                sprite = f"sprites/champions/{entry['sprite']}"
            name_zh = name_zh_map.get(slug, slug)
            base_stats = (pokedb.get_pokemon(slug) or {}).get("base_stats", {})

            def _slug(s): return s.lower().replace(" ", "-").replace("'", "").replace(".", "")
            def _is_damaging(name):
                ms = _slug(name)
                md = pokedb.get_move(ms) or {}
                p = md.get("power")
                return p is not None and p > 0
            def _tr(items, m):
                return [{"name": m.get(_slug(i.get("name", ""))) or i["name"], "pct": i["pct"]} for i in items]

            # Build evoforms list
            base_name = (entry or {}).get("name", slug)
            evoforms = []
            for pk in get_roster_db().get_all():
                if pk.get("name", "").lower() != base_name:
                    continue
                if pk["slug"] == slug:
                    continue
                form_val = pk.get("form")
                if form_val and form_val in _EVOFORM_TYPES:
                    pd = pokedb.get_pokemon(pk["slug"]) or {}
                    evoforms.append({
                        "slug_name": pk["slug"],
                        "form_name": form_val,
                        "form_name_zh": name_zh_map.get(pk["slug"], name_zh),
                        "base_stats": pd.get("base_stats", {}),
                        "ability": [{"name": a.lower()} for a in (pd.get("abilities", []) or [])] if pd.get("abilities") else [],
                        "types": pk.get("types", []),
                        "sprite": f"sprites/champions/{pk['sprite']}" if pk.get("sprite") else "",
                        "name_zh": name_zh_map.get(pk["slug"], name_zh),
                    })

            result = {
                "slug": slug,
                "name_zh": name_zh,
                "sprite": sprite,
                "rank": raw.get("rank"),
                "types": entry.get("types", []) if entry else [],
                "base_stats": base_stats,
                "moves": [{"name": move_zh_map.get(_slug(i.get("name", ""))) or i["name"], "pct": i["pct"], "damaging": _is_damaging(i.get("name", ""))} for i in raw.get("moves", [])],
                "items": _tr(raw.get("items", []), item_zh_map),
                "abilities": _tr(raw.get("abilities", []), ability_zh_map),
                "natures": [{"name": _NATURE_ZH.get(i["name"], i["name"]), "name_en": i["name"], "pct": i["pct"]} for i in raw.get("natures", [])],
                "teammates": _tr(raw.get("teammates", []), name_zh_map),
                "evs": raw.get("evs", []),
                "evoforms": evoforms,
            }
            return jsonify({"success": True, "pokemon": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/data/seasons", methods=["GET"])
    def data_seasons():
        try:
            seasons = get_usage_db().get_seasons()
            return jsonify({"success": True, "seasons": seasons})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/data/formats", methods=["GET"])
    def data_formats():
        try:
            formats = get_usage_db().get_formats()
            return jsonify({"success": True, "formats": formats})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/data/pokemon-list", methods=["GET"])
    def pokemon_data_list():
        try:
            season = request.args.get("season")
            fmt = request.args.get("format")
            pokechamdb = get_usage_db().get_all(season=season, format=fmt)
            pokedb = get_pokedb()

            roster_by_slug = {p["slug"]: p for p in get_roster_db().get_all()}
            name_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get_all_pokemon().items()}

            entries = []
            for slug, data in pokechamdb.items():
                rank = data.get("rank") if isinstance(data, dict) else None
                entry = roster_by_slug.get(slug)
                sprite = ""
                if entry and entry.get("sprite"):
                    sprite = f"sprites/champions/{entry['sprite']}"
                name_zh = name_zh_map.get(slug, slug)
                entries.append({
                    "slug": slug,
                    "name_zh": name_zh,
                    "sprite": sprite,
                    "rank": rank if rank is not None else 9999,
                })
            entries.sort(key=lambda x: x["rank"])
            for idx, p in enumerate(entries, start=1):
                p["index"] = idx
            return jsonify({"success": True, "pokemon": entries})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/data/roster-list", methods=["GET"])
    def roster_data_list():
        """返回 champions_roster 表中所有参赛（过签）宝可梦，供对手/我方切换。
        每只含基础信息（slug/name_zh/sprite/types/base_stats/forms）+ 可用时合并使用率默认
        配置（natures/abilities/items/evs/moves），方便前端直接构建默认队伍卡。"""
        try:
            season = request.args.get("season")
            fmt = request.args.get("format")
            pokedb = get_pokedb()
            roster = get_roster_db().get_all()
            roster_by_slug = {p["slug"]: p for p in roster}
            name_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get_all_pokemon().items()}
            ability_map = {k: v for k, v in pokedb.get_all_abilities().items()}
            pokedb_moves = pokedb.get_all_moves()

            usage = get_usage_db().get_all(season=season, format=fmt) or {}

            def _slug(s):
                return (s or "").lower().replace(" ", "-").replace("'", "").replace(".", "")

            def _ability_info(ablug):
                a = ability_map.get(_slug(ablug), {})
                return {"name": a.get("name", ablug), "name_zh": a.get("name_zh", ablug)}

            def _move_info(name):
                md = pokedb_moves.get(_slug(name), {})
                power = md.get("power")
                return {
                    "name": name,
                    "name_zh": md.get("name_zh", name),
                    "power": power,
                    "damaging": power is not None and power > 0,
                    "category": md.get("category", "status"),
                    "type": md.get("type", "Normal"),
                    "priority": md.get("priority", 0),
                }

            def _build_forms(slug):
                entry = roster_by_slug.get(slug)
                if not entry:
                    return []
                base_name = entry.get("name") or slug
                forms = []
                for pk in roster:
                    if (pk.get("name") or "").lower() != base_name.lower():
                        continue
                    pd = pokedb.get_pokemon(pk["slug"]) or {}
                    forms.append({
                        "slug": pk["slug"],
                        "form": pk.get("form", ""),
                        "name_zh": name_zh_map.get(pk["slug"], base_name),
                        "types": pk.get("types", []),
                        "base_stats": pd.get("base_stats", {}),
                        "abilities": [_ability_info(a) for a in (pd.get("abilities", []) or [])],
                        "sprite": f"sprites/champions/{pk['sprite']}" if pk.get("sprite") else "",
                    })
                return forms

            entries = []
            for pk in roster:
                slug = pk["slug"]
                pd = pokedb.get_pokemon(slug) or {}
                raw = usage.get(slug)
                entry = {
                    "slug": slug,
                    "form": pk.get("form", "") or "",
                    "name_zh": name_zh_map.get(slug, slug),
                    "sprite": f"sprites/champions/{pk['sprite']}" if pk.get("sprite") else "",
                    "types": pk.get("types", []),
                    "base_stats": pd.get("base_stats", {}),
                    "forms": _build_forms(slug),
                    "has_usage": bool(raw),
                }
                if raw:
                    entry["natures"] = [{"name": n.get("name", ""), "name_zh": n.get("name_zh", ""), "pct": n.get("pct", 0)} for n in raw.get("natures", [])]
                    entry["abilities"] = [{"name": a.get("name", ""), "name_zh": a.get("name_zh", ""), "pct": a.get("pct", 0)} for a in raw.get("abilities", [])]
                    entry["items"] = [{"name": i.get("name", ""), "name_zh": i.get("name_zh", ""), "pct": i.get("pct", 0)} for i in raw.get("items", [])]
                    entry["evs"] = [{"hp": e.get("hp", 0), "atk": e.get("atk", 0), "def": e.get("def", 0),
                                    "spA": e.get("spA", 0), "spD": e.get("spD", 0), "spe": e.get("spe", 0),
                                    "pct": e.get("pct", 0)} for e in raw.get("evs", [])]
                    entry["moves"] = [_move_info(m.get("name", "")) for m in raw.get("moves", [])]
                else:
                    # 无使用率：仅给 PokeDB 的基础能力（不造默认招式/道具）
                    entry["natures"] = []
                    entry["abilities"] = [_ability_info(a) for a in (pd.get("abilities", []) or [])]
                    entry["items"] = []
                    entry["evs"] = []
                    entry["moves"] = []
                entries.append(entry)

            # 排序：有使用率的按 rank 排前，无使用率的按 name_zh 兜底
            return jsonify({"success": True, "pokemon": entries, "rosterList": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/data/all-moves", methods=["GET"])
    def all_moves():
        """返回图鉴全部技能（PokeDB moves 表），供我方技能搜索挑选使用。
        技能形状与 enemies 的 moves 同构（name/name_zh/type/power/category/priority）。"""
        try:
            pokedb_moves = get_pokedb().get_all_moves()
            seen = set()
            out = []
            for slug, m in pokedb_moves.items():
                name = (m.get("name") or "").strip()
                key = name or slug
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "slug": slug,
                    "name": name,
                    "name_zh": m.get("name_zh", "") or name or slug,
                    "type": m.get("type", "Normal"),
                    "power": m.get("power"),
                    "category": m.get("category", "status"),
                    "priority": m.get("priority", 0),
                })
            return jsonify({"success": True, "moves": out, "total": len(out)})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/team-analysis/enemies", methods=["GET"])
    def team_analysis_enemies():
        """战队对抗分析页：返回某 (赛季, 格式) 下全部敌方宝可梦的构建数据。
        每只按对战数据 rank 排序，默认 rank-1 的性格/特性/道具/努力值/技能（英文名 + 中文名），
        并附多形态(forms)、基础能力、克制属性、技能威力信息，供前端做伤害计算与切换。"""
        try:
            season = request.args.get("season") or None
            fmt = request.args.get("format") or None
            usage = get_usage_db().get_all(season=season, format=fmt)
            if not usage:
                return jsonify({"success": False, "error": "该赛季/格式暂无对战数据"}), 404

            pokedb = get_pokedb()
            roster = get_roster_db().get_all()
            roster_by_slug = {p["slug"]: p for p in roster}
            name_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get_all_pokemon().items()}
            pokedb_moves = pokedb.get_all_moves()

            def _slug(s):
                return (s or "").lower().replace(" ", "-").replace("'", "").replace(".", "")

            def _en_name(raw):
                return (raw or "").strip()

            def _build_forms(slug):
                """同一 base name 的所有形态（含当前），供前端形态切换。"""
                entry = roster_by_slug.get(slug)
                if not entry:
                    return []
                base_name = entry.get("name") or slug
                forms = []
                for pk in roster:
                    if (pk.get("name") or "").lower() != base_name.lower():
                        continue
                    pd = pokedb.get_pokemon(pk["slug"]) or {}
                    forms.append({
                        "slug": pk["slug"],
                        "form": pk.get("form", ""),
                        "name_zh": name_zh_map.get(pk["slug"], base_name),
                        "types": pk.get("types", []),
                        "base_stats": pd.get("base_stats", {}),
                        "abilities": [a for a in (pd.get("abilities", []) or [])],
                        "sprite": f"sprites/champions/{pk['sprite']}" if pk.get("sprite") else "",
                    })
                return forms

            def _build_move(m):
                ms = _slug(m.get("name", ""))
                md = pokedb_moves.get(ms, {})
                power = md.get("power")
                damaging = power is not None and power > 0
                return {
                    "name": m.get("name", ""),
                    "name_zh": m.get("name_zh", ""),
                    "pct": m.get("pct", 0),
                    "damaging": damaging,
                    "power": power,
                    "category": md.get("category", "status"),
                    "type": md.get("type", "Normal"),
                    "priority": md.get("priority", 0),
                }

            enemies = []
            for slug, raw in usage.items():
                entry = roster_by_slug.get(slug)
                base_stats = (pokedb.get_pokemon(slug) or {}).get("base_stats", {})
                sprite = f"sprites/champions/{entry['sprite']}" if entry and entry.get("sprite") else ""
                enemies.append({
                    "slug": slug,
                    "rank": raw.get("rank"),
                    "name_en": _en_name(raw.get("name_en", slug)),
                    "name_zh": raw.get("name_zh", name_zh_map.get(slug, slug)),
                    "types": (entry.get("types", []) if entry else []),
                    "sprite": sprite,
                    "base_stats": base_stats,
                    "forms": _build_forms(slug),
                    "natures": [{"name": n.get("name", ""), "name_zh": n.get("name_zh", ""), "pct": n.get("pct", 0)} for n in raw.get("natures", [])],
                    "abilities": [{"name": a.get("name", ""), "name_zh": a.get("name_zh", ""), "pct": a.get("pct", 0)} for a in raw.get("abilities", [])],
                    "items": [{"name": i.get("name", ""), "name_zh": i.get("name_zh", ""), "pct": i.get("pct", 0)} for i in raw.get("items", [])],
                    "evs": [{"hp": e.get("hp", 0), "atk": e.get("atk", 0), "def": e.get("def", 0),
                             "spA": e.get("spA", 0), "spD": e.get("spD", 0), "spe": e.get("spe", 0),
                             "pct": e.get("pct", 0)} for e in raw.get("evs", [])],
                    "moves": [_build_move(m) for m in raw.get("moves", [])],
                })
            enemies.sort(key=lambda x: (x["rank"] if x["rank"] is not None else 9999))
            for idx, e in enumerate(enemies, start=1):
                e["index"] = idx

            return jsonify({
                "success": True,
                "season": season or get_usage_db().DEFAULT_SEASON,
                "format": fmt or get_usage_db().DEFAULT_FORMAT,
                "total": len(enemies),
                "enemies": enemies,
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    # Nature multiplier table
    _EVOFORM_TYPES = {"mega", "mega-nium", "mega-x", "mega-y", "blade-forme", "hero"}

    _NATURE_MULT = {
        'Hardy': {}, 'Lonely': {'attack': 1.1, 'defense': 0.9},
        'Brave': {'attack': 1.1, 'speed': 0.9}, 'Adamant': {'attack': 1.1, 'sp_atk': 0.9},
        'Naughty': {'attack': 1.1, 'sp_def': 0.9}, 'Bold': {'defense': 1.1, 'attack': 0.9},
        'Docile': {}, 'Relaxed': {'defense': 1.1, 'speed': 0.9},
        'Impish': {'defense': 1.1, 'sp_atk': 0.9}, 'Lax': {'defense': 1.1, 'sp_def': 0.9},
        'Timid': {'speed': 1.1, 'attack': 0.9}, 'Hasty': {'speed': 1.1, 'defense': 0.9},
        'Serious': {}, 'Jolly': {'speed': 1.1, 'sp_atk': 0.9}, 'Naive': {'speed': 1.1, 'sp_def': 0.9},
        'Modest': {'sp_atk': 1.1, 'attack': 0.9}, 'Mild': {'sp_atk': 1.1, 'defense': 0.9},
        'Quiet': {'sp_atk': 1.1, 'speed': 0.9}, 'Bashful': {},
        'Rash': {'sp_atk': 1.1, 'sp_def': 0.9}, 'Calm': {'sp_def': 1.1, 'attack': 0.9},
        'Gentle': {'sp_def': 1.1, 'defense': 0.9}, 'Sassy': {'sp_def': 1.1, 'speed': 0.9},
        'Careful': {'sp_def': 1.1, 'sp_atk': 0.9}, 'Quirky': {},
    }
    _STAT_KEYS = ['hp', 'attack', 'defense', 'sp_atk', 'sp_def', 'speed']
    _EV_KEYS = ['hp', 'atk', 'def', 'spA', 'spD', 'spe']

    def _build_actual_stats(base_stats, ev_dict, nature_name):
        stats = {}
        for sk, ek in zip(_STAT_KEYS, _EV_KEYS):
            base = base_stats.get(sk, 80)
            ev = ev_dict.get(ek, 0)
            if sk == 'hp':
                stats[sk] = max(1, base + 75 + ev)
            else:
                nm = _NATURE_MULT.get(nature_name, {}).get(sk, 1.0)
                stats[sk] = max(1, int((base + 20 + ev) * nm))
        return stats

    def _compute_effectiveness(types, type_chart):
        types = [t.lower() for t in types]
        eff = {}
        for atk_type, def_chart in type_chart.items():
            mult = 1.0
            for dt in types:
                mult *= def_chart.get(dt, 1.0)
            eff[atk_type] = mult
        return eff

    _EV_KEY_MAP = {'hp':'hp', 'atk':'attack', 'def':'defense', 'spA':'sp_atk', 'spD':'sp_def', 'spe':'speed'}
    _EV_LABEL_MAP = {'hp':'HP','atk':'Atk','def':'Def','spA':'SpA','spD':'SpD','spe':'Spd'}

    def _build_move_meta(move_list, pokedb_moves, move_zh_map):
        result = []
        for m in move_list:
            calc_name = m["name"].lower().replace(" ", "-").replace("'", "").replace(".", "").replace("é", "e")
            md = pokedb_moves.get(calc_name, {})
            power = md.get("power")
            if power is not None and power > 0:
                result.append({
                    "name": calc_name,  # lowercase with hyphens, for calcDamage
                    "name_zh": move_zh_map.get(calc_name, m["name"]),
                    "power": power,
                    "category": md.get("category", "status"),
                    "type": md.get("type", "Normal"),
                    "priority": md.get("priority", 0),
                })
        return result

    @app.route("/api/data/pokemon-damage-rankings/<slug>", methods=["GET"])
    def pokemon_damage_rankings(slug):
        try:
            season = request.args.get("season")
            fmt = request.args.get("format")
            pokechamdb = get_usage_db().get_all(season=season, format=fmt)
            pokedb = get_pokedb()

            roster_by_slug = {p["slug"]: p for p in get_roster_db().get_all()}
            name_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get_all_pokemon().items()}
            pokedb_moves = pokedb.get_all_moves()
            move_zh_map = {k: v.get("name_zh", "") for k, v in pokedb_moves.items()}

            my_raw = pokechamdb.get(slug)
            if not my_raw:
                return jsonify({"success": False, "error": f"slug '{slug}' not found"}), 404

            my_roster = roster_by_slug.get(slug, {})
            my_base = (pokedb.get_pokemon(slug) or {}).get("base_stats", {})

            # Accept query params for current Pokemon's EVs and nature
            my_ev = {}
            for _ek in ['hp', 'atk', 'def', 'spA', 'spD', 'spe']:
                _val = request.args.get(f'ev_{_ek}', type=int)
                if _val is not None:
                    my_ev[_ek] = _val
            _q_nature = request.args.get('nature', '')
            if not my_ev:
                my_ev_list = my_raw.get("evs", [{}])
                my_ev = my_ev_list[0] if my_ev_list else {}
            if not _q_nature:
                my_nature_list = my_raw.get("natures", [])
                my_nature = my_nature_list[0]["name"] if my_nature_list else "Hardy"
            else:
                my_nature = _q_nature

            my_actual_stats = _build_actual_stats(my_base, my_ev, my_nature)
            my_speed = my_actual_stats.get("speed", 80)
            my_hp = my_actual_stats.get("hp", 1)
            my_moves = _build_move_meta(my_raw.get("moves", []), pokedb_moves, move_zh_map)

            # Build my data in calcDamage-compatible format
            my_ev_for_calc = {}
            for ek, ck in _EV_KEY_MAP.items():
                my_ev_for_calc[ck] = my_ev.get(ek, 0)
            my_items_raw = my_raw.get("items", [])
            my_item = my_items_raw[0]["name"].lower().replace(" ", "-") if my_items_raw else ""
            my_items_list = [{"name": i["name"].lower().replace(" ", "-"), "pct": i["pct"]} for i in my_items_raw] if my_items_raw else []
            my_abilities_raw = my_raw.get("abilities", [])
            my_ability_list = [{"name": a["name"].lower()} for a in my_abilities_raw] if my_abilities_raw else [{"name": "No Ability"}]
            my_types = my_roster.get("types", [])
            my_sprite = f"sprites/champions/{my_roster['sprite']}" if my_roster and my_roster.get("sprite") else ""

            me_data = {
                "slug": slug,
                "name_zh": name_zh_map.get(slug, slug),
                "sprite": my_sprite,
                "types": my_types,
                "speed": my_speed,
                "hp": my_hp,
                "base_stats": my_base,
                "evs": my_ev_for_calc,
                "nature": my_nature,
                "ability": my_ability_list,
                "item": my_item,
                "items": my_items_list,
                "moves": my_moves,
            }

            # Build opponents list
            opponents = []
            for opp_slug, opp_raw in pokechamdb.items():
                if opp_slug == slug:
                    continue
                if not isinstance(opp_raw, dict):
                    continue
                opp_roster = roster_by_slug.get(opp_slug)
                if not opp_roster:
                    continue
                opp_base = (pokedb.get_pokemon(opp_slug) or {}).get("base_stats", {})
                if not opp_base:
                    continue

                opp_ev_list = opp_raw.get("evs", [{}])
                opp_first_ev = opp_ev_list[0] if opp_ev_list else {}
                opp_nature_list = opp_raw.get("natures", [])
                opp_nature = opp_nature_list[0]["name"] if opp_nature_list else "Hardy"
                opp_types = opp_roster.get("types", [])

                opp_actual_stats = _build_actual_stats(opp_base, opp_first_ev, opp_nature)
                opp_speed = opp_actual_stats.get("speed", 80)
                opp_hp = opp_actual_stats.get("hp", 1)
                opp_moves = _build_move_meta(opp_raw.get("moves", []), pokedb_moves, move_zh_map)

                # ev_text
                ev_text_parts = []
                for ek, el in _EV_LABEL_MAP.items():
                    v = opp_first_ev.get(ek, 0)
                    if v > 0:
                        ev_text_parts.append(f"{el}{v}")
                ev_text = ' '.join(ev_text_parts)

                # EV in calcDamage format
                ev_for_calc = {}
                for ek, ck in _EV_KEY_MAP.items():
                    ev_for_calc[ck] = opp_first_ev.get(ek, 0)

                opp_items_raw = opp_raw.get("items", [])
                opp_item = opp_items_raw[0]["name"].lower().replace(" ", "-") if opp_items_raw else ""
                opp_items_list = [{"name": i["name"].lower().replace(" ", "-"), "pct": i["pct"]} for i in opp_items_raw] if opp_items_raw else []
                opp_abilities_raw = opp_raw.get("abilities", [])
                opp_ability_list = [{"name": a["name"].lower()} for a in opp_abilities_raw] if opp_abilities_raw else [{"name": "No Ability"}]
                opp_sprite = f"sprites/champions/{opp_roster['sprite']}" if opp_roster.get("sprite") else ""

                opponents.append({
                    "slug": opp_slug,
                    "name_zh": name_zh_map.get(opp_slug, opp_slug),
                    "rank": opp_raw.get("rank", 9999),
                    "sprite": opp_sprite,
                    "types": opp_types,
                    "speed": opp_speed,
                    "hp": opp_hp,
                    "base_stats": opp_base,
                    "ev_text": ev_text,
                    "evs": ev_for_calc,
                    "nature": opp_nature,
                    "ability": opp_ability_list,
                    "item": opp_item,
                    "items": opp_items_list,
                    "moves": opp_moves,
                })

            return jsonify({
                "success": True,
                "me": me_data,
                "opponents": opponents,
            })

        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/screenshot", methods=["POST"])
    def save_screenshot():
        """接收网页截图并保存到本地"""
        try:
            if "image" not in request.files:
                return jsonify({"success": False, "error": "未找到图片"}), 400

            image_file = request.files["image"]
            stage = request.form.get("type", "unknown")

            if not image_file:
                return jsonify({"success": False, "error": "图片为空"}), 400

            # 读取图片
            image = Image.open(io.BytesIO(image_file.read()))

            # 根据 stage 参数决定保存目录
            if stage == "opp_team":
                save_dir = PROJECT_ROOT / "screenshots" / "opp_team"
                filename = "team.png"
            else:
                save_dir = SCREENSHOTS_DIR
                filename = f"{stage}.png"

            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / filename

            image.save(save_path, "PNG")

            return jsonify({
                "success": True,
                "filename": filename,
                "path": str(save_path)
            })

        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/sprites/<path:filename>")
    def sprites(filename):
        """提供精灵图静态文件"""
        return send_from_directory(SPRITES_DIR, filename)

    @app.route("/api/teams", methods=["GET"])
    def list_teams():
        teams = []
        for path in sorted(TEAM_DIR.glob("*.json")):
            if path.name == "temp.json":
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                teams.append({
                    "id": path.stem,
                    "slot_name": data.get("slot_name", path.stem)
                })
            except Exception:
                pass
        return jsonify({"success": True, "teams": teams})

    @app.route("/api/teams/library", methods=["GET"])
    def teams_library():
        """队伍库：按宝可梦名（中文/英文，物种级）AND 筛选，按 Date_Shared 降序分页。
        参数: p1~p6=宝可梦名, page=页码, page_size=每页条数。"""
        try:
            filters = []
            for i in range(1, 7):
                v = (request.args.get(f"p{i}", "") or "").strip()
                if v:
                    filters.append(v)
            page = max(1, _to_int(request.args.get("page"), 1))
            page_size = min(200, max(1, _to_int(request.args.get("page_size"), 20)))
            return jsonify(_query_team_library(filters, page, page_size))
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/teams/library/parse", methods=["POST"])
    def teams_library_parse():
        """解析粘贴的 Showdown 队伍文本 → 预览（含中文名/精灵图/未解析列表）。"""
        try:
            body = request.get_json(silent=True) or {}
            entries, resolved, unresolved = _parse_paste_entries(body.get("paste") or "")
            return jsonify({
                "success": True,
                "pokemon": _parse_paste_preview(resolved),
                "form_ids": ",".join(r["form_id"] for _, r in resolved),
                "evs_present": any(e.get("evs") for e, _ in resolved),
                "count": len(entries),
                "unresolved": [{"name": u.get("name", "")} for u in unresolved],
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/teams/library/add", methods=["POST"])
    def teams_library_add():
        """新增/覆盖队伍：解析文本 → 写 Team + team_detail → 追加 teaminfo.txt。"""
        try:
            body = request.get_json(silent=True) or {}
            team_id = (body.get("team_id") or "").strip()
            name = (body.get("name") or "").strip()
            paste = (body.get("paste") or "").strip()
            if not team_id or not name:
                return jsonify({"success": False, "error": "队伍ID和队伍名称必填"}), 400
            if not paste:
                return jsonify({"success": False, "error": "请粘贴 Showdown 队伍文本"}), 400

            entries, resolved, unresolved = _parse_paste_entries(paste)
            if unresolved:
                bad = "、".join(u.get("name", "?") for u in unresolved)
                return jsonify({"success": False, "error": f"无法解析的宝可梦: {bad}"}), 400
            if not resolved:
                return jsonify({"success": False, "error": "未解析出任何宝可梦"}), 400

            replica_code = (body.get("replica_code") or "").strip()
            evs_present = any(e.get("evs") for e, _ in resolved)
            date_shared = (body.get("date_shared") or "").strip() \
                or datetime.now().strftime("%Y-%m-%d")
            pokemon_names = [e.get("name", "") for e, _ in resolved]
            items = [e.get("item", "") for e, _ in resolved]

            col_vals = {
                "Team_Description": (body.get("description") or "").strip(),
                "Full_Name": name,
                "Pokepaste": (body.get("pokepaste") or "").strip(),
                "EVs": "Yes" if evs_present else "No",
                "Extracted_paste": "Extracted",
                "Replica_Status": "Y" if replica_code else "X",
                "Replica_Code": replica_code,
                "Date_Shared": date_shared,
                "Tournament_Event": (body.get("event") or "").strip(),
                "Rank": (body.get("rank") or "").strip(),
                "Link_to_Source": (body.get("source_link") or "").strip(),
                "Report_Video": "",
                "Other_Links": "",
                "Owner": (body.get("owner") or "").strip(),
            }
            for i in range(6):
                col_vals[f"Pokemon_{i + 1}"] = pokemon_names[i] if i < len(pokemon_names) else ""
                col_vals[f"Item_{i + 1}"] = items[i] if i < len(items) else ""

            paste_info = {
                "title": name,
                "format": (body.get("format") or "").strip(),
                "pokemon": [
                    {
                        "name": e.get("name", ""),
                        "gender": e.get("gender", ""),
                        "item": e.get("item", ""),
                        "ability": e.get("ability", ""),
                        "level": e.get("level", 0),
                        "evs": e.get("evs", {}),
                        "nature": e.get("nature", ""),
                        "moves": e.get("moves", []),
                        "dex_form": r["form_id"],
                    }
                    for e, r in resolved
                ],
            }
            form_ids = ",".join(r["form_id"] for _, r in resolved)

            conn = sqlite3.connect(str(DB_PATH))
            try:
                overwrote = _upsert_team_row(conn, team_id, col_vals)
                conn.execute(
                    """
                    INSERT INTO "team_detail" ("team_id", "form_ids", "paste_info")
                    VALUES (?, ?, ?)
                    ON CONFLICT("team_id") DO UPDATE SET
                        "form_ids"   = excluded."form_ids",
                        "paste_info" = excluded."paste_info"
                    """,
                    (team_id, form_ids, json.dumps(paste_info, ensure_ascii=False)),
                )
                conn.commit()
            finally:
                conn.close()

            meta = {
                "team_id": team_id, "name": name,
                "description": col_vals["Team_Description"],
                "source_link": col_vals["Link_to_Source"],
                "replica_code": replica_code,
                "owner": col_vals["Owner"],
                "event": col_vals["Tournament_Event"],
                "rank": col_vals["Rank"],
                "date_shared": date_shared,
                "pokepaste": col_vals["Pokepaste"],
            }
            zh_maps = {
                "pokemon": get_pokedb().get_all_pokemon(),
                "move": get_pokedb().get_all_moves(),
                "item": get_pokedb().get_all_items(),
                "ability": get_pokedb().get_all_abilities(),
            }
            _write_teaminfo(_build_teaminfo_block(meta, resolved, zh_maps))

            return jsonify({
                "success": True,
                "team_id": team_id,
                "overwrote": overwrote,
                "date_shared": date_shared,
                "count": len(resolved),
                "teaminfo_written": True,
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/teams/load/<slot_id>", methods=["POST"])
    def load_team_slot(slot_id):
        src = TEAM_DIR / f"{slot_id}.json"
        dst = TEAM_DIR / "temp.json"
        try:
            shutil.copy2(src, dst)
            with open(dst, encoding="utf-8") as f:
                data = json.load(f)
            return jsonify({"success": True, "team": data})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/teams/save", methods=["POST"])
    def save_team_slot():
        body = request.json or {}
        slot_id = body.get("slot_id")
        slot_name = body.get("slot_name", "")
        # 兼容两种 roster 传法：顶层 roster（当前前端）与 team.roster（旧前端缓存）
        roster = body.get("roster")
        if roster is None:
            team = body.get("team") or {}
            roster = team.get("roster")
        try:
            if roster is not None:
                # 与 /api/teams/build 写入 temp.json 的扁平格式保持一致：
                # {trainer_name, roster[, slot_name]}，这样 /load 返回 {team: {...}} 后前端读 data.team.roster 才对。
                data = {"trainer_name": "", "roster": roster}
            else:
                # 前端未携带 roster（旧请求）时不回退 temp.json——那会把加载的槽位整份复制成新槽位。
                raise ValueError("请求未携带 roster 数据")
            if slot_id:
                dst = TEAM_DIR / f"{slot_id}.json"
                if dst.exists():
                    with open(dst, encoding="utf-8") as f:
                        existing = json.load(f)
                    data["slot_name"] = existing.get("slot_name", slot_id)
                else:
                    data["slot_name"] = slot_name or slot_id
            else:
                nums = [int(p.stem) for p in TEAM_DIR.glob("*.json") if p.stem.isdigit()]
                new_id = max(nums, default=0) + 1
                slot_id = str(new_id)
                dst = TEAM_DIR / f"{slot_id}.json"
                data["slot_name"] = slot_name
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return jsonify({"success": True, "slot_id": slot_id, "slot_name": data["slot_name"]})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/teams/<slot_id>", methods=["DELETE"])
    def delete_team_slot(slot_id):
        try:
            path = TEAM_DIR / f"{slot_id}.json"
            if not path.exists():
                return jsonify({"success": False, "error": "不存在"}), 404
            path.unlink()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/teams/generate", methods=["POST"])
    def generate_team():
        """从截图提取 OCR 结果，保存到 draft.json，返回草稿供编辑"""
        try:
            moves_path = SCREENSHOTS_DIR / "moves.png"
            stats_path = SCREENSHOTS_DIR / "stats.png"

            if not moves_path.exists() or not stats_path.exists():
                return jsonify({"success": False, "error": "缺少截图。请先截取页面1（moves）和页面2（stats）"}), 400

            detect_cards, move_cards, stat_cards = parse_team_init(str(moves_path), str(stats_path), debug=True)

            # 校验前移：对 OCR 草稿做中文名模糊纠错，draft.json 保存经过校验的一版
            builder = PokemonBuilder()
            move_cards = builder.correct_move_cards(move_cards)

            draft = {
                "detect_cards": detect_cards,
                "move_cards": move_cards,
                "stat_cards": stat_cards
            }

            draft_path = TEAM_DIR / "draft.json"
            TEAM_DIR.mkdir(parents=True, exist_ok=True)
            with open(draft_path, "w", encoding="utf-8") as f:
                json.dump(draft, f, ensure_ascii=False, indent=2)

            return jsonify({
                "success": True,
                "draft": draft
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/teams/build", methods=["POST"])
    def build_team():
        """从编辑后的卡数据生成最终队伍，保存到 temp.json"""
        try:
            body = request.get_json() or {}
            detect_cards = body.get("detect_cards", [])
            move_cards = body.get("move_cards", [])
            stat_cards = body.get("stat_cards", [])

            if not (detect_cards and move_cards and stat_cards):
                return jsonify({"success": False, "error": "缺少卡数据"}), 400

            builder = PokemonBuilder()
            roster = []
            for dc, mc, sc in zip(detect_cards, move_cards, stat_cards):
                pokemon = builder.build_pokemon(
                    detect_data=dc,
                    moves_data=mc,
                    stats_data=sc,
                    language="zh"
                )
                roster.append(pokemon)

            team_data = {
                "trainer_name": "",
                "roster": [p.to_dict() if hasattr(p, 'to_dict') else p for p in roster]
            }

            output_path = TEAM_DIR / "temp.json"
            TEAM_DIR.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(team_data, f, ensure_ascii=False, indent=2)

            return jsonify({
                "success": True,
                "team": team_data,
                "slot": "temp"
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/pokemon/detect-card/<slug>")
    def pokemon_detect_card(slug):
        """根据 slug 查询宝可梦的 detect_card 数据"""
        try:
            detector = _get_detector()
            card = detector.get_detect_card_by_slug(slug)
            if card:
                return jsonify({"success": True, "card": card})
            return jsonify({"success": False, "error": "slug 不存在"}), 404
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/pokemon/by-name-zh/<name_zh>")
    def pokemon_by_name_zh(name_zh):
        """根据中文名查询宝可梦，返回所有匹配的variants（用于form下拉）"""
        try:
            detector = _get_detector()
            db = detector.db
            name_en = db.name_zh_to_en(name_zh)
            if not name_en:
                return jsonify({"success": False, "error": f"中文名 '{name_zh}' 不存在"}), 404

            variants = detector.get_variants_by_name(name_en)
            if not variants:
                return jsonify({"success": False, "error": f"英文名 '{name_en}' 不存在"}), 404

            result = []
            for v in variants:
                sprite_filename = v.sprite_filename
                sprite_key = f"sprites/champions/{sprite_filename}" if sprite_filename else None
                result.append({
                    "id": v.id,
                    "name": v.name,
                    "slug": v.slug,
                    "form": v.form or "",
                    "sprite_key": sprite_key,
                    "types": v.types,
                })
            return jsonify({"success": True, "variants": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/pokemon/detect-card-by-name-form/<name_zh>/<form>")
    def pokemon_detect_card_by_name_form(name_zh, form):
        """根据中文名和form查询 detect_card"""
        try:
            detector = _get_detector()
            card = detector.get_detect_card_by_name_and_form(name_zh, form if form != "_none" else "")
            if card:
                return jsonify({"success": True, "card": card})
            return jsonify({"success": False, "error": f"未找到: {name_zh}/{form}"}), 404
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/pokemon/calc-evs/<slug>", methods=["POST"])
    def pokemon_calc_evs(slug):
        """按「种族值 + 最终能力值 + 性格」反推加点，供草稿校对页联动展示。

        body: {stats: {hp..speed}, nature: "attack↑/speed↓"(可为空), evs?: {..OCR读数}}
        性格非空 → 按该性格重算全部加点；性格为空 → 数值推断（同时返回推断性格）
        """
        try:
            body = request.get_json(silent=True) or {}
            stats = body.get("stats") or {}
            builder = PokemonBuilder()
            base_stats = (builder.db.get_pokemon(slug) or {}).get("base_stats") or {}
            if not base_stats:
                return jsonify({"success": False, "error": f"slug '{slug}' 无种族值数据"}), 404
            if not stats:
                return jsonify({"success": False, "error": "缺少能力值"}), 400

            nature_in = (body.get("nature") or "").strip()
            if nature_in:
                pokemon = Pokemon(name=slug, name_zh="", index=0,
                                  stats=stats, base_stats=base_stats, nature=nature_in)
                evs = builder.calc_ev_from_stats(pokemon)
                return jsonify({"success": True, "nature": nature_in, "evs": evs})

            nature, evs, warnings = builder.infer_nature_and_evs(
                base_stats, stats, body.get("evs") or {})
            return jsonify({"success": True, "nature": nature, "evs": evs,
                            "warnings": warnings})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/pokemon/rebuild", methods=["POST"])
    def rebuild_pokemon():
        """根据 slug 重建宝可梦完整数据（对手队伍场景）"""
        try:
            data = request.get_json() or {}
            slug = data.get("slug", "").strip()
            if not slug:
                return jsonify({"success": False, "error": "缺少 slug"}), 400

            detector = _get_detector()
            card = detector.get_detect_card_by_slug(slug)
            if not card:
                return jsonify({"success": False, "error": f"slug '{slug}' 不存在"}), 404

            builder = PokemonBuilder()
            pokemon = builder.build_pokemon(detect_data=card)

            return jsonify({
                "success": True,
                "pokemon": pokemon.to_dict()
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/teams/generate-opponent", methods=["POST"])
    def generate_opponent_team():
        """从对方队伍截图生成队伍，保存到 data/opp_team/temp.json。
        同时按识别出的 6 只宝可梦匹配已收录队伍（team_detail.form_ids），
        按 Team.Date_Shared 降序最多返回 5 个，供前端切换。"""
        try:
            screenshot_path = OPP_SCREENSHOTS_DIR / "team.png"

            if not screenshot_path.exists():
                return jsonify({"success": False, "error": "缺少对方队伍截图。请先截取对方队伍"}), 400

            team, detect_cards = detect_opponents_team_with_cards(str(screenshot_path), debug=True)

            # 用识别出的 slug 匹配已收录队伍（失败不阻塞队伍生成，退化为现有逻辑）
            match_result = {"matched": False, "form_ids": None, "teams": []}
            try:
                match_result = match_teams_from_slugs(
                    [c.get("slug", "") for c in detect_cards],
                    builder=PokemonBuilder())
            except Exception as e:
                print(f"[warn] 已收录队伍匹配失败，跳过: {e}")

            team_data = {
                "trainer_name": team.get("trainer_name", ""),
                "roster": [p.to_dict() if hasattr(p, 'to_dict') else p for p in team.get("roster", [])]
            }
            form_ids, matched_teams = _build_matched_teams_payload(match_result)

            output_path = OPP_TEAM_DIR / "temp.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            team_data["form_ids"] = form_ids
            team_data["matched_teams"] = matched_teams
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(team_data, f, ensure_ascii=False, indent=2)

            return jsonify({
                "success": True,
                "team": team_data,
                "slot": "temp",
                "form_ids": form_ids,
                "matched_teams": matched_teams,
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/teams/match-opponent", methods=["POST"])
    def match_opponent_team():
        """前端手动修正对方宝可梦后，根据 6 只 slug 重新匹配已收录队伍。
        body: {"slugs": ["dragonite", ...]}；返回 {form_ids, matched_teams}。
        同步刷新 data/opp_team/temp.json 中的匹配结果（保留原 roster）。"""
        try:
            body = request.get_json(silent=True) or {}
            slugs = body.get("slugs") or []
            if not slugs:
                return jsonify({"success": False, "error": "缺少 slugs"}), 400

            match_result = {"matched": False, "form_ids": None, "teams": []}
            try:
                match_result = match_teams_from_slugs(slugs, builder=PokemonBuilder())
            except Exception as e:
                print(f"[warn] 已收录队伍匹配失败，跳过: {e}")

            form_ids, matched_teams = _build_matched_teams_payload(match_result)

            # 同步刷新 temp.json 的匹配结果（保留原 roster）
            output_path = OPP_TEAM_DIR / "temp.json"
            try:
                if output_path.exists():
                    team_data = json.loads(output_path.read_text(encoding="utf-8"))
                else:
                    team_data = {"trainer_name": "", "roster": []}
                team_data["form_ids"] = form_ids
                team_data["matched_teams"] = matched_teams
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    json.dumps(team_data, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"[warn] temp.json 刷新失败: {e}")

            return jsonify({
                "success": True,
                "form_ids": form_ids,
                "matched_teams": matched_teams,
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    ## 该方法已弃用 
    @app.route("/api/damage/range", methods=["GET", "POST"])
    def damage_range():
        """点击我方技能后，返回该技能对对方全队的伤害范围。"""
        try:
            body = request.get_json(silent=True) or {}
            if request.method == "GET" and not body:
                payload = request.args.get("payload", "")
                body = json.loads(payload) if payload else {}
            attacker = body.get("attacker") or {}
            move_index = _to_int(body.get("move_index"), -1)
            opp_team = body.get("opp_team") or []
            battle_mode = body.get("battle_mode") or "double"
            if battle_mode not in ("single", "double"):
                battle_mode = "double"

            moves = attacker.get("moves") or []
            if move_index < 0 or move_index >= len(moves):
                return jsonify({"success": False, "error": "无效的技能索引"}), 400

            move = moves[move_index]
            if not move or move.get("power") is None:
                return jsonify({"success": False, "error": "该技能非伤害技能"}), 400
            is_spread = _is_spread_move(move)
            is_guaranteed_critical = _is_guaranteed_critical_move(move)

            rows = []
            for opp in opp_team:
                range_info = _compute_damage_range(attacker, opp, move)
                if range_info is None:
                    continue
                range_info = _apply_guaranteed_critical_modifier(range_info, is_guaranteed_critical)
                range_info = _apply_spread_modifier(range_info, battle_mode, is_spread)
                hp_min, hp_max = _stat_min_max((opp.get("stats") or {}).get("hp"))
                rows.append({
                    "opp_name": opp.get("name", ""),
                    "opp_name_zh": opp.get("name_zh", ""),
                    "opp_types": opp.get("types", []),
                    "opp_hp_min": hp_min,
                    "opp_hp_max": hp_max,
                    "range": range_info,
                })

            rows.sort(
                key=lambda item: (
                    item["range"]["hp_pct_max"],
                    item["range"]["hp_pct_min"],
                ),
                reverse=True,
            )
            return jsonify({
                "success": True,
                "move_name": move.get("name", ""),
                "move_name_zh": move.get("name_zh", ""),
                "move_priority": _to_int(move.get("priority"), 0),
                "battle_mode": battle_mode,
                "is_spread_move": is_spread,
                "is_guaranteed_critical": is_guaranteed_critical,
                "is_multi_hit": _is_multi_hit_move(move),
                "rows": rows,
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/get-layout-config", methods=["GET"])
    def get_layout_config():
        """获取卡片布局配置"""
        try:
            config_path = CONFIG_DIR / "card_layout.json"

            if not config_path.exists():
                return jsonify({
                    "success": False,
                    "error": f"Config file not found: {config_path}"
                }), 404

            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            return jsonify({
                "success": True,
                "data": config_data
            }), 200

        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route("/config/<filename>", methods=["GET"])
    def get_config_file(filename):
        """获取配置文件"""
        return send_from_directory(CONFIG_DIR, filename)

    @app.route("/api/save-layout-config", methods=["POST"])
    def save_layout_config():
        """保存卡片布局配置到 card_layout.json"""
        try:
            config_data = request.get_json()
            if not config_data:
                return jsonify({"success": False, "error": "Invalid JSON"}), 400

            config_path = CONFIG_DIR / "card_layout.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            return jsonify({
                "success": True,
                "message": f"Config saved successfully",
                "config": config_data
            }), 200

        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/save-opponent-layout-config", methods=["POST"])
    def save_opponent_layout_config():
        """保存对方队伍布局配置到 opponent_team_layout.json"""
        try:
            config_data = request.get_json()
            if not config_data:
                return jsonify({"success": False, "error": "Invalid JSON"}), 400

            config_path = CONFIG_DIR / "opponent_team_layout.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            return jsonify({
                "success": True,
                "message": f"Config saved successfully",
                "config": config_data
            }), 200

        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    return app


def main():
    parser = argparse.ArgumentParser(description="采集卡视频预览服务器 + API")
    parser.add_argument("--port", type=int, default=8765, help="服务器端口")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    # 后台预热 PokemonDetector（避免首次 API 调用阻塞）
    threading.Thread(target=_get_detector, daemon=True).start()

    app = create_app()
    print(f">> 采集卡预览服务器启动: http://localhost:{args.port}")
    print(f"[dir] 截图保存位置: {SCREENSHOTS_DIR}")
    app.run(host="0.0.0.0", port=args.port, debug=args.debug, use_reloader=False)


if __name__ == "__main__":
    main()
