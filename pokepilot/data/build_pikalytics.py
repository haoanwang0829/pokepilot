"""
从 Pikalytics 爬取 Pokemon Champions Tournament 每只宝可梦的对战数据。

输出 data/pikalytics_cache.json，格式：
  {
    "venusaur": {
      "slug": "venusaur",
      "moves":     [{"name": "Sludge Bomb",   "pct": 96.8}, ...],
      "items":     [{"name": "Focus Sash",     "pct": 58.4}, ...],
      "abilities": [{"name": "Chlorophyll",    "pct": 93.6}, ...],
      "teammates": [{"name": "Charizard",      "pct": 81.6}, ...]
    },
    ...
  }

用法:
    python -m pokepilot.data.build_pikalytics              # 只抓 available=True 的
    python -m pokepilot.data.build_pikalytics --all        # 抓全部 roster
    python -m pokepilot.data.build_pikalytics --slug pikachu  # 只抓单只
    python -m pokepilot.data.build_pikalytics --resume     # 跳过已有数据，继续未完成的
"""

import argparse
import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

_ROOT         = Path(__file__).parent.parent.parent
_ROSTER_PATH  = _ROOT / "data" / "champions_roster.json"
_OUT_PATH     = _ROOT / "data" / "pikalytics_cache.json"
_BASE_URL     = "https://www.pikalytics.com/pokedex/championstournaments"
_HEADERS      = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Charset": "utf-8",
    "Referer": "https://www.pikalytics.com/",
}
_DELAY        = 1.0   # 请求间隔（秒），避免频率过高


# ── 解析函数 ──────────────────────────────────────────────────────────────────

def _parse_entries(wrapper, name_class: str) -> list[dict]:
    """从一个 wrapper div 里提取所有 {name, pct} 条目。"""
    if not wrapper:
        return []
    results = []
    for entry in wrapper.find_all("div", class_="pokedex-move-entry-new"):
        name_el = entry.find(class_=name_class)
        pct_el  = entry.find(class_="pokedex-inline-right")
        if not name_el or not pct_el:
            continue
        name = name_el.get_text(strip=True)
        try:
            pct = float(pct_el.get_text(strip=True).rstrip("%"))
        except ValueError:
            continue
        if name:
            results.append({"name": name, "pct": pct})
    return results


def _parse_teammates(soup: BeautifulSoup) -> list[dict]:
    """Teammates 用 <a class='teammate_entry'> 包裹，需要单独处理。"""
    wrapper = soup.find(id="dex_team_wrapper") or soup.find(id="teammate_wrapper")
    if not wrapper:
        return []
    results = []
    for a in wrapper.find_all("a", class_="teammate_entry"):
        name_el = a.find(class_="pokedex-inline-text")
        pct_el  = a.find(class_="pokedex-inline-right")
        if not name_el or not pct_el:
            continue
        span = name_el.find("span")
        name = (span or name_el).get_text(strip=True)
        try:
            pct = float(pct_el.get_text(strip=True).rstrip("%"))
        except ValueError:
            continue
        if name:
            results.append({"name": name, "pct": pct})
    return results


def fetch_pokemon(slug: str, session: requests.Session) -> dict | None:
    """
    抓取单只宝可梦的数据。
    返回 dict 或 None（404 / 无数据）。
    """
    url = f"{_BASE_URL}/{slug}"
    try:
        r = session.get(url, headers=_HEADERS, timeout=15)
    except requests.RequestException as e:
        print(f"  网络错误: {e}")
        return None

    if r.status_code == 404:
        return None
    if r.status_code != 200:
        print(f"  HTTP {r.status_code}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    moves     = _parse_entries(soup.find(id="moves_wrapper"),     "pokedex-inline-text-offset")
    items     = _parse_entries(soup.find(id="items_wrapper"),     "pokedex-inline-text")
    abilities = _parse_entries(soup.find(id="abilities_wrapper"), "pokedex-inline-text-offset")
    teammates = _parse_teammates(soup)

    # 如果四个列表全空，可能是 Pikalytics 上没有这只宝可梦的数据
    if not any([moves, items, abilities, teammates]):
        return None

    return {
        "slug":      slug,
        "moves":     moves,
        "items":     items,
        "abilities": abilities,
        "teammates": teammates,
    }


# ── 主流程 ────────────────────────────────────────────────────────────────────

def build_pikalytics(
    slugs: list[str],
    resume: bool = False,
) -> dict:
    """
    爬取 slugs 列表并更新 _OUT_PATH。
    resume=True 时跳过已有条目。
    返回完整 cache dict。
    """
    # 读取已有缓存（续爬用）
    cache: dict = {}
    if _OUT_PATH.exists():
        try:
            cache = json.loads(_OUT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    session = requests.Session()
    ok = skip = fail = 0

    for i, slug in enumerate(slugs, 1):
        if resume and slug in cache:
            skip += 1
            continue

        print(f"[{i}/{len(slugs)}] {slug} ...", end=" ", flush=True)
        data = fetch_pokemon(slug, session)

        if data:
            cache[slug] = data
            n = len(data["moves"])
            print(f"ok  ({n} moves)")
            ok += 1
        else:
            print("no data / 404")
            fail += 1

        # 每抓一条就写回（防中断丢数据）
        _OUT_PATH.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if i < len(slugs):
            time.sleep(_DELAY)

    print(f"\n完成: 成功={ok}  跳过={skip}  无数据={fail}")
    print(f"已写入: {_OUT_PATH}  ({len(cache)} 条)")
    return cache


def main():
    parser = argparse.ArgumentParser(description="抓取 Pikalytics Champions Tournament 数据")
    parser.add_argument("--all",    action="store_true", help="抓取 roster 全部宝可梦（包括 available=False）")
    parser.add_argument("--resume", action="store_true", help="跳过缓存中已有的条目，继续未完成的抓取")
    parser.add_argument("--slug",   help="只抓取指定的单只宝可梦（如 pikachu）")
    args = parser.parse_args()

    if args.slug:
        slugs = [args.slug]
    else:
        roster = json.loads(_ROSTER_PATH.read_text(encoding="utf-8"))["pokemon"]
        if args.all:
            # 每个 slug 只抓一次（roster 里同 slug 不重复，build_roster 已去重）
            slugs = set(list([p["slug"].replace("-breed", "") for p in roster] + \
                    [p["name"] for p in roster if p.get("available")]))
        else:
            slugs = [p["slug"].replace("-breed", "") for p in roster if p.get("available")]

    print(f"目标: {len(slugs)} 只宝可梦")
    build_pikalytics(slugs, resume=args.resume)


if __name__ == "__main__":
    main()
