"""
从队伍选择画面识别对手 6 只宝可梦

用法:
    python -m pokepilot.detect_team.opponent_team.detect_opponents <screenshot>
    python -m pokepilot.detect_team.opponent_team.detect_opponents <screenshot> --debug
"""

import argparse
import json
from pathlib import Path

import cv2

from pokepilot.common.pokemon_builder import PokemonBuilder
from pokepilot.common.pokemon_detect import get_detector
from pokepilot.tools.logger_util import setup_logger

logger = setup_logger(__name__)

_builder = None


def _get_builder() -> PokemonBuilder:
    """获取 PokemonBuilder 单例（懒加载）"""
    global _builder
    if _builder is None:
        _builder = PokemonBuilder()
    return _builder


# 加载对手队伍布局配置
_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def _load_layout() -> dict:
    """每次调用时读取布局配置（前端保存后无需重启即生效）"""
    config_path = _CONFIG_DIR / "opponent_team_layout.json"
    return json.loads(config_path.read_text(encoding="utf-8"))


def _build_slots(layout: dict):
    """根据布局配置生成 6 个槽的归一化坐标与槽内区域坐标"""
    _W, _H = layout["base_resolution"]["width"], layout["base_resolution"]["height"]
    _SLOT_CFG = layout["slot_layout"]
    _SLOT_X0, _SLOT_Y0, _SLOT_W, _SLOT_H, _SLOT_GAP = (
        _SLOT_CFG["x0"], _SLOT_CFG["y0"], _SLOT_CFG["width"], _SLOT_CFG["height"], _SLOT_CFG["gap"]
    )

    slots = [
        (
            _SLOT_X0 / _W,
            (_SLOT_Y0 + i * (_SLOT_H + _SLOT_GAP)) / _H,
            (_SLOT_X0 + _SLOT_W) / _W,
            (_SLOT_Y0 + i * (_SLOT_H + _SLOT_GAP) + _SLOT_H) / _H,
        )
        for i in range(6)
    ]

    regions = layout["slot_regions"]
    sprite = (regions["sprite"]["rx0"], regions["sprite"]["ry0"], regions["sprite"]["rx1"], regions["sprite"]["ry1"])
    type1 = (regions["type1"]["rx0"], regions["type1"]["ry0"], regions["type1"]["rx1"], regions["type1"]["ry1"])
    type2 = (regions["type2"]["rx0"], regions["type2"]["ry0"], regions["type2"]["rx1"], regions["type2"]["ry1"])
    return slots, sprite, type1, type2


def _sub(img, rx0, ry0, rx1, ry1):
    H, W = img.shape[:2]
    return img[int(ry0*H):int(ry1*H), int(rx0*W):int(rx1*W)]


def detect_opponents(screenshot: str, debug: bool = False) -> list[dict]:
    img = cv2.imread(screenshot)
    if img is None:
        raise FileNotFoundError(screenshot)

    detector = get_detector()

    if debug:
        dbg_dir = Path("debug_output")
        dbg_dir.mkdir(exist_ok=True)

    opp_slots, slot_sprite, slot_type1, slot_type2 = _build_slots(_load_layout())

    results = []
    for i, (rx0, ry0, rx1, ry1) in enumerate(opp_slots, 1):
        slot   = _sub(img, rx0, ry0, rx1, ry1)
        sprite = _sub(slot, *slot_sprite)
        t1_img = _sub(slot, *slot_type1)
        t2_img = _sub(slot, *slot_type2)

        result = detector.detect(sprite, t1_img, t2_img, bg_removal="auto")

        results.append(
            result
        )

        logger.info(f"槽{i}: {result['slug']:25s}  score={result['score']:.4f}  "
              f"属性={result['types']}  候选={result['candidates_searched']}")

        if debug:
            pokemon_dir = dbg_dir / "pokemon_opp"
            pokemon_dir.mkdir(parents=True, exist_ok=True)

            # 原始图片
            cv2.imwrite(str(pokemon_dir / f"slot_{i}_sprite.png"), sprite)
            cv2.imwrite(str(pokemon_dir / f"slot_{i}_type1.png"), t1_img)
            cv2.imwrite(str(pokemon_dir / f"slot_{i}_type2.png"), t2_img)

            # # 去除背景后的图片
            # sprite_clean = _remove_bg(sprite, )

            # cv2.imwrite(str(pokemon_dir / f"slot_{i}_sprite_clean.png"), sprite_clean)

            logger.debug(f"三个 region 已保存：{pokemon_dir}/slot_{i}_*.png (原始和去背景版)")
    return results

def detect_opponents_team_with_cards(screenshot, debug=False) -> tuple[dict, list[dict]]:
    """识别对方队伍，返回 (team, detect_cards)；detect_cards 供队伍匹配使用"""
    builder = _get_builder()
    detect_cards = detect_opponents(screenshot, debug=debug)
    roster = []
    for detect_card in detect_cards:
        pokemon = builder.build_pokemon(detect_data=detect_card)
        roster.append(pokemon)
    team = {
        "trainer_name": "",
        "roster": roster,
    }
    return team, detect_cards


def detect_opponents_team(screenshot, debug=False) -> dict:
    """识别对方队伍（只返回队伍，与旧调用兼容）"""
    team, _ = detect_opponents_team_with_cards(screenshot, debug=debug)
    return team

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("screenshot")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    detect_opponents(args.screenshot, args.debug)


if __name__ == "__main__":
    main()
