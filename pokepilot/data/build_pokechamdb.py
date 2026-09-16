"""
从 pokechamdb.com 爬取 Pokemon Champions Tournament 每只宝可梦的对战数据。

纯爬虫脚本，职责：
  1. 从排名 API 获取赛季排名列表 → data/raw/list_{SEASON}_{FORMAT}.json
  2. 从详情 API 获取每只宝可梦的原始数据 → data/raw/pokemon/{slug}.json
  3. 记录最新赛季 ID → data/raw/latest_season.json

输出的 raw 文件保留 API 原始响应（含全赛季×全格式 variants），
由 build_usage_db.py 负责从 raw 文件构建运行时 DB。

用法:
    python -m pokepilot.data.build_pokechamdb --season M-5
    python -m pokepilot.data.build_pokechamdb --season M-5 --format single
    python -m pokepilot.data.build_pokechamdb --seasons M-4,M-5
    python -m pokepilot.data.build_pokechamdb --season M-5 --slug garchomp
    python -m pokepilot.data.build_pokechamdb --season M-5 --force
    python -m pokepilot.data.build_pokechamdb --season M-5 --all
"""

import argparse
import json
import time
from pathlib import Path

import requests

_ROOT = Path(__file__).resolve().parent.parent.parent
_RAW_DIR = _ROOT / "data" / "raw"
_POKEMON_DIR = _RAW_DIR / "pokemon"
_ROSTER_PATH = _ROOT / "data" / "champions_roster.json"
_RANKING_API = "https://pokechamdb.com/snapshots/rankings/{season}/{format}.json"
_DETAIL_API = "https://pokechamdb.com/snapshots/pokemon/{slug}.json"
_DELAY = 1.5

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


# ── 排名列表 ─────────────────────────────────────────────────────────────────


def fetch_ranking_list(fmt: str = "double", season: str = "M-4",
                       save: bool = True) -> list[tuple[str, int]]:
    """从排名 API 获取某赛季/格式的排名列表。

    Args:
        fmt: 对战格式 (double/single)
        season: 赛季 ID (如 M-4, M-5)
        save: 是否同时写入 data/raw/list_{season}_{format}.json

    Returns:
        [(slug, rank), ...] 按排名排序
    """
    url = _RANKING_API.format(season=season, format=fmt)
    try:
        r = requests.get(url, headers=_HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  排名接口错误: {e}")
        return []

    entries = data.get("entries", [])
    actual_format = data.get("format", "")
    if actual_format != fmt:
        print(f"  警告：服务器返回的格式是 '{actual_format}'，请求的是 '{fmt}'")

    result = [(e["pokemonSlug"], e["rank"])
              for e in entries if "pokemonSlug" in e and "rank" in e]

    if save:
        _RAW_DIR.mkdir(parents=True, exist_ok=True)
        list_path = _RAW_DIR / f"list_{season}_{fmt.upper()}.json"
        list_data = {
            "season": season,
            "format": fmt,
            "entries": [{"slug": s, "rank": r} for s, r in result],
        }
        list_path.write_text(
            json.dumps(list_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  排名列表: {len(result)} 只宝可梦 → {list_path.name}")

    return result


# ── 详情数据 ─────────────────────────────────────────────────────────────────


def fetch_pokemon_detail(slug: str, force: bool = False) -> bool:
    """下载并保存某只宝可梦的详情数据（全赛季×全格式 variants）。

    Args:
        slug: 宝可梦 slug (如 garchomp, venusaur-mega)
        force: 强制重新下载（删除本地缓存后重新请求）

    Returns:
        True=成功（已缓存或新下载），False=失败
    """
    _POKEMON_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = _POKEMON_DIR / f"{slug}.json"

    if force and raw_path.exists():
        raw_path.unlink()

    if raw_path.exists():
        return True

    url = _DETAIL_API.format(slug=slug)
    try:
        r = requests.get(url, headers=_HEADERS, timeout=30)
        if r.status_code == 404:
            return False
        r.raise_for_status()
        raw = r.json()
    except Exception as e:
        print(f"  详情接口错误: {e}")
        return False

    raw_path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


# ── 最新赛季记录 ──────────────────────────────────────────────────────────────


def update_latest_season(season: str, fmt: str) -> None:
    """写入 data/raw/latest_season.json 记录当前最新赛季。"""
    path = _RAW_DIR / "latest_season.json"
    data = {"season": season, "format": fmt}
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  最新赛季: {season}/{fmt} → {path.name}")


def read_latest_season() -> tuple[str, str]:
    """读取 data/raw/latest_season.json，不存在则返回默认值。"""
    path = _RAW_DIR / "latest_season.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("season", "M-4"), data.get("format", "double")
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return "M-4", "double"


# ── 名称映射（供 build_usage_db.py 复用）──────────────────────────────────────
# 名称翻译直接查 db/db.db：
#   - 宝可梦/招式/特性：language_map 表（TYPE=name/move/ability），JPN→USA/SCH
#   - 招式/特性/道具：moves/abilities/items 表的 name_j→name_e/name 作兜底
#   - 宝可梦形态名：从日文形态名拆「区域前缀/羅托姆前缀/括号形态」后查基础名
#   - 性格：内置 25 个标准性格（language_map 无 nature 类型）
# 不再依赖 data/pokecham_names.json。

import sqlite3  # noqa: E402

_DB_PATH = _ROOT / "db" / "db.db"
_UNKNOWN_NAMES: dict[str, set[str]] = {}

# 25 个标准性格：日文 → (英文, 中文)
_NATURE_MAP = {
    "がんばりや": ("Hardy", "勤奋"), "さみしがり": ("Lonely", "怕寂寞"),
    "ゆうかん": ("Brave", "勇敢"), "いじっぱり": ("Adamant", "固执"),
    "やんちゃ": ("Naughty", "顽皮"), "ずぶとい": ("Bold", "大胆"),
    "すなお": ("Docile", "坦率"), "のんき": ("Relaxed", "悠闲"),
    "わんぱく": ("Impish", "淘气"), "のうてんき": ("Lax", "乐天"),
    "おくびょう": ("Timid", "胆小"), "せっかち": ("Hasty", "急躁"),
    "まじめ": ("Serious", "认真"), "ようき": ("Jolly", "爽朗"),
    "むじゃき": ("Naive", "天真"), "ひかえめ": ("Modest", "内敛"),
    "おっとり": ("Mild", "慢吞吞"), "れいせい": ("Quiet", "冷静"),
    "てれや": ("Bashful", "害羞"), "うっかりや": ("Rash", "马虎"),
    "おだやか": ("Calm", "温和"), "おとなしい": ("Gentle", "温顺"),
    "なまいき": ("Sassy", "自大"), "しんちょう": ("Careful", "慎重"),
    "きまぐれ": ("Quirky", "浮躁"),
}

# 宝可梦形态：区域前缀 → (英文, 中文)
_REGION_PREFIX = {
    "アローラ": ("Alola", "阿罗拉"), "ガラル": ("Galar", "伽勒尔"),
    "ヒスイ": ("Hisui", "洗翠"), "パルデア": ("Paldea", "帕底亚"),
}
# 寶可夢形態：羅托姆前缀 → 英文（中文同源，如 清洗/加热…）
_ROTOM_PREFIX = {
    "ウォッシュ": ("Wash", "清洗"), "カット": ("Mow", "切割"),
    "ヒート": ("Heat", "加热"), "スピン": ("Fan", "旋转"),
    "フロスト": ("Frost", "结冰"),
}
# 寶可夢形態：括号后缀 → (英文, 中文)
_FORM_SUFFIX = {
    "メス": ("Female", "雌性"), "ロー": ("Low-Key", "低调的样子"),
    "えいえん": ("Eternal", "永恒之花"), "ヒスイ": ("Hisui", "洗翠"),
}
# 帕底亚肯泰罗：括号后缀 → (英文, 中文)
_TAUROS_SUFFIX = {
    "格闘": ("Combat", "斗战种"), "水": ("Aqua", "水澜种"), "炎": ("Blaze", "火炽种"),
}
# 南瓜怪人：括号后缀 → (英文, 中文)。ちゅうだま=标准形态，不加后缀。
_PUMPKABOO_SUFFIX = {
    "おおだま": ("Large", "大尺寸"), "こだま": ("Small", "小尺寸"),
    "ギガだま": ("Super", "特大尺寸"),
}
# 鬃岩狼人：括号后缀 → (英文, 中文)
_LYCANROC_SUFFIX = {
    "たそがれ": ("Dusk", "黄昏的样子"), "まよなか": ("Midnight", "黑夜的样子"),
}

_NAMES_DB_CONN: sqlite3.Connection | None = None


def _load_names_db() -> sqlite3.Connection:
    """打开 db/db.db 只读连接（进程级复用一个）。"""
    global _NAMES_DB_CONN
    if _NAMES_DB_CONN is None:
        _NAMES_DB_CONN = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)
        _NAMES_DB_CONN.row_factory = sqlite3.Row
    return _NAMES_DB_CONN


def _resolve_lang(kind: str, ja_name: str) -> tuple[str, str] | None:
    """language_map 精确查：JPN → (USA, SCH)。kind 取值 name/move/ability。"""
    conn = _load_names_db()
    row = conn.execute(
        "SELECT USA, SCH FROM language_map WHERE TYPE=? AND JPN=?",
        (kind, ja_name),
    ).fetchone()
    return (row["USA"], row["SCH"]) if row else None


def _resolve_table(table: str, ja_name: str) -> tuple[str, str] | None:
    """moves/abilities/items 表按 name_j 查 → (name_e, name)。"""
    conn = _load_names_db()
    row = conn.execute(
        f"SELECT name_e, name FROM {table} WHERE name_j=?",
        (ja_name,),
    ).fetchone()
    return (row["name_e"], row["name"]) if row else None


def _resolve_pokemon(ja_name: str) -> tuple[str, str] | None:
    """日文宝可梦名 → (英文, 中文)。支持基础名与常见形态名。"""
    base = _resolve_lang("name", ja_name)
    if base:
        return base

    text = ja_name.strip().replace("（", "(").replace("）", ")")

    region = None
    for p, v in _REGION_PREFIX.items():
        if text.startswith(p):
            region = v
            text = text[len(p):]
            break

    rotom = None
    if not region:
        for p, v in _ROTOM_PREFIX.items():
            if text.startswith(p):
                rotom = v
                text = text[len(p):]
                break

    suffix = None
    if text.endswith(")") and "(" in text:
        text, tok = text.rstrip(")").rsplit("(", 1)
        suffix = (_TAUROS_SUFFIX.get(tok) or _PUMPKABOO_SUFFIX.get(tok)
                  or _LYCANROC_SUFFIX.get(tok) or _FORM_SUFFIX.get(tok))
        if not suffix and region:
            suffix = (tok, tok)

    base = _resolve_lang("name", text)
    if not base:
        return None

    en, zh = base
    if rotom:
        # 羅托姆形态：英文 base+Wash，中文 前缀式（清洗洛托姆）
        return en + " " + rotom[0], rotom[1] + zh
    if suffix:
        en += " " + (region[0] + " " if region else "") + suffix[0]
        zh += "（" + suffix[1] + "）"
    elif region:
        en += " " + region[0]
        zh += "（" + region[1] + "）"
    return en, zh


def _resolve_name(kind: str, ja_name: str) -> tuple[str, str, str]:
    """把 API 返回的日文名翻译为 (英文, 日文, 中文)。未命中时回退保留日文。"""
    if kind == "natures":
        entry = _NATURE_MAP.get(ja_name)
    elif kind == "pokemon":
        entry = _resolve_pokemon(ja_name)
    else:
        lang_kind = {"moves": "move", "abilities": "ability"}.get(kind)
        entry = (_resolve_lang(lang_kind, ja_name) if lang_kind else None) \
            or (_resolve_table(kind, ja_name) if kind in ("moves", "abilities", "items") else None)
    if entry:
        return entry[0], ja_name, entry[1]
    _UNKNOWN_NAMES.setdefault(kind, set()).add(ja_name)
    return ja_name, ja_name, ""


# ── 主流程 ───────────────────────────────────────────────────────────────────


def _load_roster_slugs() -> set[str]:
    """从 champions_roster.json 加载全部 slug（含 available=False）。"""
    if not _ROSTER_PATH.exists():
        return set()
    try:
        roster = json.loads(_ROSTER_PATH.read_text(encoding="utf-8"))["pokemon"]
        return {p["slug"].replace("-breed", "") for p in roster}
    except (json.JSONDecodeError, KeyError):
        return set()


def run(fmt: str = "double", season: str = "M-4", slug: str | None = None,
        force: bool = False, include_all: bool = False) -> None:
    """执行爬取流程。

    Args:
        fmt: 对战格式
        season: 赛季 ID
        slug: 只抓取指定宝可梦（子串匹配）
        force: 强制重新下载
        include_all: 包含 roster 中 available=False 的宝可梦
    """
    print(f"=== 爬取 {season}/{fmt} ===")

    ranking = fetch_ranking_list(fmt=fmt, season=season)
    if not ranking:
        print("无法获取排名数据，退出")
        return

    if slug:
        ranking = [(s, r) for s, r in ranking if slug in s]
        if not ranking:
            print(f"排名列表中未匹配到 '{slug}'")
            return

    if include_all:
        roster_slugs = _load_roster_slugs()
        known = {s for s, _ in ranking}
        for s in sorted(roster_slugs - known):
            ranking.append((s, None))

    slugs = [s for s, _ in ranking]
    print(f"目标: {len(slugs)} 只宝可梦（season={season}, format={fmt}）")

    ok = skip = fail = 0
    for i, (s, rank) in enumerate(ranking, 1):
        tag = f"#{rank}" if rank else "—"
        print(f"[{i}/{len(slugs)}] {s} ({tag}) ...", end=" ", flush=True)

        if fetch_pokemon_detail(s, force=force):
            status = "cached" if not force and _POKEMON_DIR.exists() else "new"
            print(f"ok ({status})")
            ok += 1
        else:
            print("fail")
            fail += 1

        if i < len(ranking):
            time.sleep(_DELAY)

    print(f"\n完成: 成功={ok}  失败={fail}")
    update_latest_season(season, fmt)


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="从 pokechamdb.com 爬取宝可梦对战数据")
    parser.add_argument("--format", default="double", choices=["single", "double"],
                        help="对战格式（默认 double）")
    parser.add_argument("--season", default="M-4",
                        help="赛季 ID（如 M-4, M-5）")
    parser.add_argument("--seasons",
                        help="逗号分隔的多赛季列表（如 M-4,M-5），依次执行")
    parser.add_argument("--slug", help="只抓取匹配的宝可梦（子串匹配）")
    parser.add_argument("--force", action="store_true",
                        help="强制重新下载（忽略本地 raw 缓存）")
    parser.add_argument("--all", action="store_true",
                        help="包含 roster 中 available=False 的宝可梦")
    args = parser.parse_args()

    seasons = [s.strip() for s in args.seasons.split(",")] if args.seasons else [args.season]

    for season in seasons:
        run(fmt=args.format, season=season, slug=args.slug,
            force=args.force, include_all=args.all)


if __name__ == "__main__":
    main()
