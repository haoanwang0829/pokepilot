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
from pokepilot.common.pokemon_detect import PokemonDetector, _remove_bg
from pokepilot.tools.logger_util import setup_logger

logger = setup_logger(__name__)

# 加载对手队伍布局配置
_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
_LAYOUT_CONFIG = json.loads((_CONFIG_DIR / "opponent_team_layout.json").read_text(encoding="utf-8"))
_SLOT_CFG = _LAYOUT_CONFIG["slot_layout"]
_SLOT_X0, _SLOT_Y0, _SLOT_W, _SLOT_H, _SLOT_GAP = (
    _SLOT_CFG["x0"], _SLOT_CFG["y0"], _SLOT_CFG["width"], _SLOT_CFG["height"], _SLOT_CFG["gap"]
)
_W, _H = _LAYOUT_CONFIG["base_resolution"]["width"], _LAYOUT_CONFIG["base_resolution"]["height"]

# 生成 6 个槽的归一化坐标
OPP_SLOTS = [
    (
        _SLOT_X0 / _W,
        (_SLOT_Y0 + i * (_SLOT_H + _SLOT_GAP)) / _H,
        (_SLOT_X0 + _SLOT_W) / _W,
        (_SLOT_Y0 + i * (_SLOT_H + _SLOT_GAP) + _SLOT_H) / _H,
    )
    for i in range(6)
]

# 槽内区域坐标
_REGIONS = _LAYOUT_CONFIG["slot_regions"]
SLOT_SPRITE = (_REGIONS["sprite"]["rx0"], _REGIONS["sprite"]["ry0"], _REGIONS["sprite"]["rx1"], _REGIONS["sprite"]["ry1"])
SLOT_TYPE1 = (_REGIONS["type1"]["rx0"], _REGIONS["type1"]["ry0"], _REGIONS["type1"]["rx1"], _REGIONS["type1"]["ry1"])
SLOT_TYPE2 = (_REGIONS["type2"]["rx0"], _REGIONS["type2"]["ry0"], _REGIONS["type2"]["rx1"], _REGIONS["type2"]["ry1"])


def _sub(img, rx0, ry0, rx1, ry1):
    H, W = img.shape[:2]
    return img[int(ry0*H):int(ry1*H), int(rx0*W):int(rx1*W)]


def detect_opponents(screenshot: str, debug: bool = False) -> list[dict]:
    img = cv2.imread(screenshot)
    if img is None:
        raise FileNotFoundError(screenshot)

    detector = PokemonDetector()

    if debug:
        dbg_dir = Path("debug_output")
        dbg_dir.mkdir(exist_ok=True)

    results = []
    for i, (rx0, ry0, rx1, ry1) in enumerate(OPP_SLOTS, 1):
        slot   = _sub(img, rx0, ry0, rx1, ry1)
        sprite = _sub(slot, *SLOT_SPRITE)
        t1_img = _sub(slot, *SLOT_TYPE1)
        t2_img = _sub(slot, *SLOT_TYPE2)

        result = detector.detect(sprite, t1_img, t2_img, bg_removal="auto")

        results.append(
            result
        )

        logger.info(f"槽{i}: {result['slug']:25s}  score={result['score']:.1f}  "
              f"属性={result['types']}  候选={result['candidates_searched']}")

        if debug:
            pokemon_dir = dbg_dir / "pokemon_opp"
            pokemon_dir.mkdir(parents=True, exist_ok=True)

            # 原始图片
            cv2.imwrite(str(pokemon_dir / f"slot_{i}_sprite.png"), sprite)
            cv2.imwrite(str(pokemon_dir / f"slot_{i}_type1.png"), t1_img)
            cv2.imwrite(str(pokemon_dir / f"slot_{i}_type2.png"), t2_img)

            # 去除背景后的图片
            sprite_clean = _remove_bg(sprite, )

            cv2.imwrite(str(pokemon_dir / f"slot_{i}_sprite_clean.png"), sprite_clean)

            logger.debug(f"三个 region 已保存：{pokemon_dir}/slot_{i}_*.png (原始和去背景版)")
    return results

def detect_opponents_team(screenshot, debug=False) -> dict:
    builder = PokemonBuilder()
    roster = []
    detect_cards = detect_opponents(screenshot, debug=debug)
    for i, detect_card in enumerate(detect_cards, 1):
        pokemon = builder.build_pokemon(
            detect_data=detect_card)
        roster.append(pokemon)
    team = {
        "trainer_name": "",
        "roster": roster,
    }
    return team

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("screenshot")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    detect_opponents(args.screenshot, args.debug)


if __name__ == "__main__":
    main()
