"""
交互式坐标选取工具 —— 在图片上拖拽框选，打印归一化和像素坐标

用法:
    python -m pokepilot.tools.pick_coords <image_path>

操作:
    拖拽        框选区域，松开后打印坐标
    关闭窗口    退出
"""

import sys

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.widgets import RectangleSelector
from PIL import Image
import numpy as np


def main():
    if len(sys.argv) < 2:
        print("用法: python -m pokepilot.tools.pick_coords <image_path>")
        sys.exit(1)

    img = np.array(Image.open(sys.argv[1]))
    H, W = img.shape[:2]
    print(f"图片尺寸: {W}×{H}")
    print("拖拽框选区域，可多次框选，关闭窗口退出\n")

    fig, ax = plt.subplots(figsize=(16, 9))
    ax.imshow(img)
    ax.set_title("拖拽框选区域（可多次），关闭窗口退出")
    ax.axis("off")

    drawn = []

    def on_select(eclick, erelease):
        x0 = int(min(eclick.xdata, erelease.xdata))
        y0 = int(min(eclick.ydata, erelease.ydata))
        x1 = int(max(eclick.xdata, erelease.xdata))
        y1 = int(max(eclick.ydata, erelease.ydata))
        if x1 - x0 < 4 or y1 - y0 < 4:
            return
        drawn.append((x0, y0, x1, y1))
        rect = patches.Rectangle((x0, y0), x1-x0, y1-y0,
                                  linewidth=2, edgecolor="lime", facecolor="none")
        ax.add_patch(rect)
        ax.text(x0, y0 - 6, f"#{len(drawn)}", color="lime", fontsize=8)
        fig.canvas.draw_idle()
        print(f"#{len(drawn)}")
        print(f"  像素  : ({x0}, {y0}, {x1}, {y1})  w={x1-x0} h={y1-y0}")
        print(f"  归一化: ({x0/W:.4f}, {y0/H:.4f}, {x1/W:.4f}, {y1/H:.4f})")
        print()

    sel = RectangleSelector(ax, on_select, useblit=True,
                            button=[1],
                            minspanx=5, minspany=5,
                            spancoords="pixels",
                            interactive=False)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
