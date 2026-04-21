"""
队伍配置解析工具 —— 本地 OCR

用法:
    python -m pokepilot.detect_team.parse_team \\
        --moves screenshots/team/frame_20260410_220344.png \\
        --stats screenshots/team/frame_20260410_220347.png \\
        --out   data/my_team.json
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from pokepilot.common.pokemon_builder import PokemonBuilder
from pokepilot.tools.ocr_engine import read_region
from pokepilot.common.pokemon_detect import PokemonDetector
from .layout_detect import detect_card_layout


# ─────────────────────────────────────────────────────────────────────────────
# Pokemon 识别配置
# ─────────────────────────────────────────────────────────────────────────────
# 三个矩形的相对坐标（基于卡牌框）
_SPRITE_REGION = {"rx": 0.0226, "ry": -0.0876, "size": 66}
_TYPE1_REGION = {"rx": 0.4699, "ry": 0.0567, "size": 31}
_TYPE2_REGION = {"rx": 0.5259, "ry": 0.0567, "size": 31}

# 根据行数调整 type 的 y 坐标（临时修复）
# 布局：第一行 (1,4)，第二行 (2,5)，第三行 (3,6)
_TYPE_Y_OFFSETS = {
    1: 0.0,    # 第一行
    2: 0.02,   # 第二行
    3: 0.04,   # 第三行
}

# 多色背景颜色（RGB → BGR）
_BG_COLORS_MULTI = [(221, 237, 245), (200, 95, 115)]

# ─────────────────────────────────────────────────────────────────────────────
# Stats 页 - 属性值框（基于卡片内的相对坐标，兼容不同分辨率）
# ─────────────────────────────────────────────────────────────────────────────
_STAT_BOX_W = 0.189
_STAT_BOX_H = 0.198

_STAT_LEFT_X = 0.287
_STAT_LEFT_Y_TOPS = [0.2708, 0.5000, 0.7292]

_STAT_RIGHT_X = 0.762
_STAT_RIGHT_Y_TOPS = [0.2708, 0.5000, 0.7292]

# 性格箭头位置（中文版本更新）
_STAT_ARROWS = [
    ("hp",      0.167, 0.307, 0.203, 0.442),
    ("attack",  0.187, 0.531, 0.221, 0.667),
    ("defense", 0.188, 0.781, 0.221, 0.906),
    ("sp_atk",  0.653, 0.302, 0.691, 0.438),
    ("sp_def",  0.656, 0.552, 0.689, 0.667),
    ("speed",   0.656, 0.776, 0.692, 0.906),
]


# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────

_pokemon_detector = None  # 全局单例


def _get_detector() -> PokemonDetector:
    """获取 PokemonDetector 单例"""
    global _pokemon_detector
    if _pokemon_detector is None:
        _pokemon_detector = PokemonDetector()
    return _pokemon_detector


def _extract_regions(img: np.ndarray, card_info: dict, slot_idx: int) -> dict:
    """从卡牌框提取三个矩形（sprite、type1、type2）"""
    x, y, w, h = card_info['x'], card_info['y'], card_info['w'], card_info['h']
    regions = {}

    # 根据行数调整 type 的 y 坐标
    row = (slot_idx - 1) % 3 + 1
    type_y_offset = _TYPE_Y_OFFSETS.get(row, 0)

    # 提取三个矩形
    for label, region_cfg in [
        ('sprite', _SPRITE_REGION),
        ('type1', {**_TYPE1_REGION, 'ry': _TYPE1_REGION['ry'] + type_y_offset}),
        ('type2', {**_TYPE2_REGION, 'ry': _TYPE2_REGION['ry'] + type_y_offset}),
    ]:
        rx = region_cfg['rx']
        ry = region_cfg['ry']
        size = region_cfg['size']

        rx0 = int(x + rx * w)
        ry0 = int(y + ry * h)
        rx1 = rx0 + size
        ry1 = ry0 + size

        # 提取矩形（超出边界的部分用白色填充）
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

        regions[label] = extracted

    return regions


def _identify_pokemon(img: np.ndarray, card_info: dict, slot_idx: int, debug: bool = False) -> dict:
    """识别卡牌中的 Pokemon"""
    from pokepilot.common.pokemon_detect import _remove_bg_multi

    # 提取三个矩形
    regions = _extract_regions(img, card_info, slot_idx)

    # 识别 Pokemon
    detector = _get_detector()
    result = detector.detect(
        regions['sprite'],
        regions['type1'],
        regions['type2'],
        bg_removal="multi",
        bg_colors=_BG_COLORS_MULTI,
    )

    # 保存去除背景后的 sprite（用于调试）
    if debug:
        sprite_clean = _remove_bg_multi(regions['sprite'], _BG_COLORS_MULTI, tolerance=40)
        out_dir = Path("debug_output")
        out_dir.mkdir(exist_ok=True)
        cv2.imwrite(str(out_dir / f"my_team_slot_{slot_idx}_sprite_clean.png"), sprite_clean)

    return result


def _get_card_coords(image_path: str) -> dict:
    """
    用新的布局检测方法获取6个卡片的坐标
    返回格式：{'left_cards': [...], 'right_cards': [...]}
    """
    layout_result = detect_card_layout(image_path, debug=False)
    if layout_result is None:
        raise RuntimeError(f"无法检测布局: {image_path}")
    return layout_result


def _detect_stat_color(card: np.ndarray, rx0: float, ry0: float, rx1: float, ry1: float) -> tuple[str, dict]:
    """检测箭头区域的颜色 —— 返回 ("red"/"blue"/"neutral", debug_info)"""
    H, W = card.shape[:2]

    x0 = int(rx0 * W)
    y0 = int(ry0 * H)
    x1 = int(rx1 * W)
    y1 = int(ry1 * H)

    if x0 >= W or y0 >= H or x1 <= x0 or y1 <= y0:
        return "neutral", {}

    x0 = max(0, x0)
    x1 = min(x1, W)
    y0 = max(0, y0)
    y1 = min(y1, H)

    region = card[y0:y1, x0:x1]
    if region.size == 0:
        return "neutral", {}

    b_mean = np.mean(region[:, :, 0])
    g_mean = np.mean(region[:, :, 1])
    r_mean = np.mean(region[:, :, 2])

    return "color", {
        "b_mean": b_mean,
        "g_mean": g_mean,
        "r_mean": r_mean,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Moves & More 页解析
# ─────────────────────────────────────────────────────────────────────────────

def _parse_moves_screen(image_path: str) -> tuple[list[dict], list[dict]]:
    """提取 Moves & More 页数据"""
    img = cv2.imread(image_path)
    cards = []
    pokemon_infos = []
    # 获取动态布局坐标
    layout = _get_card_coords(image_path)
    all_cards = layout['left_cards'] + layout['right_cards']  # 左3个 + 右3个

    for slot_idx, card_info in enumerate(all_cards):
        x0, y0 = card_info['x'], card_info['y']
        w, h = card_info['w'], card_info['h']
        x1, y1 = x0 + w, y0 + h

        card = img[y0:y1, x0:x1]
        cH, cW = card.shape[:2]

        # 整张卡片 OCR
        results = read_region(card, min_conf=0.1)
        # 按 y 坐标分组，提取前3行（名字、特性、道具）和后4行（招式）
        split_x = cW // 2
        split_y = cH // 2  # 大概中线分左右

        # 按 y 坐标排序，然后按行分组
        results_sorted = sorted(results, key=lambda r: r[0][0][1])

        # 估计高度分组：前3个词汇应该是名字、特性、道具；后面应该是招式
        # 更简单的方法：按x坐标分左右列，但对同一行的词汇合并
        results_left = []
        results_right = []

        for box, text, conf in results:
            # 取框的中点x坐标判断属于左还是右
            center_x = sum(p[0] for p in box) / len(box)
            if center_x < split_x:
                results_left.append((box, text, conf))
            else:
                results_right.append((box, text, conf))

        slot_num = slot_idx + 1
        print(f"\n[Slot {slot_num}] OCR 识别 {len(results)} 个区域，左列 {len(results_left)}，右列 {len(results_right)}")
        for i, (box, text, conf) in enumerate(results):
            center_x = sum(p[0] for p in box) / len(box)
            print(f"  {i}: x={center_x:.0f} y={box[0][1]:.0f} '{text}' (conf={conf:.2f})")

        # 按 y 坐标分组提取（同一行的词汇合并）
        def group_by_y(items, y_threshold=20):
            """按 y 坐标分组，同一行的词汇合并"""
            if not items:
                return []

            sorted_items = sorted(items, key=lambda r: r[0][0][1])  # 按 y 排序
            groups = []
            current_group = [sorted_items[0]]

            for item in sorted_items[1:]:
                y_curr = item[0][0][1]
                y_prev = current_group[-1][0][0][1]
                if abs(y_curr - y_prev) < y_threshold:
                    current_group.append(item)
                else:
                    groups.append(current_group)
                    current_group = [item]
            groups.append(current_group)
            return groups

        # 分组
        left_groups = group_by_y(results_left)
        right_groups = group_by_y(results_right)

        print(f"  左列 {len(left_groups)} 组，右列 {len(right_groups)} 组")
        for i, group in enumerate(right_groups):
            print(f"    右组{i}: {[t for _, t, _ in group]}")

        # 提取数据（每组内按 x 排序后拼接）
        def extract_text_from_group(group):
            """从一组词汇中按 x 坐标排序后拼接"""
            if not group:
                return ""
            sorted_group = sorted(group, key=lambda r: r[0][0][0])  # 按 x 排序
            return " ".join(t for _, t, _ in sorted_group)

        nickname = extract_text_from_group(left_groups[0]) if len(left_groups) > 0 else ""
        ability = extract_text_from_group(left_groups[1]) if len(left_groups) > 1 else ""
        held_item = extract_text_from_group(left_groups[2]) if len(left_groups) > 2 else ""

        moves = []
        for group in right_groups:
            move_text = extract_text_from_group(group)
            if move_text:
                moves.append(move_text)

        # 识别 Pokemon
        pokemon_info = _identify_pokemon(img, card_info, slot_idx + 1, debug=False)

        cards.append({
            "slot": slot_idx + 1,
            "nickname": nickname,  # OCR 识别的昵称/标注
            "ability": ability,
            "held_item": held_item,
            "moves": moves,
        })
        pokemon_infos.append(pokemon_info)
        slot_num = slot_idx + 1
        print(f"  槽{slot_num}: {pokemon_info['name']} (score={pokemon_info['score']}) | {nickname} | {ability} | {held_item}")

    return pokemon_infos, cards


# ─────────────────────────────────────────────────────────────────────────────
# Stats 页解析
# ─────────────────────────────────────────────────────────────────────────────

def _parse_stats_screen(image_path: str, layout: dict = None) -> list[dict]:
    """提取 Stats 页数据"""
    img = cv2.imread(image_path)
    cards = []

    bg_color = np.array([204, 114, 137], dtype=np.float32)
    arrow_map = {key: (rx0, ry0, rx1, ry1) for key, rx0, ry0, rx1, ry1 in _STAT_ARROWS}
    stat_names = ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]

    # 保存卡片图片用于标注
    card_output_dir = Path(__file__).parent.parent.parent / "screenshots" / "stat_cards"
    card_output_dir.mkdir(parents=True, exist_ok=True)

    # 获取动态布局坐标（如果没有传入，则自己检测）
    if layout is None:
        layout = _get_card_coords(image_path)
    all_cards = layout['left_cards'] + layout['right_cards']  # 左3个 + 右3个

    for slot_idx, card_info in enumerate(all_cards):
        x0, y0 = card_info['x'], card_info['y']
        w, h = card_info['w'], card_info['h']
        x1, y1 = x0 + w, y0 + h

        card = img[y0:y1, x0:x1]
        cH, cW = card.shape[:2]

        # 保存卡片图片（带属性框和箭头框标注）
        slot_num = slot_idx + 1
        card_debug = card.copy()

        # 画属性框
        stat_names_row = ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]
        colors = {
            "hp": (0, 255, 0),        # 绿
            "attack": (255, 0, 0),   # 蓝
            "defense": (0, 255, 255),# 青
            "sp_atk": (0, 0, 255),   # 红
            "sp_def": (255, 255, 0), # 黄
            "speed": (255, 0, 255),  # 紫
        }

        # 左列属性框
        for i, y_top in enumerate(_STAT_LEFT_Y_TOPS):
            x0 = int(_STAT_LEFT_X * cW)
            y0 = int(y_top * cH)
            x1 = int((_STAT_LEFT_X + _STAT_BOX_W) * cW)
            y1 = int((y_top + _STAT_BOX_H) * cH)
            color = colors.get(stat_names_row[i], (255, 255, 255))
            cv2.rectangle(card_debug, (x0, y0), (x1, y1), color, 2)
            cv2.putText(card_debug, f"val_{stat_names_row[i]}", (x0, y0-5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # 右列属性框
        for i, y_top in enumerate(_STAT_RIGHT_Y_TOPS):
            x0 = int(_STAT_RIGHT_X * cW)
            y0 = int(y_top * cH)
            x1 = int((_STAT_RIGHT_X + _STAT_BOX_W) * cW)
            y1 = int((y_top + _STAT_BOX_H) * cH)
            color = colors.get(stat_names_row[i+3], (255, 255, 255))
            cv2.rectangle(card_debug, (x0, y0), (x1, y1), color, 2)
            cv2.putText(card_debug, f"val_{stat_names_row[i+3]}", (x0, y0-5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # 画箭头框（虚线）
        arrow_map = {key: (rx0, ry0, rx1, ry1) for key, rx0, ry0, rx1, ry1 in _STAT_ARROWS}
        for key, (rx0, ry0, rx1, ry1) in arrow_map.items():
            x0 = int(rx0 * cW)
            y0 = int(ry0 * cH)
            x1 = int(rx1 * cW)
            y1 = int(ry1 * cH)
            color = colors.get(key, (128, 128, 128))
            cv2.rectangle(card_debug, (x0, y0), (x1, y1), color, 1, cv2.LINE_AA)  # 细虚线
            cv2.putText(card_debug, f"arrow_{key}", (x0, y1+15),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

        card_path = card_output_dir / f"slot_{slot_num}.png"
        cv2.imwrite(str(card_path), card_debug)

        # OCR 卡片左右两部分（避免左右列框混淆）
        card_w = card.shape[1]
        card_mid = card_w // 2

        # 左部分（HP, Attack, Defense）
        card_left = card[:, :card_mid]
        results_left = read_region(card_left)

        # 右部分（Sp.Atk, Sp.Def, Speed）
        card_right = card[:, card_mid:]
        results_right = read_region(card_right)
        # 调整右部分的 x 坐标
        results_right = [(box, text, conf) if isinstance(box, str) else
                        ([[p[0] + card_mid, p[1]] for p in box], text, conf)
                        for box, text, conf in results_right]

        # 合并结果
        results = results_left + results_right

        # 提取名字
        nickname = results[0][1] if len(results) > 0 else ""

        # 从框中提取属性值
        def extract_from_box(box_x0, box_x1, box_y0, box_y1, stat_name=""):
            import re
            nums = []
            for box, text, conf in results:
                xs = [p[0] / cW for p in box]
                ys = [p[1] / cH for p in box]
                bx_min, bx_max = min(xs), max(xs)
                by_min, by_max = min(ys), max(ys)

                if bx_max >= box_x0 and bx_min <= box_x1 and by_max >= box_y0 and by_min <= box_y1:
                    # 从文本中提取数字
                    match = re.search(r'\d+', text)
                    if match:
                        center_x = (bx_min + bx_max) / 2
                        nums.append((center_x, int(match.group())))
            nums.sort()
            return [n for _, n in nums]

        stats = {}

        # 左列 3 个属性
        for i, y_top in enumerate(_STAT_LEFT_Y_TOPS):
            nums = extract_from_box(_STAT_LEFT_X, _STAT_LEFT_X + _STAT_BOX_W,
                                   y_top, y_top + _STAT_BOX_H)
            if len(nums) >= 1:
                stats[stat_names[i]] = nums[0]

        # 右列 3 个属性
        for i, y_top in enumerate(_STAT_RIGHT_Y_TOPS):
            nums = extract_from_box(_STAT_RIGHT_X, _STAT_RIGHT_X + _STAT_BOX_W,
                                   y_top, y_top + _STAT_BOX_H)
            if len(nums) >= 1:
                stats[stat_names[3 + i]] = nums[0]

        # 检测性格
        nature_inc = None
        nature_dec = None
        distance_threshold = 20

        arrow_colors = {}
        for key, (rx0, ry0, rx1, ry1) in arrow_map.items():
            _, debug_info = _detect_stat_color(card, rx0, ry0, rx1, ry1)
            arrow_colors[key] = debug_info

        for key, color_info in arrow_colors.items():
            if not color_info:
                continue

            b = color_info.get('b_mean', 0)
            g = color_info.get('g_mean', 0)
            r = color_info.get('r_mean', 0)
            current_color = np.array([b, g, r], dtype=np.float32)
            distance = np.linalg.norm(current_color - bg_color)

            if distance < distance_threshold:
                continue

            b_delta = b - bg_color[0]
            g_delta = g - bg_color[1]
            r_delta = r - bg_color[2]

            g_abs = abs(g_delta)
            r_abs = abs(r_delta)

            if g_abs > r_abs:
                nature_dec = key
            else:
                nature_inc = key

        # 生成性格字符串
        nature = None
        if nature_inc and nature_dec:
            nature = f"{nature_inc}↑/{nature_dec}↓"
        elif nature_inc:
            nature = f"{nature_inc}↑"
        elif nature_dec:
            nature = f"{nature_dec}↓"

        cards.append({
            "slot": slot_idx + 1,
            "nickname": nickname,
            "stats": stats,
            "nature": nature,
        })

        print(f"  槽{slot_num}: {nickname} | {stats} | 性格: {nature}")


    return cards

def parse_team(moves_screenshot: str, stats_screenshot: str) -> dict:
    detect_cards, moves_cards = _parse_moves_screen(moves_screenshot)

    # 从 moves 获取布局，传递给 stats（避免 stats 重复检测）
    layout = _get_card_coords(moves_screenshot)
    stats_cards = _parse_stats_screen(stats_screenshot, layout=layout)


    builder = PokemonBuilder()
    roster = []

    for i, (detect_card, move_card, stat_card) in enumerate(zip(detect_cards, moves_cards, stats_cards), 1):

        pokemon = builder.build_pokemon(
            detect_data=detect_card,
            moves_data=move_card,
            stats_data=stat_card,
            language="zh",
        )
        roster.append(pokemon)

    team = {
        "trainer_name": "",
        "roster": roster,
    }
    return team

def main() -> None:
    parser = argparse.ArgumentParser(description="从游戏截图生成 my_team.json")
    parser.add_argument("--moves",  required=True)
    parser.add_argument("--stats",  required=True)
    args = parser.parse_args()

    print("── Moves & More ──")
    moves_cards = _parse_moves_screen(args.moves)

    print("\n── Stats ──")
    stats_cards = _parse_stats_screen(args.stats)
    print(moves_cards)
    print(stats_cards)

    


if __name__ == "__main__":
    main()
