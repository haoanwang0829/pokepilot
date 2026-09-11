"""
从 db/db.db 读取 Team 表，遍历每行队伍的 Pokepaste 网址，
爬取 pokepast.es 上的队伍详情，写入 team_detail 表。

数据库: db/db.db (sqlite3)
表 Team      —— 队伍表，Pokepaste 字段为 pokepast.es 链接
表 team_detail —— team_id | form_ids | paste_info

输出形状（写入 team_detail）:
  form_ids   宝可梦 dex号-形态号 4 位补零逗号拼接，如 "0149-0,0478-0,0983-0,0903-0,0902-0,0445-0"
             （从页面 img.img-pokemon 的 src 形如 /img/pokemon/149-0.png 提取）
  paste_info 结构化 JSON 字符串:
    {
      "title": "队伍标题",
      "format": "gen9championsvgc2026regmb",
      "pokemon": [
        {"name": "Dragonite", "gender": "M", "item": "Dragoninite",
         "ability": "Inner Focus", "level": 50,
         "evs": {"hp":2,"attack":0,"defense":0,"sp_atk":32,"sp_def":0,"speed":32},
         "nature": "Modest",
         "moves": ["Dragon Pulse","Heat Wave","Thunderbolt","Tailwind"]}
      ]
    }

用法:
    python -m pokepilot.data.build_team_detail
    python -m pokepilot.data.build_team_detail --resume
    python -m pokepilot.data.build_team_detail --team MB607
    python -m pokepilot.data.build_team_detail --limit 10 --delay 1.0
"""

import argparse
import json
import re
import sqlite3
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

_ROOT    = Path(__file__).resolve().parent.parent.parent
_DB_PATH = _ROOT / "db" / "db.db"
_ROSTER_PATH = _ROOT / "data" / "champions_roster.json"
_DELAY   = 1.5
_RETRIES = 3

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

# pokepast.es 页面上 img.img-pokemon 的 src 形如 /img/pokemon/149-0.png
_DEX_FORM_RE = re.compile(r"/img/pokemon/(\d+)-(\d+)\.png")

# Showdown EVs 文本中的统计键 → 项目统计算法键
_EV_KEY_MAP = {
    "HP":   "hp",
    "Atk":  "attack",
    "Def":  "defense",
    "SpA":  "sp_atk",
    "SpD":  "sp_def",
    "Spe":  "speed",
}
_EV_LINE_RE = re.compile(r"EVs:\s*(.*)", re.IGNORECASE)

# 宝可梦英文名 → dex 号（来自 champions_roster.json，做 0 dex 回退）
_DEX_BY_NAME: dict[str, int] | None = None


def _load_dex_by_name() -> dict[str, int]:
    """加载 宝可梦英文名（小写，含形态）→ dex 号 映射。"""
    global _DEX_BY_NAME
    if _DEX_BY_NAME is not None:
        return _DEX_BY_NAME

    _DEX_BY_NAME = {}
    if _ROSTER_PATH.exists():
        try:
            roster = json.loads(_ROSTER_PATH.read_text(encoding="utf-8"))["pokemon"]
        except (json.JSONDecodeError, KeyError):
            roster = []
        for p in roster:
            name = (p.get("name") or "").strip().lower()
            form = (p.get("form") or "").strip().lower()
            dex = p.get("id")
            if name and dex:
                _DEX_BY_NAME.setdefault(name, dex)
                if form:
                    # 如 "raichu" + form "mega-y" → "raichu-mega-y"
                    _DEX_BY_NAME.setdefault(f"{name}-{form}", dex)
    return _DEX_BY_NAME


def _resolve_dex_from_name(name: str) -> int:
    """从宝可梦名解析 dex 号；用于 img src 中 dex 为 0（站点占位）时的回退。

    名称可能带形态后缀（如 Ninetales-Alola），先取最长匹配前缀。
    """
    dex_map = _load_dex_by_name()
    key = (name or "").strip().lower()
    if not key:
        return 0
    if key in dex_map:
        return dex_map[key]
    # 逐级去掉 -形态 后缀匹配：maushold-four → maushold
    parts = key.split("-")
    while len(parts) > 1:
        parts.pop()
        candidate = "-".join(parts)
        if candidate in dex_map:
            return dex_map[candidate]
    return 0


def _connect_db(db_path: Path) -> sqlite3.Connection:
    """连接数据库并返回连接对象。"""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def fetch_paste(url: str, retries: int = _RETRIES) -> requests.Response | None:
    """GET pokepaste 页面，失败按 retries 重试，最终失败返回 None。"""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=30)
            if r.status_code == 404:
                print(f"  404 页面不存在")
                return None
            r.raise_for_status()
            return r
        except Exception as e:
            print(f"  请求失败 (第 {attempt}/{retries} 次): {e}")
            if attempt < retries:
                time.sleep(_DELAY)
    return None


def parse_paste_page(html: str) -> dict | None:
    """解析 pokepaste 页面 HTML → 结构化队伍数据。

    返回 {title, format, pokemon:[...]}；无任何 article 时返回 None。
    """
    soup = BeautifulSoup(html, "html.parser")

    aside = soup.find("aside")
    title = ""
    fmt = ""
    if aside:
        h1 = aside.find("h1")
        if h1:
            title = h1.get_text(strip=True)
        p = aside.find("p")
        if p:
            text = p.get_text(strip=True)
            if text.startswith("Format:"):
                fmt = text[len("Format:"):].strip()

    pokemon = []
    for article in soup.find_all("article"):
        pre = article.find("pre")
        entry = _parse_pre_text(pre.get_text() if pre else "")

        img = article.find("img", class_="img-pokemon")
        m = _DEX_FORM_RE.search(img.get("src", "")) if img else None
        if m:
            dex, form = int(m.group(1)), int(m.group(2))
            if dex == 0:
                # 站点对部分宝可梦（如 Sinistcha）用 0 占位，按名字回退
                dex = _resolve_dex_from_name(entry["name"])
            dex_form = f"{dex:04d}-{form}"
        else:
            dex = _resolve_dex_from_name(entry["name"])
            dex_form = f"{dex:04d}-0" if dex else ""

        entry["dex_form"] = dex_form
        pokemon.append(entry)

    if not pokemon:
        return None

    return {
        "title": title,
        "format": fmt,
        "pokemon": pokemon,
    }


def _parse_pre_text(text: str) -> dict:
    """解析单只宝可梦的 <pre> 文本（Showdown 标准格式）→ 结构化字段。"""
    entry: dict = {
        "name": "", "gender": "", "item": "",
        "ability": "", "level": 0,
        "evs": {}, "nature": "", "moves": [],
    }
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]

    for ln in lines:
        if ln.startswith("- "):
            entry["moves"].append(ln[2:].strip())
            continue
        if ln.lower().startswith("ability:"):
            entry["ability"] = ln.split(":", 1)[1].strip()
            continue
        if ln.lower().startswith("level:"):
            entry["level"] = int(ln.split(":", 1)[1].strip())
            continue
        ev_match = _EV_LINE_RE.match(ln)
        if ev_match:
            entry["evs"] = _parse_evs(ev_match.group(1))
            continue
        if "@" in ln:
            # 首行: Name (G) @ Item
            head, _, rest = ln.partition("@")
            name_gender = head.strip()
            entry["item"] = rest.strip()
            m = re.match(r"^(.*?)\s*\(([MFmf])\)$", name_gender)
            if m:
                entry["name"] = m.group(1).strip()
                entry["gender"] = m.group(2).upper()
            else:
                entry["name"] = name_gender
            continue
        if not entry["name"]:
            entry["name"] = ln.strip()
            continue
        # 其余无冒号行 → 性格（去掉 "Nature" 后缀）
        entry["nature"] = ln.strip().removesuffix(" Nature")

    return entry


def _parse_evs(ev_text: str) -> dict:
    """解析 "2 HP / 32 SpA / 32 Spe" → {"hp":2, "sp_atk":32, "speed":32}。"""
    evs: dict = {}
    for part in ev_text.split("/"):
        m = re.match(r"(\d+)\s*([A-Za-z]+)", part.strip())
        if m:
            key = _EV_KEY_MAP.get(m.group(2), "")
            if key:
                evs[key] = int(m.group(1))
    return evs


def _list_existing_ids(conn: sqlite3.Connection) -> set[str]:
    """查询 team_detail 已存在的 team_id（用于 --resume）。"""
    rows = conn.execute('SELECT "team_id" FROM "team_detail"').fetchall()
    return {r[0] for r in rows}


def _upsert_team_detail(conn: sqlite3.Connection, team_id: str,
                        form_ids: str, paste_info: str) -> None:
    """写入/覆盖 team_detail 的一行，立即提交。"""
    conn.execute(
        """
        INSERT INTO "team_detail" ("team_id", "form_ids", "paste_info")
        VALUES (?, ?, ?)
        ON CONFLICT("team_id") DO UPDATE SET
            "form_ids"   = excluded."form_ids",
            "paste_info" = excluded."paste_info"
        """,
        (team_id, form_ids, paste_info),
    )
    conn.commit()


def build_team_detail(db_path: Path = _DB_PATH, resume: bool = False,
                      team_filter: str | None = None, limit: int | None = None,
                      delay: float = _DELAY, retries: int = _RETRIES) -> None:
    """遍历 Team 表，爬取每个队伍的 Pokepaste 并写入 team_detail。"""
    conn = _connect_db(db_path)
    existing = _list_existing_ids(conn) if resume else set()

    rows = conn.execute(
        'SELECT "Team_ID", "Pokepaste" FROM "Team"'
    ).fetchall()
    teams = [(r[0], r[1]) for r in rows if r[1]]

    if team_filter:
        teams = [(tid, url) for tid, url in teams if tid == team_filter]
        if not teams:
            print(f"未找到队伍 {team_filter}，或该队没有 Pokepaste 链接")
            conn.close()
            return

    if limit:
        teams = teams[:limit]

    ok = skip = fail = 0
    total = len(teams)
    print(f"目标: {total} 支队伍")

    for i, (team_id, url) in enumerate(teams, 1):
        if team_id in existing:
            skip += 1
            continue

        print(f"[{i}/{total}] {team_id}  {url} ...", end=" ", flush=True)
        resp = fetch_paste(url, retries=retries)
        if resp is None:
            print("失败")
            fail += 1
            continue

        data = parse_paste_page(resp.text)
        if data is None:
            print("解析失败（页面无队伍数据）")
            fail += 1
            continue

        form_ids = ",".join(p["dex_form"] for p in data["pokemon"])
        paste_info = json.dumps(data, ensure_ascii=False)

        _upsert_team_detail(conn, team_id, form_ids, paste_info)
        ok += 1
        print(f"ok  ({len(data['pokemon'])} 只)")

        if delay > 0 and i < total:
            time.sleep(delay)

    conn.close()
    print(f"\n完成: 成功={ok}  跳过={skip}  失败={fail}")


def main():
    parser = argparse.ArgumentParser(description="爬取 Pokepaste 队伍详情写入 team_detail")
    parser.add_argument("--db", default=str(_DB_PATH), help="sqlite 数据库路径（默认 db/db.db）")
    parser.add_argument("--resume", action="store_true",
                        help="跳过 team_detail 中已有的 team_id")
    parser.add_argument("--team", help="只处理指定 Team_ID（如 MB607）")
    parser.add_argument("--limit", type=int, help="最多处理的队伍数")
    parser.add_argument("--delay", type=float, default=_DELAY,
                        help="队伍间限速秒数（默认 1.5）")
    parser.add_argument("--retries", type=int, default=_RETRIES,
                        help="单队请求失败重试次数（默认 3）")
    args = parser.parse_args()

    build_team_detail(
        db_path=Path(args.db),
        resume=args.resume,
        team_filter=args.team,
        limit=args.limit,
        delay=args.delay,
        retries=args.retries,
    )


if __name__ == "__main__":
    main()
