"""
卡牌布局可视化工具 —— 在截图上绘制卡牌框和提取目标区域。

用法:
    python -m pokepilot.debug_tools.debug_card_layout --image screenshots/team/moves_latest.png

说明:
  - 绿框：左边卡牌
  - 蓝框：右边卡牌
  - 黄框（R1）：66×66 像素区域
  - 紫框（R2）：31×31 像素区域
  - 橙框（R3）：31×31 像素区域
  - 结果保存到 debug_output/ 目录
"""

import argparse
import cv2
import numpy as np
from pathlib import Path

from pokepilot.detect_team.my_team.parse_team import _get_card_coords


COLORS = {
    "left":    (0, 255, 0),      # 绿 - 左边卡牌
    "right":   (255, 0, 0),      # 蓝 - 右边卡牌
    "region":  (0, 255, 255),    # 黄 - 提取区域
}

# 提取区域配置（相对坐标 + 固定像素大小）
REGIONS = [
    {"rx": 0.0226, "ry": -0.0876, "size": 66, "label": "R1"},   # 66×66
    {"rx": 0.4699, "ry": 0.0567,  "size": 31, "label": "R2"},   # 31×31
    {"rx": 0.5259, "ry": 0.0567,  "size": 31, "label": "R3"},   # 31×31
]

REGION_COLORS = {
    "R1": (0, 255, 255),  # 黄
    "R2": (255, 0, 255),  # 紫
    "R3": (255, 127, 0),  # 橙
}


def draw_card_layout(image_path: str) -> np.ndarray:
    """在图上绘制卡牌框和提取目标区域，返回标注后的图像。"""
    frame = cv2.imread(image_path)
    if frame is None:
        raise FileNotFoundError(f"找不到图片: {image_path}")

    out = frame.copy()
    H, W = out.shape[:2]

    # 获取卡牌布局
    layout = _get_card_coords(image_path)
    left_cards = layout['left_cards']
    right_cards = layout['right_cards']
    all_cards = left_cards + right_cards

    # 显示所有卡牌框的信息
    if all_cards:
        for idx, card in enumerate(all_cards, 1):
            print(f"卡{idx}: x={card['x']}, y={card['y']}, w={card['w']}, h={card['h']}")

        print("\n相对坐标应用效果：")
        for region in REGIONS:
            print(f"{region['label']}:")
            for idx, card in enumerate(all_cards, 1):
                rx0 = int(card['x'] + region['rx'] * card['w'])
                ry0 = int(card['y'] + region['ry'] * card['h'])
                print(f"  卡{idx}: ({rx0}, {ry0})")

    # 绘制左边卡牌（绿色） + 提取区域
    for idx, card_info in enumerate(left_cards):
        x, y, w, h = card_info['x'], card_info['y'], card_info['w'], card_info['h']
        x1, y1 = x + w, y + h

        # 卡牌框
        cv2.rectangle(out, (x, y), (x1, y1), COLORS["left"], 2)
        label = f"L{idx + 1}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        cv2.rectangle(out, (x, y - th - 6), (x + tw + 6, y), COLORS["left"], -1)
        cv2.putText(out, label, (x + 3, y - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)

        # 所有提取区域
        for region in REGIONS:
            rx0 = int(x + region['rx'] * w)
            ry0 = int(y + region['ry'] * h)
            rx1 = rx0 + region['size']
            ry1 = ry0 + region['size']
            color = REGION_COLORS.get(region['label'], (255, 255, 255))
            cv2.rectangle(out, (rx0, ry0), (rx1, ry1), color, 1)

    # 绘制右边卡牌（蓝色） + 提取区域
    for idx, card_info in enumerate(right_cards):
        x, y, w, h = card_info['x'], card_info['y'], card_info['w'], card_info['h']
        x1, y1 = x + w, y + h

        # 卡牌框
        cv2.rectangle(out, (x, y), (x1, y1), COLORS["right"], 2)
        label = f"R{idx + 1}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        cv2.rectangle(out, (x, y - th - 6), (x + tw + 6, y), COLORS["right"], -1)
        cv2.putText(out, label, (x + 3, y - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)

        # 所有提取区域
        for region in REGIONS:
            rx0 = int(x + region['rx'] * w)
            ry0 = int(y + region['ry'] * h)
            rx1 = rx0 + region['size']
            ry1 = ry0 + region['size']
            color = REGION_COLORS.get(region['label'], (255, 255, 255))
            cv2.rectangle(out, (rx0, ry0), (rx1, ry1), color, 1)

    # 统计信息
    info = f"Left: {len(left_cards)} | Right: {len(right_cards)} | Total: {len(left_cards) + len(right_cards)}"
    cv2.putText(out, info, (10, H - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1, cv2.LINE_AA)

    return out


def visualize(image_path: str) -> None:
    """可视化卡牌布局并保存结果"""
    try:
        annotated = draw_card_layout(image_path)
    except Exception as e:
        print(f"错误: {e}")
        return

    H, W = annotated.shape[:2]
    print(f"图片分辨率: {W}x{H}")

    # 保存结果
    out_dir = Path("debug_output")
    out_dir.mkdir(exist_ok=True)
    name = Path(image_path).stem + "_card_layout.png"
    out_path = out_dir / name
    cv2.imwrite(str(out_path), annotated)
    print(f"✓ 已保存: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="卡牌布局可视化工具")
    parser.add_argument("--image", required=True, help="截图路径")
    args = parser.parse_args()
    visualize(args.image)
