"""
测试多个深紫色/淡紫色范围组合
"""

import cv2
import numpy as np
import os
import sys


def test_color_ranges(image_path, output_dir="test_ranges_output"):
    """
    测试多个颜色范围组合
    """

    img = cv2.imread(image_path)
    if img is None:
        print(f"无法读取图片: {image_path}")
        return

    os.makedirs(output_dir, exist_ok=True)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    print("\n" + "="*60)
    print("测试深紫色/淡紫色范围...")
    print("="*60 + "\n")

    # 定义多个范围组合
    test_configs = [
        {
            "name": "V_threshold_70",
            "dark": (np.array([120, 20, 0]), np.array([160, 255, 70])),
            "light": (np.array([120, 20, 70]), np.array([160, 255, 255]))
        },
        {
            "name": "V_threshold_80",
            "dark": (np.array([120, 20, 0]), np.array([160, 255, 80])),
            "light": (np.array([120, 20, 80]), np.array([160, 255, 255]))
        },
        {
            "name": "V_threshold_100",
            "dark": (np.array([120, 20, 0]), np.array([160, 255, 100])),
            "light": (np.array([120, 20, 100]), np.array([160, 255, 255]))
        },
        {
            "name": "V_threshold_120",
            "dark": (np.array([120, 20, 0]), np.array([160, 255, 120])),
            "light": (np.array([120, 20, 120]), np.array([160, 255, 255]))
        },
        {
            "name": "V_threshold_140",
            "dark": (np.array([120, 20, 0]), np.array([160, 255, 140])),
            "light": (np.array([120, 20, 140]), np.array([160, 255, 255]))
        },
        {
            "name": "Conservative_S",
            "dark": (np.array([130, 30, 0]), np.array([150, 255, 100])),
            "light": (np.array([130, 10, 100]), np.array([150, 255, 255]))
        },
    ]

    for config in test_configs:
        name = config["name"]
        dark_lower, dark_upper = config["dark"]
        light_lower, light_upper = config["light"]

        # 创建掩膜
        mask_dark = cv2.inRange(hsv, dark_lower, dark_upper)
        mask_light = cv2.inRange(hsv, light_lower, light_upper)

        # 绘制结果
        result = img.copy()

        # 检测深紫色轮廓
        contours_dark, _ = cv2.findContours(mask_dark, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours_dark:
            if cv2.contourArea(contour) < 50:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(result, (x, y), (x+w, y+h), (255, 0, 0), 2)

        # 检测淡紫色轮廓
        contours_light, _ = cv2.findContours(mask_light, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours_light:
            if cv2.contourArea(contour) < 50:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(result, (x, y), (x+w, y+h), (0, 255, 0), 2)

        # 保存结果
        filename = os.path.join(output_dir, f"{name}.jpg")
        cv2.imwrite(filename, result)

        dark_pixels = np.count_nonzero(mask_dark)
        light_pixels = np.count_nonzero(mask_light)

        print(f"{name:20} | 深紫: {dark_pixels:6}px | 淡紫: {light_pixels:6}px")

    print("\n" + "="*60)
    print(f"所有结果已保存到: {output_dir}")
    print("查看哪个效果最好，告诉我名字，我来调参")
    print("="*60 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python test_color_ranges.py <image_path>")
        sys.exit(1)

    test_color_ranges(sys.argv[1])
