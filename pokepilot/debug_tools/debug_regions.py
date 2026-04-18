"""
ROI 可视化工具 —— 在截图上叠加标注框，用于验证和调整 regions.py 坐标。

用法:
    python -m pokepilot.debug_regions --image screenshots/single_english/frame_20260410_220530.png --mode single
    python -m pokepilot.debug_regions --image screenshots/double/frame_20260410_214411.png --mode double

操作:
    鼠标悬停 → 显示当前像素坐标（便于量取新坐标）
    按 S     → 保存标注图到 debug_output/
    按 Q     → 退出
"""

import argparse
import cv2
import numpy as np
from pathlib import Path

from pokepilot.config.regions import Region, SingleRegions, DoubleRegions, TeamSelectRegions


# 每种区域类型用不同颜色
COLORS = {
    "my":     (0,   255,  80),   # 绿 - 我方
    "enemy":  (0,   100, 255),   # 橙红 - 对方
    "move":   (255, 200,   0),   # 黄 - 招式
    "timer":  (200, 200, 200),   # 灰 - 计时
    "event":  (255,   0, 255),   # 紫 - 事件文字
    "slot":   (100, 255, 255),   # 青 - 选宝
    "default":(255, 255, 255),
}

def _color_for(label: str) -> tuple:
    if label.startswith("my"):    return COLORS["my"]
    if label.startswith("enemy"): return COLORS["enemy"]
    if "move" in label:           return COLORS["move"]
    if "timer" in label or "time" in label: return COLORS["timer"]
    if "event" in label:          return COLORS["event"]
    if "slot" in label:           return COLORS["slot"]
    return COLORS["default"]


def draw_regions(frame: np.ndarray, regions: list[Region]) -> np.ndarray:
    out = frame.copy()
    h, w = out.shape[:2]
    for r in regions:
        x1, y1, x2, y2 = r.to_pixels(w, h)
        color = _color_for(r.label)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        # 标签背景
        (tw, th), _ = cv2.getTextSize(r.label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(out, (x1, y1 - th - 4), (x1 + tw + 4, y1), color, -1)
        cv2.putText(out, r.label, (x1 + 2, y1 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
    return out


# 鼠标回调，用于读取坐标
_mouse_pos = [0, 0]
def _on_mouse(event, x, y, flags, param):
    _mouse_pos[0], _mouse_pos[1] = x, y


def visualize(image_path: str, mode: str) -> None:
    frame = cv2.imread(image_path)
    if frame is None:
        raise FileNotFoundError(f"找不到图片: {image_path}")
    H, W = frame.shape[:2]
    print(f"图片分辨率: {W}x{H}")

    # 根据 mode 收集所有区域
    regions: list[Region] = []
    if mode == "single":
        cls = SingleRegions
        regions = [v for v in vars(cls).values() if isinstance(v, Region)]
    elif mode == "double":
        cls = DoubleRegions
        regions = [v for v in vars(cls).values() if isinstance(v, Region)]
    elif mode == "team":
        cls = TeamSelectRegions
        for v in vars(cls).values():
            if isinstance(v, Region):
                regions.append(v)
            elif isinstance(v, list):
                regions.extend(r for r in v if isinstance(r, Region))
    else:
        raise ValueError(f"未知 mode: {mode}，可选 single / double / team")

    annotated = draw_regions(frame, regions)

    win = "PokePilot - Region Debug (S=save, Q=quit)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, min(W, 1280), min(H * min(W, 1280) // W, 720))
    cv2.setMouseCallback(win, _on_mouse)

    print(f"共 {len(regions)} 个区域，按 S 保存，按 Q 退出")
    while True:
        display = annotated.copy()
        mx, my = _mouse_pos
        # 换算成归一化坐标，方便调整 regions.py
        nx, ny = mx / W, my / H
        info = f"pixel ({mx},{my})  norm ({nx:.3f},{ny:.3f})"
        cv2.putText(display, info, (10, H - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1, cv2.LINE_AA)
        cv2.imshow(win, display)

        key = cv2.waitKey(30) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("s"):
            out_dir = Path("debug_output")
            out_dir.mkdir(exist_ok=True)
            name = Path(image_path).stem + f"_{mode}_regions.png"
            out_path = out_dir / name
            cv2.imwrite(str(out_path), annotated)
            print(f"已保存: {out_path}")

    cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ROI 可视化验证工具")
    parser.add_argument("--image", required=True, help="截图路径")
    parser.add_argument("--mode", required=True, choices=["single", "double", "team"],
                        help="对战模式")
    args = parser.parse_args()
    visualize(args.image, args.mode)
