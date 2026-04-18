"""
把对手队伍选择画面裁出 6 个槽，以及每槽内的精灵图和属性图标，
保存到 debug_output/

用法:
    python -m pokepilot.tools.crop_slots <image_path>
"""

import sys
from pathlib import Path

import cv2

# ── 对手槽布局参数（像素，基于 1920×1080）────────────────────────────────
_W, _H     = 1920, 1080
_SLOT_X0   = 1554   # 左边起始
_SLOT_W    = 300    # 槽宽
_SLOT_Y0   = 153    # 第一槽顶部
_SLOT_H    = 115    # 槽高
_SLOT_GAP  = 11   # 槽间距（px）

OPP_SLOTS = [
    (
        _SLOT_X0 / _W,
        (_SLOT_Y0 + i * (_SLOT_H + _SLOT_GAP)) / _H,
        (_SLOT_X0 + _SLOT_W) / _W,
        (_SLOT_Y0 + i * (_SLOT_H + _SLOT_GAP) + _SLOT_H) / _H,
    )
    for i in range(6)
]

# ── 槽内归一化坐标：精灵图 & 最多两个属性图标 ────────────────────────────
SLOT_SPRITE = (0.2152, 0.1466, 0.5662, 0.9914)
SLOT_TYPE1  = (0.6391, 0.1293, 0.7980, 0.5517)
SLOT_TYPE2  = (0.8146, 0.1207, 0.9735, 0.5431)


def _sub(img, rx0, ry0, rx1, ry1):
    H, W = img.shape[:2]
    return img[int(ry0*H):int(ry1*H), int(rx0*W):int(rx1*W)]


def crop_slots(image_path: str, out_dir: str = "debug_output") -> None:
    img = cv2.imread(image_path)
    if img is None:
        print(f"无法读取: {image_path}")
        sys.exit(1)
    H, W = img.shape[:2]
    out = Path(out_dir)
    out.mkdir(exist_ok=True)

    for i, (rx0, ry0, rx1, ry1) in enumerate(OPP_SLOTS, 1):
        slot = _sub(img, rx0, ry0, rx1, ry1)
        cv2.imwrite(str(out / f"opp_slot_{i}.png"), slot)

        sprite = _sub(slot, *SLOT_SPRITE)
        type1  = _sub(slot, *SLOT_TYPE1)
        type2  = _sub(slot, *SLOT_TYPE2)

        cv2.imwrite(str(out / f"opp_slot_{i}_sprite.png"), sprite)
        cv2.imwrite(str(out / f"opp_slot_{i}_type1.png"),  type1)
        cv2.imwrite(str(out / f"opp_slot_{i}_type2.png"),  type2)

        print(f"槽{i}: slot={slot.shape[1]}×{slot.shape[0]}  "
              f"sprite={sprite.shape[1]}×{sprite.shape[0]}  "
              f"type={type1.shape[1]}×{type1.shape[0]}")

    print(f"\n保存到 {out}/")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python -m pokepilot.battle.crop_slots <image_path>")
        sys.exit(1)
    crop_slots(sys.argv[1])
