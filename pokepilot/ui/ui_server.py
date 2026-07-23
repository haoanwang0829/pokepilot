"""
采集卡视频预览服务器 —— 用浏览器 getUserMedia 打开摄像头 + API 服务

用法：
    python -m pokepilot.ui.ui_server --port 8765
"""

import argparse
import io
import json
import shutil
import threading
from math import floor
from pathlib import Path
from flask import Flask, send_file, request, jsonify, send_from_directory
from flask_cors import CORS
from PIL import Image
from pokepilot.detect_team.my_team.parse_team import parse_team_init
from pokepilot.detect_team.opponent_team.detect_opponents import detect_opponents_team
from pokepilot.common.pokemon_detect import get_detector as _get_detector
from pokepilot.common.pokemon_builder import PokemonBuilder

_ROOT = Path(__file__).parent
PROJECT_ROOT = _ROOT.parent.parent
POKEPILOT_DIR = _ROOT.parent  # pokepilot/ 目录
CONFIG_DIR = POKEPILOT_DIR / "config"
SCREENSHOTS_DIR = PROJECT_ROOT / "screenshots" / "team"
OPP_SCREENSHOTS_DIR = PROJECT_ROOT / "screenshots" / "opp_team"
SPRITES_DIR = PROJECT_ROOT / "sprites"
TEAM_DIR = PROJECT_ROOT / "data" / "my_team"
OPP_TEAM_DIR = PROJECT_ROOT / "data" / "opp_team"

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

    @app.route("/data", methods=["GET"])
    def data_page():
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

    @app.route("/api/data/pokemon-detail/<slug>", methods=["GET"])
    def pokemon_data_detail(slug):
        try:
            cache_path = PROJECT_ROOT / "data" / "pokechamdb_cache.json"
            roster_path = PROJECT_ROOT / "data" / "champions_roster.json"
            pokedb_path = PROJECT_ROOT / "data" / "pokedb_cache.json"

            pokechamdb = json.loads(cache_path.read_text(encoding="utf-8"))
            raw = pokechamdb.get(slug)
            if not raw:
                return jsonify({"success": False, "error": f"slug '{slug}' not found"}), 404

            roster_data = json.loads(roster_path.read_text(encoding="utf-8"))
            pokedb = json.loads(pokedb_path.read_text(encoding="utf-8"))

            roster_by_slug = {p["slug"]: p for p in roster_data.get("pokemon", [])}
            name_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get("pokemon", {}).items()}
            move_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get("moves", {}).items()}
            item_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get("items", {}).items()}
            ability_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get("abilities", {}).items()}

            entry = roster_by_slug.get(slug)
            sprite = ""
            if entry and entry.get("sprite"):
                sprite = f"sprites/champions/{entry['sprite']}"
            name_zh = name_zh_map.get(slug, slug)
            base_stats = pokedb.get("pokemon", {}).get(slug, {}).get("base_stats", {})

            def _slug(s): return s.lower().replace(" ", "-").replace("'", "").replace(".", "")
            def _is_damaging(name):
                ms = _slug(name)
                md = pokedb.get("moves", {}).get(ms, {})
                p = md.get("power")
                return p is not None and p > 0
            def _tr(items, m):
                return [{"name": m.get(_slug(i.get("name", ""))) or i["name"], "pct": i["pct"]} for i in items]

            # Build evoforms list
            base_name = (entry or {}).get("name", slug)
            evoforms = []
            for pk in roster_data.get("pokemon", []):
                if pk.get("name", "").lower() != base_name:
                    continue
                if pk["slug"] == slug:
                    continue
                form_val = pk.get("form")
                if form_val and form_val in _EVOFORM_TYPES:
                    pd = pokedb.get("pokemon", {}).get(pk["slug"], {})
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

    @app.route("/api/data/pokemon-list", methods=["GET"])
    def pokemon_data_list():
        try:
            cache_path = PROJECT_ROOT / "data" / "pokechamdb_cache.json"
            roster_path = PROJECT_ROOT / "data" / "champions_roster.json"
            pokedb_path = PROJECT_ROOT / "data" / "pokedb_cache.json"

            pokechamdb = json.loads(cache_path.read_text(encoding="utf-8"))
            roster_data = json.loads(roster_path.read_text(encoding="utf-8"))
            pokedb = json.loads(pokedb_path.read_text(encoding="utf-8"))

            roster_by_slug = {p["slug"]: p for p in roster_data.get("pokemon", [])}
            name_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get("pokemon", {}).items()}

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
            cache_path = PROJECT_ROOT / "data" / "pokechamdb_cache.json"
            roster_path = PROJECT_ROOT / "data" / "champions_roster.json"
            pokedb_path = PROJECT_ROOT / "data" / "pokedb_cache.json"

            pokechamdb = json.loads(cache_path.read_text(encoding="utf-8"))
            roster_data = json.loads(roster_path.read_text(encoding="utf-8"))
            pokedb = json.loads(pokedb_path.read_text(encoding="utf-8"))

            roster_by_slug = {p["slug"]: p for p in roster_data.get("pokemon", [])}
            name_zh_map = {k: v.get("name_zh", "") for k, v in pokedb.get("pokemon", {}).items()}
            pokedb_moves = pokedb.get("moves", {})
            move_zh_map = {k: v.get("name_zh", "") for k, v in pokedb_moves.items()}

            my_raw = pokechamdb.get(slug)
            if not my_raw:
                return jsonify({"success": False, "error": f"slug '{slug}' not found"}), 404

            my_roster = roster_by_slug.get(slug, {})
            my_base = pokedb.get("pokemon", {}).get(slug, {}).get("base_stats", {})

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
                opp_base = pokedb.get("pokemon", {}).get(opp_slug, {}).get("base_stats", {})
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
        try:
            temp = TEAM_DIR / "temp.json"
            with open(temp, encoding="utf-8") as f:
                data = json.load(f)
            if slot_id:
                dst = TEAM_DIR / f"{slot_id}.json"
                with open(dst, encoding="utf-8") as f:
                    existing = json.load(f)
                data["slot_name"] = existing.get("slot_name", slot_id)
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
        """从对方队伍截图生成队伍，保存到 data/opp_team/temp.json"""
        try:
            screenshot_path = OPP_SCREENSHOTS_DIR / "team.png"

            if not screenshot_path.exists():
                return jsonify({"success": False, "error": "缺少对方队伍截图。请先截取对方队伍"}), 400

            team = detect_opponents_team(str(screenshot_path), debug=True)

            output_path = OPP_TEAM_DIR / "temp.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            team_data = {
                "trainer_name": team.get("trainer_name", ""),
                "roster": [p.to_dict() if hasattr(p, 'to_dict') else p for p in team.get("roster", [])]
            }
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(team_data, f, ensure_ascii=False, indent=2)

            return jsonify({
                "success": True,
                "team": team_data,
                "slot": "temp"
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
    print(f"🎥 采集卡预览服务器启动: http://localhost:{args.port}")
    print(f"📁 截图保存位置: {SCREENSHOTS_DIR}")
    app.run(host="0.0.0.0", port=args.port, debug=args.debug, use_reloader=False)


if __name__ == "__main__":
    main()
