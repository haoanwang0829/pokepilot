"""
从队伍选择画面识别对手 6 只宝可梦

用法:
    python -m pokepilot.detect_team.opponent_team.detect_opponents <screenshot>
    python -m pokepilot.detect_team.opponent_team.detect_opponents <screenshot> --debug
"""

import argparse
from pathlib import Path

import cv2

from pokepilot.common.pokemon_builder import PokemonBuilder
from pokepilot.detect_team.opponent_team.crop_slots import OPP_SLOTS, SLOT_SPRITE, SLOT_TYPE1, SLOT_TYPE2
from pokepilot.common.pokemon_detect import PokemonDetector, _remove_bg


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

        print(f"槽{i}: {result['slug']:25s}  score={result['score']:.1f}  "
              f"属性={result['types']}  候选={result['candidates_searched']}")

        if debug:
            cv2.imwrite(str(dbg_dir / f"opp_slot_{i}_sprite_clean.png"),
                        _remove_bg(sprite))
    return results

def detect_opponents_team(screenshot) -> dict:
    builder = PokemonBuilder()
    roster = []
    detect_cards = detect_opponents(screenshot)
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
