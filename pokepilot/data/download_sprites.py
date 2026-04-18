"""
从 Bulbagarden Archives 下载 Champions 精灵图（普通 + 闪光）。

用法:
    python -m pokepilot.data.download_sprites              # 普通 + 闪光
    python -m pokepilot.data.download_sprites --normal     # 只下载普通版
    python -m pokepilot.data.download_sprites --shiny      # 只下载闪光版
"""

import argparse
import time
from pathlib import Path

import requests

_ROOT    = Path(__file__).parent.parent.parent
_WIKI_API = "https://archives.bulbagarden.net/w/api.php"

_CATEGORIES = {
    "normal": ("Champions_menu_sprites",       _ROOT / "sprites" / "champions"),
    "shiny":  ("Champions_Shiny_menu_sprites", _ROOT / "sprites" / "champions_shiny"),
}


def iter_category_files(category: str):
    """逐页产出 (filename, url) —— 利用 MediaWiki generator API 自动翻页"""
    params = {
        "action":    "query",
        "generator": "categorymembers",
        "gcmtitle":  f"Category:{category}",
        "gcmtype":   "file",
        "gcmlimit":  "50",
        "prop":      "imageinfo",
        "iiprop":    "url",
        "format":    "json",
    }
    while True:
        r = requests.get(_WIKI_API, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            title = page.get("title", "")
            filename = title.removeprefix("File:")
            ii = page.get("imageinfo", [])
            if ii:
                yield filename, ii[0]["url"]

        cont = data.get("continue")
        if not cont:
            break
        params.update(cont)


def download_category(category: str, out_dir: Path) -> None:
    """下载分类中的所有精灵图"""
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"目标目录: {out_dir}")
    print(f"正在枚举 {category} ...")

    ok = skip = fail = 0
    for filename, url in iter_category_files(category):
        out_path = out_dir / filename

        if out_path.exists():
            skip += 1
            continue

        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            out_path.write_bytes(resp.content)
            print(f"  ✓ {filename}")
            ok += 1
        else:
            print(f"  ✗ {filename}  HTTP {resp.status_code}")
            fail += 1

        time.sleep(0.2)

    print(f"完成: 下载 {ok}，跳过 {skip}，失败 {fail}\n")


def main():
    parser = argparse.ArgumentParser(description="下载 Pokemon Champions 精灵图")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--normal", action="store_true", help="只下载普通版")
    group.add_argument("--shiny", action="store_true", help="只下载闪光版")
    args = parser.parse_args()

    # 决定下载的变体
    if args.normal:
        variants = ["normal"]
    elif args.shiny:
        variants = ["shiny"]
    else:
        variants = ["normal", "shiny"]

    # 下载
    for variant in variants:
        if variant != "normal":
            print("=" * 50)
        category, out_dir = _CATEGORIES[variant]
        download_category(category, out_dir)


if __name__ == "__main__":
    main()
