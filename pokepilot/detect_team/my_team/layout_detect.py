"""
布局检测：识别6个Pokemon卡片的位置
返回：左边3个和右边3个矩形的坐标
"""

import cv2
import numpy as np
import os


def detect_card_layout(image_path, debug=False, output_dir="debug_output"):
    """
    检测布局中的6个卡片位置

    Args:
        image_path: 图片路径
        debug: 是否输出调试图片（True/False）
        output_dir: 调试输出目录

    Returns:
        dict: 包含以下内容
        {
            'layout': {
                'top_x': int,       # 左上角X
                'top_y': int,       # 左上角Y
                'rect_w': int,      # 矩形宽
                'rect_h': int,      # 矩形高
                'vertical_gap': int,# 竖直间距
                'horizontal_gap': int, # 横向间距
            },
            'left_cards': [  # 左边3个卡片的坐标
                {'x': int, 'y': int, 'w': int, 'h': int},
                ...
            ],
            'right_cards': [ # 右边3个卡片的坐标
                {'x': int, 'y': int, 'w': int, 'h': int},
                ...
            ]
        }
    """

    img = cv2.imread(image_path)
    if img is None:
        print(f"错误：无法读取图片 {image_path}")
        return None

    if debug:
        os.makedirs(output_dir, exist_ok=True)

    h, w = img.shape[:2]

    # ============ 1. 颜色分割 ============
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_purple = np.array([120, 30, 30])
    upper_purple = np.array([160, 255, 255])
    mask = cv2.inRange(hsv, lower_purple, upper_purple)

    # ============ 2. 形态学操作 ============
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    # ============ 3. 边缘检测 ============
    edges = cv2.Canny(mask, 50, 150)
    # 膨胀边缘以连接间隙
    edge_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.dilate(edges, edge_kernel, iterations=1)

    # ============ 4. 轮廓检测 ============
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # ============ 5. 矩形检测和去重 ============
    rectangles = []
    for idx, contour in enumerate(contours):
        area = cv2.contourArea(contour)
        if area < 500:
            continue

        epsilon = 0.02 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)

        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(contour)
            rectangles.append({
                'index': idx,
                'x': x,
                'y': y,
                'w': w,
                'h': h,
                'area': area
            })

    # 去重：合并接近的矩形
    rectangles = _merge_close_rectangles(rectangles, threshold=10)

    # ============ 6. 分析布局 ============
    layout_info = _analyze_layout(rectangles, img)

    if layout_info is None:
        print("错误：无法检测到完整的布局")
        return None

    # ============ 调试输出 ============
    if debug:
        _save_debug_images(img, rectangles, layout_info, output_dir)

    # ============ 构造返回结果 ============
    result = {
        'layout': {
            'top_x': layout_info['top_x'],
            'top_y': layout_info['top_y'],
            'rect_w': layout_info['rect_w'],
            'rect_h': layout_info['rect_h'],
            'vertical_gap': layout_info['avg_vertical_gap'],
            'horizontal_gap': layout_info['horizontal_gap'],
        },
        'left_cards': [],
        'right_cards': []
    }

    # 生成6个卡片的坐标
    top_x = layout_info['top_x']
    top_y = layout_info['top_y']
    rect_w = layout_info['rect_w']
    rect_h = layout_info['rect_h']
    v_gap = layout_info['avg_vertical_gap']
    h_gap = layout_info['horizontal_gap']

    # 左边3个卡片
    for i in range(3):
        y = top_y + i * (rect_h + v_gap)
        result['left_cards'].append({
            'x': top_x,
            'y': y,
            'w': rect_w,
            'h': rect_h
        })

    # 右边3个卡片
    right_x = top_x + rect_w + h_gap
    for i in range(3):
        y = top_y + i * (rect_h + v_gap)
        result['right_cards'].append({
            'x': right_x,
            'y': y,
            'w': rect_w,
            'h': rect_h
        })

    return result


def _merge_close_rectangles(rectangles, threshold=10):
    """合并距离接近的矩形"""
    if not rectangles:
        return rectangles

    merged = []
    used = set()

    for i, rect1 in enumerate(rectangles):
        if i in used:
            continue

        x1, y1, w1, h1 = rect1['x'], rect1['y'], rect1['w'], rect1['h']
        group = [rect1]

        for j, rect2 in enumerate(rectangles):
            if i == j or j in used:
                continue

            x2, y2, w2, h2 = rect2['x'], rect2['y'], rect2['w'], rect2['h']

            if (abs(x1 - x2) <= threshold and
                abs(y1 - y2) <= threshold and
                abs(w1 - w2) <= threshold and
                abs(h1 - h2) <= threshold):
                group.append(rect2)
                used.add(j)

        merged_rect = {
            'index': group[0]['index'],
            'x': int(np.mean([r['x'] for r in group])),
            'y': int(np.mean([r['y'] for r in group])),
            'w': int(np.mean([r['w'] for r in group])),
            'h': int(np.mean([r['h'] for r in group])),
            'area': np.mean([r['area'] for r in group])
        }
        merged.append(merged_rect)
        used.add(i)

    return merged


def _analyze_layout(rectangles, img):
    """分析6个矩形的布局"""
    if len(rectangles) < 6:
        return None

    rects_list = list(rectangles)
    rects_list.sort(key=lambda r: r['x'])

    img_w = img.shape[1]
    mid_x = img_w / 2

    left_rects = [r for r in rects_list if r['x'] + r['w']//2 < mid_x]
    right_rects = [r for r in rects_list if r['x'] + r['w']//2 >= mid_x]

    if len(left_rects) < 3 or len(right_rects) < 3:
        return None

    # 取前3个
    left_rects = sorted(left_rects[:3], key=lambda r: r['y'])
    right_rects = sorted(right_rects[:3], key=lambda r: r['y'])

    # 计算参数
    top_left = left_rects[0]
    top_x = top_left['x']
    top_y = top_left['y']
    rect_w = int(np.mean([r['w'] for r in left_rects]))
    rect_h = int(np.mean([r['h'] for r in left_rects]))

    # 竖直间距
    vertical_gaps = []
    for i in range(len(left_rects) - 1):
        gap = left_rects[i + 1]['y'] - (left_rects[i]['y'] + left_rects[i]['h'])
        vertical_gaps.append(gap)

    avg_vertical_gap = int(np.mean(vertical_gaps)) if vertical_gaps else 0

    # 横向间距
    horizontal_gap = right_rects[0]['x'] - (top_left['x'] + top_left['w'])

    return {
        'top_x': top_x,
        'top_y': top_y,
        'rect_w': rect_w,
        'rect_h': rect_h,
        'vertical_gaps': vertical_gaps,
        'avg_vertical_gap': avg_vertical_gap,
        'horizontal_gap': horizontal_gap,
        'left_rects': left_rects,
        'right_rects': right_rects
    }


def _save_debug_images(img, rectangles, layout_info, output_dir):
    """保存调试图片和6张卡片切割图"""

    # 绘制检测到的矩形
    result = img.copy()
    for rect in rectangles:
        x, y, w, h = rect['x'], rect['y'], rect['w'], rect['h']
        cv2.rectangle(result, (x, y), (x+w, y+h), (0, 255, 0), 2)

    cv2.imwrite(os.path.join(output_dir, "detected.jpg"), result)

    # 绘制计算出的6个矩形
    result = img.copy()

    top_x = layout_info['top_x']
    top_y = layout_info['top_y']
    rect_w = layout_info['rect_w']
    rect_h = layout_info['rect_h']
    v_gap = layout_info['avg_vertical_gap']
    h_gap = layout_info['horizontal_gap']

    # 左边3个
    for i in range(3):
        y = top_y + i * (rect_h + v_gap)
        cv2.rectangle(result, (top_x, y), (top_x+rect_w, y+rect_h), (255, 0, 0), 2)
        cv2.putText(result, f"L{i+1}", (top_x+10, y+30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

    # 右边3个
    right_x = top_x + rect_w + h_gap
    for i in range(3):
        y = top_y + i * (rect_h + v_gap)
        cv2.rectangle(result, (right_x, y), (right_x+rect_w, y+rect_h), (0, 255, 0), 2)
        cv2.putText(result, f"R{i+1}", (right_x+10, y+30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

    cv2.imwrite(os.path.join(output_dir, "layout.jpg"), result)

    # ============ 切割6张卡片图片 ============
    crops_dir = os.path.join(output_dir, "crops")
    os.makedirs(crops_dir, exist_ok=True)

    # 左边3个卡片
    for i in range(3):
        y = top_y + i * (rect_h + v_gap)
        crop = img[y:y+rect_h, top_x:top_x+rect_w]
        cv2.imwrite(os.path.join(crops_dir, f"L{i+1}_card.jpg"), crop)

    # 右边3个卡片
    for i in range(3):
        y = top_y + i * (rect_h + v_gap)
        crop = img[y:y+rect_h, right_x:right_x+rect_w]
        cv2.imwrite(os.path.join(crops_dir, f"R{i+1}_card.jpg"), crop)

    print(f"✓ 调试图片保存到 {output_dir}")
    print(f"✓ 6张卡片切割图保存到 {crops_dir}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python layout_detect.py <image_path> [--debug]")
        sys.exit(1)

    image_path = sys.argv[1]
    debug_mode = "--debug" in sys.argv

    result = detect_card_layout(image_path, debug=debug_mode)

    if result:
        print("\n布局参数:")
        print(f"  X: {result['layout']['top_x']}")
        print(f"  Y: {result['layout']['top_y']}")
        print(f"  宽: {result['layout']['rect_w']}")
        print(f"  高: {result['layout']['rect_h']}")
        print(f"  竖直间距: {result['layout']['vertical_gap']}")
        print(f"  横向间距: {result['layout']['horizontal_gap']}")

        print("\n左边卡片:")
        for i, card in enumerate(result['left_cards'], 1):
            print(f"  L{i}: ({card['x']}, {card['y']}) {card['w']}x{card['h']}")

        print("\n右边卡片:")
        for i, card in enumerate(result['right_cards'], 1):
            print(f"  R{i}: ({card['x']}, {card['y']}) {card['w']}x{card['h']}")
