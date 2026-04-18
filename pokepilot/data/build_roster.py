"""
从 Bulbapedia 爬取 Pokemon Champions 完整 roster，包含所有 form、Mega、地区变体。

输出 data/champions_roster.json，格式：
  {
    "pokemon": [
      {"id": 38, "name": "ninetales", "form": null,    "slug": "ninetales",       "types": ["fire"],         "available": true,  "version": "1.0.0"},
      {"id": 38, "name": "ninetales", "form": "alola",  "slug": "ninetales-alola", "types": ["ice","fairy"],   "available": true,  "version": "1.0.2"},
      ...
    ]
  }

用法:
    python -m pokepilot.data.build_roster
    python -m pokepilot.data.build_roster --dry-run   # 只打印，不写文件
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

_URL       = "https://bulbapedia.bulbagarden.net/wiki/List_of_Pok%C3%A9mon_in_Pok%C3%A9mon_Champions"
_ROOT      = Path(__file__).parent.parent.parent
_OUT_PATH  = _ROOT / "data" / "champions_roster.json"
_SPRITE_DIRS = {
    "normal": _ROOT / "sprites" / "champions",
    "shiny":  _ROOT / "sprites" / "champions_shiny",
}


# ── form 名称 → slug 片段 ───────────────────────────────────────────────────────
# 按"最长匹配优先"处理，避免 "Alolan Form" 被部分匹配

_FORM_TOKENS = [
    # 地区 form
    ("alolan form",   "alola"),
    ("galarian form", "galar"),
    ("hisuian form",  "hisui"),
    ("paldean form",  "paldea"),
    # Mega（带字母后缀的先匹配）
    ("mega x",        "mega-x"),
    ("mega y",        "mega-y"),
    ("mega",          "mega"),
    # Rotom appliance（形如 "Heat Rotom" — 先去掉 base name 再处理）
    # 其他复合 form 用通用规则处理
]


def _filename_to_id_form(filename: str) -> tuple[int, str] | None:
    """
    从 sprite 文件名提取 ID 和 form。
    例：
      "Menu CP 0003.png" → (3, "")
      "Menu CP 0003-Mega.png" → (3, "mega")
      "Menu CP 0003 shiny.png" → (3, "")  （shiny 单独处理）
      "Menu CP 0025-Alola.png" → (25, "alola")
    """
    # 先去掉 " shiny" 后缀（如果存在）
    base_name = filename.replace(" shiny", "").replace(" Shiny", "")

    # 提取 ID 和 form（用 - 分隔）
    m = re.search(r"Menu\s+CP\s+(\d{4})(?:-(.+?))?\.png", base_name, re.IGNORECASE)
    if not m:
        return None

    poke_id = int(m.group(1))
    form_text = m.group(2) or ""
    form = form_text.lower().replace(" ", "-") if form_text else ""

    return (poke_id, form)


def _form_slug(base_name: str, form_text: str) -> str:
    """
    把 Bulbapedia 的 form 文字转成 slug 片段。
    例：
      base="charizard", form_text="Mega Charizard X" → "mega-x"
      base="ninetales",  form_text="Alolan Form"      → "alola"
      base="rotom",      form_text="Heat Rotom"        → "heat"
      base="tauros",     form_text="Paldean Combat Form" → "paldea-combat"
    """
    t = form_text.lower().strip()

    # 先尝试已知映射（最长优先）
    for pattern, slug in _FORM_TOKENS:
        if pattern in t:
            # 去掉已匹配的已知部分，再清洗残余 base name
            remainder = t.replace(pattern, "").replace(base_name.lower(), "").strip(" -")
            if remainder:
                slug = slug + "-" + re.sub(r"[\s/]+", "-", remainder).strip("-")
            return slug

    # 通用规则：去掉 base name，清理剩余文字
    t = t.replace(base_name.lower(), "").strip()
    # 去掉尾部的 "form" 词
    t = re.sub(r"\bform\b", "", t).strip()
    # 空格/斜杠 → 连字符
    slug = re.sub(r"[\s/]+", "-", t).strip("-")
    return slug if slug else "base"


def _thumb_to_sprite_filename(thumb_url: str) -> str | None:
    """
    从 Bulbapedia 的缩略图 URL 提取本地精灵图文件名。

    例：
      https://archives.bulbagarden.net/media/upload/thumb/4/40/Menu_CP_0009.png/60px-Menu_CP_0009.png
      → "Menu CP 0009.png"

    步骤：
      1. 去掉 /thumb/ 路径段，得到完整 URL
      2. 从 URL 中提取文件名（最后的路径段）
      3. 将下划线替换为空格（与 MediaWiki API 下载命名一致）
    """
    if not thumb_url:
        return None

    try:
        # 去掉 /thumb/ 和后续的 /NNpx-filename 后缀
        # 原始: .../thumb/4/40/Menu_CP_0009.png/60px-Menu_CP_0009.png
        if "/thumb/" in thumb_url:
            # 提取 /thumb/ 前面的路径，拼回完整 URL
            parts = thumb_url.split("/thumb/")
            base_path = parts[0]
            thumb_part = parts[1]
            # thumb_part = "4/40/Menu_CP_0009.png/60px-Menu_CP_0009.png"
            # 找到文件名（最后一个 / 前的部分）
            # 但这里的问题是有两个文件名，我们要第一个
            # 实际上：base/thumb/hash_dir/original_filename/thumb_sizes/filename
            # 所以直接提取倒数第二个 / 到倒数第一个 / 之间的部分
            # 或者更简单：原始文件名在第一个完整路径中
            # 让我们按照格式分析：thumb_part = "4/40/filename/60px-filename"
            # 先找出原始文件名位置
            filename_match = re.search(r"Menu_CP_\d{4}(?:-\w+)?\.png", thumb_url)
            if filename_match:
                url_filename = filename_match.group()
                # 替换下划线为空格（本地文件约定）
                local_filename = url_filename.replace("_", " ")
                return local_filename
        else:
            # 如果不是 thumb URL，直接提取文件名
            url_filename = thumb_url.split("/")[-1]
            local_filename = url_filename.replace("_", " ")
            return local_filename
    except Exception:
        return None


def _parse_table(soup: BeautifulSoup) -> list[dict]:
    results   = []
    seen_slugs: set[str] = set()
    last_poke_id = None  # 用于处理 rowspan 导致的空 dex 列

    # 找所有包含 "Ndex" 标题的表格（主表 + Mega + Other forms），按顺序合并
    data_tables = [
        tbl for tbl in soup.find_all("table")
        if (th := tbl.find("th")) and "ndex" in th.get_text(strip=True).lower()
    ]
    if not data_tables:
        raise RuntimeError("找不到数据表格，页面结构可能已变更")

    for table in data_tables:
        row_num = 0
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            row_num += 1

            # ── 列 0：Dex 编号 ─────────────────────────────────────────────
            dex_text = cells[0].get_text(strip=True).lstrip("#")
            if dex_text.isdigit():
                poke_id = int(dex_text)
                last_poke_id = poke_id
                name_cell_idx = 1  # dex 存在时，name 在 cells[1]
                type_start = 2     # type 从 cells[2] 开始
            elif last_poke_id is not None:
                # dex 列为空（rowspan），使用上一个 ID
                poke_id = last_poke_id
                name_cell_idx = 0  # dex 不存在时，name 在 cells[0]
                type_start = 1     # type 从 cells[1] 开始
            else:
                continue

            # ── 列 name：名字 + form ──────────────────────────────────
            name_cell = cells[name_cell_idx]
            links = name_cell.find_all("a")
            if not links:
                continue
            base_name = links[0].get_text(strip=True).lower()

            # form 文字在 <br/> 后面（可能在 <small> 标签或纯文本）
            form_text = None

            # 方法1：尝试 <small> 标签
            small = name_cell.find("small")
            if small:
                ft = small.get_text(strip=True)
                if ft.lower() != base_name:
                    form_text = ft

            # 方法2：如果没找到 <small>，从 <br/> 后面的文本提取
            if not form_text:
                br = name_cell.find("br")
                if br:
                    # 获取 <br/> 之后的所有文本
                    text_after_br = ""
                    current = br.next_sibling
                    while current:
                        if isinstance(current, str):
                            text_after_br += current
                        elif hasattr(current, "get_text"):
                            text_after_br += current.get_text()
                        current = current.next_sibling

                    form_text = text_after_br.strip()
                    if not form_text or form_text.lower() == base_name:
                        form_text = None

            if form_text:
                form_slug_part = _form_slug(base_name, form_text)
                form_val = form_slug_part
                slug     = f"{base_name}-{form_slug_part}"
            else:
                form_val = None
                slug     = base_name

            # 跨表去重（同一 slug 已收录则跳过）
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            # ── 属性、可用、版本 ──────────────────────────────────────
            # 版本在最后一列，可用在倒数第二列，属性在中间
            version    = cells[-1].get_text(strip=True)
            avail_text = cells[-2].get_text(strip=True).lower()
            available  = "yes" in avail_text

            # 属性：从 type_start 到倒数第 3（可能 1～2 列）
            types = []
            for c in cells[type_start:-2]:
                for a in c.find_all("a"):
                    t = a.get_text(strip=True).lower()
                    if t:
                        types.append(t)

            # ── 提取精灵图（从 <th> 中的 <img> 标签） ──────────────────────────
            sprite_filename = None
            sprite_shiny_filename = None
            ths = row.find_all("th")
            for th in ths:
                img = th.find("img")
                if img:
                    src = img.get("src", "")
                    if src:
                        sprite_filename = _thumb_to_sprite_filename(src)
                        if sprite_filename:
                            # 派生闪光版文件名（添加 " shiny" 在扩展名之前）
                            sprite_shiny_filename = sprite_filename.replace(".png", " shiny.png")
                        break

            results.append({
                "id":        poke_id,
                "name":      base_name,
                "form":      form_val,
                "slug":      slug,
                "types":     types,
                "available": available,
                "version":   version,
                "sprite":    sprite_filename,
                "sprite_shiny": sprite_shiny_filename,
            })

    return results


def build_roster(dry_run: bool = False) -> list[dict]:
    print(f"抓取: {_URL}")
    resp = requests.get(_URL, timeout=20,
                        headers={"User-Agent": "Mozilla/5.0 pokepilot-bot"})
    resp.raise_for_status()

    soup    = BeautifulSoup(resp.text, "html.parser")
    pokemon = _parse_table(soup)
    print(f"解析完成: {len(pokemon)} 条记录")

    # 预览
    print("\n前 5 个爬取结果：")
    for p in pokemon[:5]:
        sprite_info = p.get('sprite', '')
        print(f"  id={p['id']}, name={p['name']}, slug={p['slug']}, types={p['types']}, sprite={sprite_info}")
    print("  ...")

    # 检查 Ninetales 及其变体
    ninetales_entries = [p for p in pokemon if "ninetales" in p["name"].lower()]
    if ninetales_entries:
        print(f"\n调试: Ninetales 相关条目 ({len(ninetales_entries)} 个):")
        for p in ninetales_entries:
            print(f"  {p['id']:4d}  {p['slug']:30s}  form={p.get('form')}")

    if not dry_run:
        data = {
            "_source":  _URL,
            "_updated": str(date.today()),
            "_note":    "Auto-generated. Includes all forms, Mega, regional variants.",
            "pokemon":  pokemon,
        }
        _OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入: {_OUT_PATH}  ({len(pokemon)} 条)")
    else:
        print("\n[dry-run] 不写文件")

    return pokemon


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只解析，不写文件")
    args = parser.parse_args()
    build_roster(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
