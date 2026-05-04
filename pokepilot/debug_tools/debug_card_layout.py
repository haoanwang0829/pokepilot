"""
Debug script: Visualize card layout and extract individual regions
- Draws card frames, sprite, type1, type2 regions on the image
- Extracts each region and saves as individual images
- Generates HTML preview

Usage:
    python debug_card_layout.py [image_path] [output_dir]

    python debug_card_layout.py
        Uses default: screenshots/team/moves.png -> debug_output/layout
"""

import cv2
import sys
import json
from pathlib import Path
import numpy as np


def load_card_layout_config():
    """Load card layout config from JSON file"""
    config_path = Path(__file__).parent.parent / "config" / "card_layout.json"

    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    # Fallback to default if file doesn't exist
    return {
        'layout': {
            'top_x': 190,
            'top_y': 265,
            'rect_w': 738,
            'rect_h': 186,
            'vertical_gap': 31,
            'horizontal_gap': 64,
        },
        'regions': {
            'sprite': {"rx": 0.01, "ry": -0.11, "size": 66},
            'type1': {"rx": 0.471, "ry": 0.05, "size": 30},
            'type2': {"rx": 0.528, "ry": 0.05, "size": 30},
        },
        'stat_boxes': {
            'box_w': 0.189,
            'box_h': 0.19,
            'left_x': 0.287,
            'right_x': 0.762,
            'y_tops': [0.2708, 0.5200, 0.7692]
        },
        'stat_arrows': [
            {'name': 'hp', 'x': 0.162, 'y': 0.302, 'size': 27},
            {'name': 'attack', 'x': 0.182, 'y': 0.552, 'size': 27},
            {'name': 'defense', 'x': 0.183, 'y': 0.79, 'size': 27},
            {'name': 'sp_atk', 'x': 0.653, 'y': 0.302, 'size': 27},
            {'name': 'sp_def', 'x': 0.656, 'y': 0.552, 'size': 27},
            {'name': 'speed', 'x': 0.656, 'y': 0.79, 'size': 27},
        ]
    }


config = load_card_layout_config()
layout = config['layout']
regions = config.get('regions', {})

top_x = layout['top_x']
top_y = layout['top_y']
rect_w = layout['rect_w']
rect_h = layout['rect_h']
v_gap = layout['vertical_gap']
h_gap = layout['horizontal_gap']

_FALLBACK_LAYOUT = {'left_cards': [], 'right_cards': []}

# 左边3个卡片
for i in range(3):
    y = top_y + i * (rect_h + v_gap)
    _FALLBACK_LAYOUT['left_cards'].append({
        'x': top_x,
        'y': y,
        'w': rect_w,
        'h': rect_h
    })

# 右边3个卡片
right_x = top_x + rect_w + h_gap
for i in range(3):
    y = top_y + i * (rect_h + v_gap)
    _FALLBACK_LAYOUT['right_cards'].append({
        'x': right_x,
        'y': y,
        'w': rect_w,
        'h': rect_h
    })

# Region coordinates (relative to card frame)
_SPRITE_REGION = regions.get('sprite', {"rx": 0.01, "ry": -0.11, "size": 66})
_TYPE1_REGION = regions.get('type1', {"rx": 0.471, "ry": 0.05, "size": 30})
_TYPE2_REGION = regions.get('type2', {"rx": 0.528, "ry": 0.05, "size": 30})

# Stats boxes and arrows loaded from config
stat_boxes = config.get('stat_boxes', {})
stat_arrows = config.get('stat_arrows', [])

_STAT_BOX_W = stat_boxes.get('box_w', 0.189)
_STAT_BOX_H = stat_boxes.get('box_h', 0.19)
_STAT_LEFT_X = stat_boxes.get('left_x', 0.287)
_STAT_RIGHT_X = stat_boxes.get('right_x', 0.762)
_STAT_Y_TOPS = stat_boxes.get('y_tops', [0.2708, 0.5200, 0.7692])

# Convert arrow dict list to tuple list for compatibility
_STAT_ARROWS = [(arrow['name'], arrow['x'], arrow['y'], arrow['size']) for arrow in stat_arrows]


def debug_card_layout(image_path: str, output_dir: str = "debug_output/layout"):
    """
    1. 在原图上画出所有框
    2. 截取每个区域的小图片
    """
    # 创建输出目录
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 读入图片
    img = cv2.imread(image_path)
    if img is None:
        print(f"无法读取图片: {image_path}")
        return

    h, w = img.shape[:2]
    print(f"图片大小: {w}x{h}")

    # 绘制版本：在原图上画框
    img_marked = img.copy()

    # 颜色定义 (BGR)
    color_card = (0, 255, 0)      # 绿色：卡片框
    color_sprite = (255, 0, 0)    # 蓝色：sprite
    color_type1 = (0, 255, 255)   # 黄色：type1
    color_type2 = (0, 165, 255)   # 橙色：type2
    thickness = 2

    all_cards = _FALLBACK_LAYOUT['left_cards'] + _FALLBACK_LAYOUT['right_cards']

    # 遍历每张卡片
    for slot_idx, card_info in enumerate(all_cards):
        slot_num = slot_idx + 1
        x0, y0 = card_info['x'], card_info['y']
        w_card, h_card = card_info['w'], card_info['h']
        x1, y1 = x0 + w_card, y0 + h_card

        # 1. 画卡片框
        cv2.rectangle(img_marked, (x0, y0), (x1, y1), color_card, thickness + 1)
        # 白色背景标签框
        label_text = f"Slot {slot_num}"
        (text_w, text_h), baseline = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(img_marked, (x0, y0 - text_h - 10), (x0 + text_w + 5, y0), (255, 255, 255), -1)
        cv2.putText(img_marked, label_text, (x0 + 2, y0 - 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_card, 2)

        # 根据行数调整 type 的 y 坐标
        row = (slot_idx % 3) + 1

        # 2. 画 sprite, type1, type2 的框
        regions = [
            ('sprite', _SPRITE_REGION, color_sprite),
            ('type1', {**_TYPE1_REGION, 'ry': _TYPE1_REGION['ry']}, color_type1),
            ('type2', {**_TYPE2_REGION, 'ry': _TYPE2_REGION['ry']}, color_type2),
        ]

        for label, region_cfg, color in regions:
            rx = region_cfg['rx']
            ry = region_cfg['ry']
            size = region_cfg['size']

            rx0 = int(x0 + rx * w_card)
            ry0 = int(y0 + ry * h_card)
            rx1 = rx0 + size
            ry1 = ry0 + size

            # 画框（虚线）
            cv2.rectangle(img_marked, (rx0, ry0), (rx1, ry1), color, 2)
            # 添加带背景的标签
            font_scale = 0.4
            (text_w, text_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
            label_bg_x0 = max(rx0, 0)
            label_bg_y0 = max(ry0 - text_h - 5, 0)
            cv2.rectangle(img_marked, (label_bg_x0, label_bg_y0), (label_bg_x0 + text_w + 4, label_bg_y0 + text_h + 4), color, -1)
            cv2.putText(img_marked, label, (label_bg_x0 + 2, ry0 - 3),
                       cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1)

            # 3. 截取矩形并保存
            extracted = np.full((size, size, 3), 255, dtype=np.uint8)

            # 计算在原图和提取矩形中的有效范围
            src_x0 = max(0, rx0)
            src_y0 = max(0, ry0)
            src_x1 = min(img.shape[1], rx1)
            src_y1 = min(img.shape[0], ry1)

            dst_x0 = src_x0 - rx0
            dst_y0 = src_y0 - ry0
            dst_x1 = dst_x0 + (src_x1 - src_x0)
            dst_y1 = dst_y0 + (src_y1 - src_y0)

            if src_x1 > src_x0 and src_y1 > src_y0:
                extracted[dst_y0:dst_y1, dst_x0:dst_x1] = img[src_y0:src_y1, src_x0:src_x1]

            # 保存截取的图片
            region_path = output_path / f"slot_{slot_num}_{label}.png"
            cv2.imwrite(str(region_path), extracted)
            print(f"  Saved: {region_path}")

        # 4. Draw stat boxes
        color_stat = (200, 200, 0)  # Cyan for stat boxes

        # Left stat boxes
        for y_top in _STAT_Y_TOPS:
            box_x0 = int(x0 + _STAT_LEFT_X * w_card)
            box_y0 = int(y0 + y_top * h_card)
            box_x1 = int(box_x0 + _STAT_BOX_W * w_card)
            box_y1 = int(box_y0 + _STAT_BOX_H * h_card)
            cv2.rectangle(img_marked, (box_x0, box_y0), (box_x1, box_y1), color_stat, 1)

        # Right stat boxes
        for y_top in _STAT_Y_TOPS:
            box_x0 = int(x0 + _STAT_RIGHT_X * w_card)
            box_y0 = int(y0 + y_top * h_card)
            box_x1 = int(box_x0 + _STAT_BOX_W * w_card)
            box_y1 = int(box_y0 + _STAT_BOX_H * h_card)
            cv2.rectangle(img_marked, (box_x0, box_y0), (box_x1, box_y1), color_stat, 1)

        # 5. Draw stat arrows
        color_arrow = (100, 200, 255)  # Orange for arrows
        for stat_name, x, y, size_px in _STAT_ARROWS:
            arrow_x0 = int(x0 + x * w_card)
            arrow_y0 = int(y0 + y * h_card)
            arrow_x1 = arrow_x0 + size_px
            arrow_y1 = arrow_y0 + size_px
            cv2.rectangle(img_marked, (arrow_x0, arrow_y0), (arrow_x1, arrow_y1), color_arrow, 1)

    # 保存标注后的完整图片
    marked_path = output_path / "marked_layout.png"
    cv2.imwrite(str(marked_path), img_marked)
    print(f"\nMarked layout saved: {marked_path}")

    # 创建简单的 HTML 预览（可选）
    create_preview_html(output_path, image_path)


def create_preview_html(output_dir: Path, original_image: str):
    """生成 HTML 预览页面"""
    html_content = """
    <html>
    <head>
        <title>Card Layout Debug</title>
        <style>
            body { font-family: Arial; margin: 20px; }
            .image-group { margin-bottom: 30px; border: 1px solid #ccc; padding: 10px; }
            h2 { color: #333; }
            img { max-width: 100%; border: 1px solid #ddd; margin-top: 10px; }
            .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px; }
            .grid-item { border: 1px solid #ddd; padding: 5px; }
            .grid-item img { width: 100%; }
        </style>
    </head>
    <body>
        <h1>Card Layout Debug Preview</h1>

        <div class="image-group">
            <h2>Original with Marked Regions</h2>
            <img src="marked_layout.png" alt="Marked Layout">
        </div>

        <div class="image-group">
            <h2>Extracted Regions</h2>
            <div class="grid" id="regions"></div>
        </div>

        <script>
            const regions = document.getElementById('regions');
            const files = [
    """

    # 列出所有截取的图片
    region_files = sorted(Path(output_dir).glob("slot_*.png"))
    for f in region_files:
        html_content += f'                "' + f.name + '",\n'

    html_content += """            ];

            files.forEach(file => {
                const div = document.createElement('div');
                div.className = 'grid-item';
                div.innerHTML = `<img src="${file}" alt="${file}"><p>${file}</p>`;
                regions.appendChild(div);
            });
        </script>
    </body>
    </html>
    """

    html_path = Path(output_dir) / "preview.html"
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"HTML preview saved: {html_path}")


if __name__ == "__main__":
    # Parse command line arguments
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        output_dir = sys.argv[2] if len(sys.argv) > 2 else "debug_output/layout"
    else:
        image_path = r"pokepilot/screenshots/team/stats.png"
        output_dir = "debug_output/layout"

    # Convert to absolute path if relative
    image_path = str(Path(image_path).resolve())

    print(f"Input: {image_path}")
    print(f"Output: {output_dir}")

    debug_card_layout(image_path, output_dir)
    print("\nDebug complete! Open debug_output/layout/preview.html to view results")
