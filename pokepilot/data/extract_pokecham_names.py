"""
从 pokechamdb.com 的前端 webpack 分包中抽取 宝可梦/招式/道具/特性/性格 的
英/日/中 名称映射，输出 data/pokecham_names.json。

数据来源（data/mapping/*.js）：
  - 26-*.js   模块 7769：道具表 [{slug, ja, ...}]
  - 534-*.js  模块 7851：宝可梦 slug→日文 + 形态名别名/后缀修正
              模块 9096：性格 日文→英/中、招式/特性 slug→日文 + 修正表、道具修正表
              模块 9416：中文名表（宝可梦 Fi / 招式 Ls / 道具 HX / 特性 IO）

英文名规则与站点一致：slug 转 Title Case（body-slam → Body Slam）。

输出 data/pokecham_names.json，格式：
  {
    "meta": {"source": ..., "generated_at": ...},
    "pokemon":   {"garchomp": {"en": "Garchomp", "ja": "ガブリアス", "zh": "烈咬陆鲨"}, ...},
    "moves":     {"earthquake": {"en": "Earthquake", "ja": "じしん", "zh": "地震"}, ...},
    "items":     {"leftovers": {"en": "Leftovers", "ja": "たべのこし", "zh": "吃剩的东西"}, ...},
    "abilities": {"rough-skin": {"en": "Rough Skin", "ja": "さめはだ", "zh": "粗糙皮肤"}, ...},
    "natures":   {"adamant": {"en": "Adamant", "ja": "いじっぱり", "zh": "固执"}, ...},
    "ja_index":  {"moves": {"じしん": "earthquake", ...}, "items": ..., "abilities": ..., "natures": ..., "pokemon": ...},
    "pokemon_alias":       {"フラエッテ": "フラエッテ(えいえん)", ...},
    "pokemon_form_suffix": {"霊獣": "れいじゅう", ...}
  }

用法:
    python -m pokepilot.data.extract_pokecham_names
"""

import json
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_MAPPING_DIR = _ROOT / "data" / "mapping"
_OUT_PATH = _ROOT / "data" / "pokecham_names.json"

# 各分包文件名
_F26 = "26-28f2611f766f4514.js"
_F534 = "534-ec63c932371f2141.js"


# ── 轻量 JS 字面量解析（仅支持扁平 string/number 键值对）─────────────────────


def _find_object(text: str, start: int) -> tuple[str, int]:
    """从 text[start] 的 '{' 开始，返回 `{...}` 的内部文本和结束下标。"""
    assert text[start] == "{", text[start]
    depth = 0
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i + 1
        elif ch in "\"'":
            quote = ch
            i += 1
            while i < n and text[i] != quote:
                if text[i] == "\\":
                    i += 1
                i += 1
        i += 1
    raise ValueError("unbalanced object literal")


def _find_array(text: str, start: int) -> tuple[str, int]:
    """从 text[start] 的 '[' 开始，返回数组内部文本和结束下标。"""
    assert text[start] == "[", text[start]
    depth = 0
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i + 1
        elif ch in "\"'":
            quote = ch
            i += 1
            while i < n and text[i] != quote:
                if text[i] == "\\":
                    i += 1
                i += 1
        i += 1
    raise ValueError("unbalanced array literal")


def _unescape(s: str) -> str:
    out: list[str] = []
    i, n = 0, len(s)
    simple = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "\\": "\\"}
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n:
            nxt = s[i + 1]
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
            elif nxt == "u":
                out.append(chr(int(s[i + 2 : i + 6], 16)))
                i += 6
            elif nxt == "x":
                out.append(chr(int(s[i + 2 : i + 4], 16)))
                i += 4
            else:
                out.append(nxt)
                i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _parse_object(text: str) -> dict[str, str]:
    """解析扁平 JS 对象 `{key:value, key:value, ...}` 内部文本。"""
    out: dict[str, str] = {}
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        if text[i] in "\"'":
            quote = text[i]
            i += 1
            key = ""
            while i < n and text[i] != quote:
                if text[i] == "\\":
                    key += text[i] + text[i + 1]
                    i += 2
                else:
                    key += text[i]
                    i += 1
            i += 1
        else:
            j = i
            while j < n and text[j] not in ":,":
                j += 1
            key = text[i:j].strip()
            i = j
        while i < n and text[i] in " \t\r\n":
            i += 1
        assert text[i] == ":"
        i += 1
        while i < n and text[i] in " \t\r\n":
            i += 1
        ch = text[i]
        if ch in "\"'":
            quote = ch
            i += 1
            val = ""
            while i < n and text[i] != quote:
                if text[i] == "\\":
                    val += text[i] + text[i + 1]
                    i += 2
                else:
                    val += text[i]
                    i += 1
            i += 1
            out[key] = _unescape(val)
        else:
            j = i
            while j < n and text[j] not in ",}":
                j += 1
            out[key] = text[i:j].strip()
            i = j
    return out


def _object_at(text: str, start: int) -> dict[str, str]:
    inner, _ = _find_object(text, start)
    return _parse_object(inner)


def _find(text: str, probe: str) -> int:
    idx = text.find(probe)
    if idx < 0:
        raise ValueError(f"probe not found: {probe!r}")
    return idx


# ── 分包数据定位与抽取 ────────────────────────────────────────────────────────


def _extract_534(f534: str) -> dict:
    """解析 534 分包：返回 {nature_en, nature_zh, move_slug_ja, move_fix,
    abil_slug_ja, abil_fix, item_fix, poke_slug_ja, poke_alias,
    poke_form_suffix, zh_pokemon, zh_move, zh_item, zh_abil}。"""
    s = _find(f534, "9096:(e,a,r)=>")
    e = _find(f534, "9416:(e,a,r)=>")
    seg = f534[s:e]

    # 性格：日文→英文 / 日文→中文
    i = _find(seg, "let t=")
    nature_en = _object_at(seg, i + len("let t="))
    i = _find(seg, "},s=")
    nature_zh = _object_at(seg, i + len("},s="))

    # 招式：slug→日文 字面量（m = Object.fromEntries(Object.entries({...})... 的反转）
    i = _find(seg, "let m=Object.fromEntries(Object.entries(")
    inner, _ = _find_object(seg, i + len("let m=Object.fromEntries(Object.entries("))
    move_slug_ja = _parse_object(inner)
    # 招式修正：日文→slug（API 中的替代/变体名）
    i = _find(seg, "p=")
    move_fix = _object_at(seg, i + len("p="))

    # 特性：slug→日文 字面量（b 为反转），+ 修正表 k（日文→slug）
    i = _find(seg, "let b=Object.fromEntries(Object.entries(")
    inner, _ = _find_object(seg, i + len("let b=Object.fromEntries(Object.entries("))
    abil_slug_ja = _parse_object(inner)
    i = _find(seg, "k=")
    abil_fix = _object_at(seg, i + len("k="))

    # 道具修正表 v（日文→slug）
    i = _find(seg, "v=")
    item_fix = _object_at(seg, i + len("v="))

    # 宝可梦 slug→日文 字面量（l 为反转）
    s78 = _find(f534, "7851:(e,a,r)=>")
    seg7 = f534[s78:]
    i = _find(seg7, "Object.entries({bulbasaur")
    inner, _ = _find_object(seg7, i + len("Object.entries("))
    poke_slug_ja = _parse_object(inner)
    # 形态后缀表 n / 别名表 c
    i = _find(seg7, ",n=")
    poke_form_suffix = _object_at(seg7, i + len(",n="))
    i = _find(seg7, ",c=")
    poke_alias = _object_at(seg7, i + len(",c="))

    # 中文名表（模块 9416）：宝可梦 Fi / 招式 Ls / 道具 HX / 特性 IO
    seg9 = f534[e:]
    i = _find(seg9, "let o=")
    zh_pokemon = _object_at(seg9, i + len("let o="))
    i = _find(seg9, ",i=")
    zh_move = _object_at(seg9, i + len(",i="))
    i = _find(seg9, ",t=")
    zh_item = _object_at(seg9, i + len(",t="))
    i = _find(seg9, ",s=")
    zh_abil = _object_at(seg9, i + len(",s="))

    return {
        "nature_en": nature_en,
        "nature_zh": nature_zh,
        "move_slug_ja": move_slug_ja,
        "move_fix": move_fix,
        "abil_slug_ja": abil_slug_ja,
        "abil_fix": abil_fix,
        "item_fix": item_fix,
        "poke_slug_ja": poke_slug_ja,
        "poke_alias": poke_alias,
        "poke_form_suffix": poke_form_suffix,
        "zh_pokemon": zh_pokemon,
        "zh_move": zh_move,
        "zh_item": zh_item,
        "zh_abil": zh_abil,
    }


def _extract_26(f26: str) -> list[dict]:
    """解析 26 分包：返回道具表 [{slug, ja, effect, flingPower}, ...]。"""
    s = _find(f26, "7769:(e,t,a)=>")
    seg = f26[s:]
    i = _find(seg, "let i=")
    inner, _ = _find_array(seg, i + len("let i="))
    items: list[dict] = []
    k = 0
    while k < len(inner):
        while k < len(inner) and inner[k] in " \t\r\n,":
            k += 1
        if k >= len(inner):
            break
        obj, end = _find_object(inner, k)
        items.append(_parse_object(obj))
        k = end
    return items


# ── 名称表组装 ────────────────────────────────────────────────────────────────


def _title_case(slug: str) -> str:
    return " ".join((p[:1].upper() + p[1:]) if p else p for p in slug.split("-"))


def _build_table(slug_ja: dict[str, str], zh: dict[str, str]) -> dict:
    return {
        slug: {"en": _title_case(slug), "ja": ja, "zh": zh.get(slug, "")}
        for slug, ja in slug_ja.items()
        if slug
    }


def _build_natures(nature_en: dict, nature_zh: dict) -> dict:
    table = {}
    for ja, en in nature_en.items():
        slug = en.lower()
        table[slug] = {"en": en, "ja": ja, "zh": nature_zh.get(ja, "")}
    return table


def _build_ja_index(kind: str, table: dict, fixes: dict) -> dict:
    index = {}
    for slug, entry in table.items():
        index.setdefault(entry["ja"], slug)
    index.update(fixes)
    return index


def main() -> None:
    f534 = (_MAPPING_DIR / _F534).read_text(encoding="utf-8")
    f26 = (_MAPPING_DIR / _F26).read_text(encoding="utf-8")

    m = _extract_534(f534)
    items = _extract_26(f26)

    pokemon = _build_table(m["poke_slug_ja"], m["zh_pokemon"])
    moves = _build_table(m["move_slug_ja"], m["zh_move"])
    items_table = _build_table(
        {it["slug"]: it["ja"] for it in items if it.get("slug")}, m["zh_item"]
    )
    abilities = _build_table(m["abil_slug_ja"], m["zh_abil"])
    natures = _build_natures(m["nature_en"], m["nature_zh"])

    data = {
        "meta": {
            "source": f"{_F26}, {_F534} (pokechamdb.com webpack chunks)",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "pokemon": pokemon,
        "moves": moves,
        "items": items_table,
        "abilities": abilities,
        "natures": natures,
        "ja_index": {
            "pokemon": _build_ja_index("pokemon", pokemon, {}),
            "moves": _build_ja_index("moves", moves, m["move_fix"]),
            "items": _build_ja_index("items", items_table, m["item_fix"]),
            "abilities": _build_ja_index("abilities", abilities, m["abil_fix"]),
            "natures": _build_ja_index("natures", natures, {}),
        },
        "pokemon_alias": m["poke_alias"],
        "pokemon_form_suffix": m["poke_form_suffix"],
    }

    _OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入: {_OUT_PATH}")
    print(
        f"  宝可梦 {len(pokemon)}  招式 {len(moves)}  道具 {len(items_table)}"
        f"  特性 {len(abilities)}  性格 {len(natures)}"
    )


if __name__ == "__main__":
    main()
