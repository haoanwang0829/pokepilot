"""
从 pokechamdb.com 爬取 Pokemon Champions Tournament 每只宝可梦的对战数据（含 EVs）。

参照 pikalytics_cache.json 的结构，额外添加 evs / natures 字段。

输出 data/pokechamdb_cache.json，格式：
  {
    "venusaur": {
      "slug": "venusaur",
      "rank": 19,
      "moves":     [{"name": "Sludge Bomb", "pct": 93.4}, ...],
      "items":     [{"name": "Venusaurite",  "pct": 65.8}, ...],
      "abilities": [{"name": "Chlorophyll",  "pct": 95.3}, ...],
      "natures":   [{"name": "Modest",       "pct": 79.5}, ...],
      "evs":       [{"hp": 2, "atk": 0, "def": 0, "spA": 32, "spD": 0, "spe": 32, "pct": 16.0}, ...],
      "teammates": [{"name": "Basculegion",  "pct": 0}, ...]
    },
    ...
  }

用法:
    python -m pokepilot.data.build_pokechamdb
    python -m pokepilot.data.build_pokechamdb --all
    python -m pokepilot.data.build_pokechamdb --slug venusaur
    python -m pokepilot.data.build_pokechamdb --resume
"""

import argparse
import json
import re
import time
from pathlib import Path

import cloudscraper

_ROOT         = Path(__file__).resolve().parent.parent.parent
_ROSTER_PATH  = _ROOT / "data" / "champions_roster.json"
_OUT_PATH     = _ROOT / "data" / "pokechamdb_cache.json"
_BASE_URL     = "https://pokechamdb.com/en/pokemon"
_RANKING_URL  = "https://pokechamdb.com/zh-Hans?format=double&season=M-2&view=pokemon"
_DELAY        = 1.5

_RSC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/x-component",
    "RSC": "1",
    "Next-Router-State-Tree": (
        '%5B%22%22%2C%7B%22children%22%3A%5B%22en%22%2C%7B%22children%22%3A%5B%22pokemon%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D'
    ),
}

_HTML_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

# ── 排名列表解析 ──────────────────────────────────────────────────────────

_RANKING_CACHE: dict[str, int] = {}


def _fetch_ranking_list() -> dict[str, int]:
    """从 pokechamdb.com 排名页面抓取所有宝可梦的使用率排名。

    Returns:
        dict[str, int]: slug -> rank 的映射（rank 从 1 开始）。
    """
    global _RANKING_CACHE
    if _RANKING_CACHE:
        return _RANKING_CACHE

    scraper = _get_scraper()
    try:
        r = scraper.get(_RANKING_URL, headers=_HTML_HEADERS, timeout=30)
    except Exception as e:
        print(f"  排名页网络错误: {e}")
        return {}

    if r.status_code != 200:
        print(f"  排名页 HTTP {r.status_code}")
        return {}

    result = _parse_ranking_list(r.text)
    _RANKING_CACHE = result
    print(f"  排名列表: {len(result)} 只宝可梦")
    return result


def _parse_ranking_list(html: str) -> dict[str, int]:
    """从排名页 HTML 中解析 slug -> rank 的映射。"""
    result: dict[str, int] = {}

    main_m = re.search(r'<main[^>]*>(.*)</main>', html, re.DOTALL)
    if not main_m:
        return result
    main_content = main_m.group(1)

    for a_m in re.finditer(
        r'<a\s[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        main_content, re.DOTALL
    ):
        href = a_m.group(1)
        inner = a_m.group(2)

        if 'pokemon/' not in href:
            continue

        slug_m = re.search(r'/zh-Hans/pokemon/([^?/]+)', href)
        if not slug_m:
            continue
        slug = slug_m.group(1)

        rank_m = re.search(
            r'<span[^>]*class="[^"]*font-display[^"]*"[^>]*>\s*(\d+)\s*</span>',
            inner
        )
        if not rank_m:
            continue
        rank = int(rank_m.group(1))
        result[slug] = rank

    return result


# ── RSC payload 解析 ─────────────────────────────────────────────────────────


def _find_enclosing_json(text: str, pos: int) -> str | None:
    """从 pos 位置向前找 '{'，向后匹配 '}'，提取 JSON 字符串。"""
    obj_start = text.rfind('{', 0, pos)
    if obj_start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(obj_start, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == '\\':
            esc = True
            continue
        if ch == '"' and not esc:
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[obj_start:i + 1]
    return None


def _extract_usage_panels(text: str) -> dict[str, list[dict]]:
    """从 RSC payload 中提取所有 UsagePanel (iconLabel + entries + displayNames)。"""
    icon_map = {
        "MOVES": "moves", "ITEMS": "items",
        "ABILITY": "abilities", "NATURE": "natures",
        "PARTNER": "teammates",
    }
    result: dict[str, list[dict]] = {}

    for m in re.finditer(r'"iconLabel":"([^"]+)"', text):
        label = m.group(1)
        if label not in icon_map:
            continue
        obj_str = _find_enclosing_json(text, m.start())
        if obj_str is None:
            continue
        try:
            obj = json.loads(obj_str)
        except json.JSONDecodeError:
            continue

        entries = obj.get("entries", [])
        display_names = obj.get("displayNames", {})

        data_key = icon_map[label]
        items = []
        for e in entries:
            ja_name = e.get("name", "")
            en_name = display_names.get(ja_name, ja_name)
            pct = e.get("percentage", e.get("pct", 0))
            if ja_name:
                items.append({"name": en_name, "pct": round(pct, 3)})
        result[data_key] = items

    return result


def _extract_ev_table(text: str) -> list[dict]:
    """从 RSC payload 中解析 EV 分布表。"""
    ev_idx = text.find('"EVs"," Distribution Ranking"')
    if ev_idx < 0:
        return []
    section = text[ev_idx:ev_idx + 50000]

    tbody_idx = section.find('"tbody"')
    if tbody_idx < 0:
        return []
    tbody_section = section[tbody_idx:]

    def _extract_val(td, depth=0) -> float:
        if depth > 6:
            return 0.0
        if isinstance(td, (int, float)):
            return float(td)
        if isinstance(td, str):
            try:
                return float(td)
            except (ValueError, TypeError):
                return 0.0
        if isinstance(td, list):
            # 2-element list like ["16.0", "%"] -> first element
            if len(td) == 2 and isinstance(td[0], str):
                try:
                    return float(td[0])
                except (ValueError, TypeError):
                    pass
            if len(td) >= 4:
                nested = td[3]
                if isinstance(nested, dict):
                    return _extract_val(nested.get("children", 0), depth + 1)
                return _extract_val(nested, depth + 1)
            return 0.0
        if isinstance(td, dict):
            return _extract_val(td.get("children", 0), depth + 1)
        return 0.0

    seen = set()
    evs = []
    pos = 0
    while True:
        pos = tbody_section.find('"tr","', pos)
        if pos < 0:
            break

        # 找到 tr 数组的开始 (["$,"tr","N")
        arr_start = tbody_section.rfind('["$', 0, pos)
        if arr_start < 0:
            pos += 1
            continue

        # 配对的 ]
        depth = 0
        in_str = esc = False
        arr_end = -1
        for i in range(arr_start, len(tbody_section)):
            ch = tbody_section[i]
            if esc:
                esc = False
                continue
            if ch == '\\':
                esc = True
                continue
            if ch == '"' and not esc:
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    arr_end = i + 1
                    break

        if arr_end < 0:
            pos += 1
            continue

        try:
            row_arr = json.loads(tbody_section[arr_start:arr_end])
        except json.JSONDecodeError:
            pos += 1
            continue

        if not isinstance(row_arr, list) or len(row_arr) < 4:
            pos += 1
            continue

        children = row_arr[3].get("children", [])
        if not isinstance(children, list) or len(children) != 8:
            pos += 1
            continue

        vals = [_extract_val(td) for td in children]
        hp, atk, defense, spA, spD, spe = (
            int(vals[1]), int(vals[2]), int(vals[3]),
            int(vals[4]), int(vals[5]), int(vals[6]),
        )
        pct = vals[7]

        key = (hp, atk, defense, spA, spD, spe)
        if key not in seen:
            seen.add(key)
            evs.append({
                "hp": hp, "atk": atk, "def": defense,
                "spA": spA, "spD": spD, "spe": spe,
                "pct": round(pct, 3),
            })

        pos += 1

    evs.sort(key=lambda x: x["pct"], reverse=True)
    return evs


def parse_pokemon_data(text: str, slug: str, rank: int | None = None) -> dict | None:
    """从 RSC payload 中提取宝可梦的完整数据。"""
    panels = _extract_usage_panels(text)

    result = {
        "slug": slug,
        "moves": panels.get("moves", []),
        "items": panels.get("items", []),
        "abilities": panels.get("abilities", []),
        "natures": panels.get("natures", []),
        "teammates": panels.get("teammates", []),
        "evs": _extract_ev_table(text),
    }

    if rank is not None:
        result["rank"] = rank

    if not any([result["moves"], result["items"], result["abilities"],
                result["natures"], result["evs"]]):
        return None

    return result


# ── 网络请求 ─────────────────────────────────────────────────────────────────

_scraper = None


def _get_scraper():
    global _scraper
    if _scraper is None:
        _scraper = cloudscraper.create_scraper()
    return _scraper


def fetch_pokemon_rsc(slug: str, rank: int | None = None) -> dict | None:
    url = f"{_BASE_URL}/{slug}?format=double&season=M-2"
    scraper = _get_scraper()
    try:
        r = scraper.get(url, headers=_RSC_HEADERS, timeout=30)
    except Exception as e:
        print(f"  网络错误: {e}")
        return None

    if r.status_code == 404:
        return None
    if r.status_code != 200:
        print(f"  HTTP {r.status_code}")
        return None

    if r.text.startswith("<!DOCTYPE") or "<html" in r.text[:200]:
        return None

    return parse_pokemon_data(r.text, slug, rank=rank)


# ── 主流程 ───────────────────────────────────────────────────────────────────

def build_pokechamdb(slugs: list[str], resume: bool = False) -> dict:
    cache: dict = {}
    if _OUT_PATH.exists():
        try:
            cache = json.loads(_OUT_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    # 只获取排名，不获取全部队伍数据
    ranking = _fetch_ranking_list()
    print(f"  排名数据: {len(ranking)} 只宝可梦")

    ok = skip = fail = 0

    for i, slug in enumerate(slugs, 1):
        if resume and slug in cache:
            skip += 1
            continue

        print(f"[{i}/{len(slugs)}] {slug} ...", end=" ", flush=True)
        rank = ranking.get(slug)
        data = fetch_pokemon_rsc(slug, rank=rank)

        if data:
            cache[slug] = data
            n_moves = len(data.get("moves", []))
            n_evs = len(data.get("evs", []))
            rank_str = f" #{rank}" if rank else ""
            print(f"ok{rank_str}  ({n_moves} moves, {n_evs} evs)")
            ok += 1
        else:
            print("no data / 404")
            fail += 1

        _OUT_PATH.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if i < len(slugs):
            time.sleep(_DELAY)

    print(f"\n完成: 成功={ok}  跳过={skip}  无数据={fail}")
    print(f"已写入: {_OUT_PATH}  ({len(cache)} 条)")
    return cache


def add_rank_to_cache() -> None:
    """为现有缓存中所有宝可梦添加 rank 字段（无需重新抓取）。"""
    if not _OUT_PATH.exists():
        print(f"缓存文件不存在: {_OUT_PATH}")
        return

    cache = json.loads(_OUT_PATH.read_text(encoding="utf-8"))
    ranking = _fetch_ranking_list()
    if not ranking:
        print("无法获取排名数据")
        return

    updated = 0
    for slug, entry in cache.items():
        rank = ranking.get(slug)
        if rank is not None:
            if entry.get("rank") != rank:
                entry["rank"] = rank
                updated += 1
        elif "rank" in entry:
            del entry["rank"]
            updated += 1

    _OUT_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已更新 {updated} 条记录的 rank 字段，共 {len(cache)} 条")


def main():
    parser = argparse.ArgumentParser(description="抓取 pokechamdb.com Champions 数据（含 EVs）")
    parser.add_argument("--all", action="store_true",
                        help="抓取 roster 全部宝可梦（包括 available=False）")
    parser.add_argument("--resume", action="store_true",
                        help="跳过缓存中已有的条目，继续未完成的抓取")
    parser.add_argument("--slug", help="只抓取指定的单只宝可梦（如 venusaur）")
    parser.add_argument("--add-rank", action="store_true",
                        help="为现有缓存添加 rank 字段（无需重新抓取）")
    args = parser.parse_args()

    if args.add_rank:
        add_rank_to_cache()
        return

    if args.slug:
        slugs = [args.slug]
    else:
        roster = json.loads(_ROSTER_PATH.read_text(encoding="utf-8"))["pokemon"]
        if args.all:
            slugs = list(set(
                [p["slug"].replace("-breed", "") for p in roster] +
                [p["name"] for p in roster if p.get("available")]
            ))
        else:
            slugs = [p["slug"].replace("-breed", "") for p in roster if p.get("available")]

    # 去重
    slugs = list(dict.fromkeys(slugs))
    print(f"目标: {len(slugs)} 只宝可梦")
    build_pokechamdb(slugs, resume=args.resume)


if __name__ == "__main__":
    main()
