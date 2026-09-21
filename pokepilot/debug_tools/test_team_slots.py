"""队伍槽位 / 草稿接口回归测试（全部写在临时目录，不碰真实 data/my_team）。

用法：
    python -m pokepilot.debug_tools.test_team_slots

覆盖：
1. GET  /api/teams          只列队伍槽位：排除 temp/draft，也排除无 roster 的 JSON
2. POST /api/teams/save     带 roster 新建/覆盖/改名；不带 roster 回退 temp.json；两者皆无 → 400
3. POST /api/teams/load/*   正常读取；temp/draft → 400；不存在 → 404
4. DELETE /api/teams/draft  物理删除草稿且幂等
5. DELETE /api/teams/<slot> 删除槽位；temp/draft → 400
6. POST /api/teams/build    构建成功后自动清理 draft.json
"""

import json
import shutil
import tempfile
from pathlib import Path

from pokepilot.ui import ui_server

FAKE_MON = {"nickname": "test", "name": "pikachu", "types": ["Electric"]}


class _StubPokemon:
    def __init__(self, d):
        self._d = d

    def to_dict(self):
        return self._d


class _StubBuilder:
    """替身：跳过真实 OCR/查表，只验证接口的落盘与清理逻辑。"""

    def build_pokemon(self, detect_data=None, moves_data=None, stats_data=None, language="zh"):
        return _StubPokemon(dict(FAKE_MON))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pokepilot_test_"))
    ui_server.TEAM_DIR = tmp  # 关键：把队伍目录指到临时目录，真实数据零影响
    app = ui_server.create_app()
    client = app.test_client()

    failures = []

    def check(name, cond, extra=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"   <- {extra}"))
        if not cond:
            failures.append(name)

    def write(name, data):
        (tmp / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def teams():
        return client.get("/api/teams").get_json()["teams"]

    def names():
        return [t["id"] for t in teams()]

    print("== 1. 槽位列表隔离 ==")
    check("空目录列表为空", teams() == [])
    write("7", {"trainer_name": "", "roster": [FAKE_MON], "slot_name": "甲"})
    write("3", {"foo": "bar"})  # 无 roster，不应被当成槽位
    write("temp", {"trainer_name": "", "roster": [FAKE_MON]})
    write("draft", {"detect_cards": [], "move_cards": [], "stat_cards": []})
    check("只列出 7，排除 temp/draft/无 roster 文件", names() == ["7"], names())
    check("槽位名取自 slot_name", teams()[0]["slot_name"] == "甲", teams())

    print("== 2. 草稿持久化删除 ==")
    r = client.delete("/api/teams/draft").get_json()
    check("DELETE /api/teams/draft 成功且 deleted=True", r.get("success") and r.get("deleted"), r)
    check("draft.json 已从磁盘消失", not (tmp / "draft.json").exists())
    r = client.delete("/api/teams/draft").get_json()
    check("重复删除幂等（deleted=False）", r.get("success") and r.get("deleted") is False, r)
    check("draft 不在槽位列表中", "draft" not in names(), names())

    print("== 3. 写入队伍（新建 / 覆盖 / 改名）==")
    r = client.post("/api/teams/save", json={}).get_json()
    check("无 roster 时回退 temp.json 保存", r.get("success") and r.get("from_temp"), r)
    check("新建槽位自增为 8", r.get("slot_id") == "8", r)
    check("新建槽位默认名「队伍 8」", r.get("slot_name") == "队伍 8", r)
    check("8.json 落盘且含 roster", json.loads((tmp / "8.json").read_text(encoding="utf-8")).get("roster") == [FAKE_MON])

    r = client.post("/api/teams/save", json={"slot_name": "新队伍", "roster": [FAKE_MON]}).get_json()
    check("带 roster 另存为新槽位 9", r.get("success") and r.get("slot_id") == "9" and r.get("slot_name") == "新队伍", r)
    check("列表包含 9", "9" in names(), names())

    r = client.post("/api/teams/save", json={"slot_id": "7", "roster": [FAKE_MON]}).get_json()
    check("覆盖 7 但未传名字 → 沿用原名「甲」", r.get("success") and r.get("slot_name") == "甲", r)
    r = client.post("/api/teams/save", json={"slot_id": "7", "slot_name": "乙", "roster": [FAKE_MON]}).get_json()
    check("覆盖 7 且传新名字 → 改名「乙」", r.get("success") and r.get("slot_name") == "乙", r)
    check("列表里 7 已改名", [t for t in teams() if t["id"] == "7"][0]["slot_name"] == "乙", teams())

    r = client.post("/api/teams/save", json={"slot_id": "temp", "roster": [FAKE_MON]})
    check("拒绝写入系统文件 temp（400）", r.status_code == 400 and not r.get_json()["success"], r.status_code)

    print("== 4. 工作缓冲一致性 ==")
    buf = json.loads((tmp / "temp.json").read_text(encoding="utf-8"))
    check("保存后 temp.json 同步 roster", buf.get("roster") == [FAKE_MON], buf)
    check("保存后 temp.json 同步 slot_name", buf.get("slot_name") == "乙", buf)

    print("== 5. 读取队伍 ==")
    r = client.post("/api/teams/load/7").get_json()
    check("读取 7 成功且带回 roster", r.get("success") and r.get("team", {}).get("roster") == [FAKE_MON], r)
    check("读取 temp → 400", client.post("/api/teams/load/temp").status_code == 400)
    check("读取 draft → 400", client.post("/api/teams/load/draft").status_code == 400)
    check("读取不存在槽位 → 404", client.post("/api/teams/load/99").status_code == 404)

    print("== 6. 无队伍时的友好报错 ==")
    (tmp / "temp.json").unlink()
    r = client.post("/api/teams/save", json={})
    check("无 roster 且无 temp → 400 而非 500", r.status_code == 400, r.status_code)
    check("错误提示可读", "没有可保存的队伍" in r.get_json()["error"], r.get_json())
    r = client.post("/api/teams/save", json={"roster": []})
    check("空 roster 且无 temp → 400", r.status_code == 400, r.status_code)

    print("== 7. 生成队伍后自动清理草稿 ==")
    write("draft", {"detect_cards": [{}], "move_cards": [{}], "stat_cards": [{}]})
    orig = ui_server.PokemonBuilder
    ui_server.PokemonBuilder = _StubBuilder
    try:
        r = client.post("/api/teams/build", json={"detect_cards": [{}], "move_cards": [{}], "stat_cards": [{}]}).get_json()
    finally:
        ui_server.PokemonBuilder = orig
    check("build 成功", r.get("success"), r)
    check("build 后草稿被清理", not (tmp / "draft.json").exists())
    check("build 结果写入 temp.json", json.loads((tmp / "temp.json").read_text(encoding="utf-8")).get("roster") == [FAKE_MON])

    print("== 8. 删除槽位 ==")
    r = client.delete("/api/teams/7").get_json()
    check("删除 7 成功", r.get("success"), r)
    check("7 已从列表消失", "7" not in names(), names())
    check("删除不存在的槽位 → 404", client.delete("/api/teams/77").status_code == 404)
    check("删除 temp → 400", client.delete("/api/teams/temp").status_code == 400)

    shutil.rmtree(tmp, ignore_errors=True)
    print()
    if failures:
        print(f"共 {len(failures)} 项失败：" + "；".join(failures))
        return 1
    print("全部通过 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
