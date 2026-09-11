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

_NAMES_PATH = _ROOT / "data" / "pokecham_names.json"
_NAMES_DB: dict | None = None
_UNKNOWN_NAMES: dict[str, set[str]] = {}


def _load_names_db() -> dict:
    global _NAMES_DB
    if _NAMES_DB is None:
        _NAMES_DB = json.loads(_NAMES_PATH.read_text(encoding="utf-8"))
    return _NAMES_DB


def _resolve_pokemon_slug(name: str, index: dict[str, str], alias: dict[str, str],
                          suffix: dict[str, str]) -> str | None:
    """日文宝可梦名 → slug，复刻站点模块 7851 的 H0() 归一化逻辑。"""
    if name in index:
        return index[name]

    s = name.strip().replace("（", "(").replace("）", ")")
    s = alias.get(s, s)
    for k, v in suffix.items():
        s = s.replace(k, v)
    s = alias.get(s, s)
    if s in index:
        return index[s]

    for k, v in suffix.items():
        if s.startswith(k):
            candidate = s[len(k):] + "(" + v + ")"
            if candidate in index:
                return index[candidate]

    for key, val in index.items():
        if key == s or key.startswith(s):
            return val
    return None


def _resolve_name(kind: str, ja_name: str) -> tuple[str, str, str]:
    """把 API 返回的日文名翻译为 (英文, 日文, 中文)。未命中时回退保留日文。"""
    db = _load_names_db()
    index = db["ja_index"][kind]
    if kind == "pokemon":
        slug = _resolve_pokemon_slug(
            ja_name, index, db["pokemon_alias"], db["pokemon_form_suffix"]
        )
    else:
        slug = index.get(ja_name)
    entry = db[kind].get(slug) if slug else None
    if entry:
        return entry["en"], entry["ja"], entry["zh"]
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
