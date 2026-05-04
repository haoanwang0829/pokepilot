import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from pokepilot.tools.logger_util import setup_logger

logger = setup_logger(__name__)

from pokepilot.common.pokemon_builder import PokemonBuilder
from pokepilot.tools.ocr_engine import read_region
from pokepilot.common.pokemon_detect import PokemonDetector

debug_dir = "debug_output/my_team"
# ─────────────────────────────────────────────────────────────────────────────
# Load configuration from JSON
# ─────────────────────────────────────────────────────────────────────────────
def _load_card_config():
    """Load card layout configuration from JSON file"""
    config_path = Path(__file__).parent.parent.parent / "config" / "card_layout.json"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    logger.debug(f"Loaded card config from: {config_path}")
    return config

_CARD_CONFIG = _load_card_config()

# 从配置中提取参数
_SPRITE_REGION = _CARD_CONFIG['regions']['sprite']
_TYPE1_REGION = _CARD_CONFIG['regions']['type1']
_TYPE2_REGION = _CARD_CONFIG['regions']['type2']
_BG_COLORS_MULTI = _CARD_CONFIG['bg_colors_multi']

# Stats 页配置
_STAT_BOXES_CONFIG = _CARD_CONFIG['stat_boxes']
_STAT_BOX_W = _STAT_BOXES_CONFIG['box_w']
_STAT_BOX_H = _STAT_BOXES_CONFIG['box_h']
_STAT_LEFT_X = _STAT_BOXES_CONFIG['left_x']
_STAT_RIGHT_X = _STAT_BOXES_CONFIG['right_x']
_STAT_Y_TOPS = _STAT_BOXES_CONFIG['y_tops']

# 性格箭头位置从配置加载
_STAT_ARROWS = [(a['name'], a['x'], a['y'], a['size']) for a in _CARD_CONFIG['stat_arrows']]


_pokemon_detector = None  # 全局单例


def _get_detector() -> PokemonDetector:
    """获取 PokemonDetector 单例"""
    global _pokemon_detector
    if _pokemon_detector is None:
        _pokemon_detector = PokemonDetector()
    return _pokemon_detector


def _extract_regions(img: np.ndarray, card_info: dict) -> dict:
    """从卡牌框提取三个矩形（sprite、type1、type2），可能超出卡片框边界"""
    x, y, w, h = card_info['x'], card_info['y'], card_info['w'], card_info['h']
    regions = {}

    for label, region_cfg in [
        ('sprite', _SPRITE_REGION),
        ('type1', _TYPE1_REGION),
        ('type2', _TYPE2_REGION),
    ]:
        rx = region_cfg['rx']
        ry = region_cfg['ry']
        size = region_cfg['size']

        rx0 = int(x + rx * w)
        ry0 = int(y + ry * h)
        rx1 = rx0 + size
        ry1 = ry0 + size

        extracted = img[ry0:ry1, rx0:rx1]
        regions[label] = extracted

    return regions


def _identify_pokemon(img: np.ndarray, card_info: dict, slot_idx: int, debug=False) -> dict:
    """识别卡牌中的 Pokemon"""
    regions = _extract_regions(img, card_info)

    detector = _get_detector()
    result = detector.detect(
        regions['sprite'],
        regions['type1'],
        regions['type2'],
        bg_removal="multi",
        bg_colors=_BG_COLORS_MULTI,
    )
    if debug == True:
        from pokepilot.common.pokemon_detect import _remove_bg_multi
        pokemon_dir = Path(debug_dir) / "pokemon"
        pokemon_dir.mkdir(parents=True, exist_ok=True)

        # 原始图片
        cv2.imwrite(str(pokemon_dir / f"slot_{slot_idx}_sprite.png"), regions['sprite'])
        cv2.imwrite(str(pokemon_dir / f"slot_{slot_idx}_type1.png"), regions['type1'])
        cv2.imwrite(str(pokemon_dir / f"slot_{slot_idx}_type2.png"), regions['type2'])

        # 去除背景后的图片
        sprite_clean = _remove_bg_multi(regions['sprite'], _BG_COLORS_MULTI, tolerance=40)

        cv2.imwrite(str(pokemon_dir / f"slot_{slot_idx}_sprite_clean.png"), sprite_clean)
        logger.debug(f"三个 region 已保存：{pokemon_dir}/slot_{slot_idx}_*.png (原始和去背景版)")

    return result


def _get_card_coords() -> dict:
    """
    获取6个卡片的坐标（从配置文件）
    返回格式：{'left_cards': [...], 'right_cards': [...]}
    """
    layout = _CARD_CONFIG['layout']
    top_x = layout['top_x']
    top_y = layout['top_y']
    rect_w = layout['rect_w']
    rect_h = layout['rect_h']
    v_gap = layout['vertical_gap']
    h_gap = layout['horizontal_gap']

    cards = {'left_cards': [], 'right_cards': []}

    # 左边3个卡片
    for i in range(3):
        y = top_y + i * (rect_h + v_gap)
        cards['left_cards'].append({
            'x': top_x,
            'y': y,
            'w': rect_w,
            'h': rect_h
        })

    # 右边3个卡片
    right_x = top_x + rect_w + h_gap
    for i in range(3):
        y = top_y + i * (rect_h + v_gap)
        cards['right_cards'].append({
            'x': right_x,
            'y': y,
            'w': rect_w,
            'h': rect_h
        })

    return cards


def _parse_pokemons(image_path: str, debug: bool = False) -> list[dict]:
    """
    从图片中识别所有 Pokemon

    返回: (pokemon_infos列表, layout字典)
    """
    img = cv2.imread(image_path)
    layout = _get_card_coords()
    all_cards = layout['left_cards'] + layout['right_cards']

    pokemon_infos = []
    for slot_idx, card_info in enumerate(all_cards):
        pokemon_info = _identify_pokemon(img, card_info, slot_idx, debug=debug)
        pokemon_infos.append(pokemon_info)
        logger.info(f"[Slot {slot_idx + 1}] {pokemon_info['slug']:25s} score={pokemon_info['score']:.1f} 属性={pokemon_info['types']}")

    return pokemon_infos


def _group_by_y(items: list, y_threshold: float = 20) -> list[list]:
    """按 y 坐标分组，同一行的词汇合并"""
    if not items:
        return []

    sorted_items = sorted(items, key=lambda r: r[0][0][1])
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


def _extract_text_from_group(group: list) -> str:
    """从一组词汇中按 x 坐标排序后拼接"""
    if not group:
        return ""
    sorted_group = sorted(group, key=lambda r: r[0][0][0])
    return " ".join(t for _, t, _ in sorted_group)


def _detect_stat_color(card: np.ndarray, rx0: float, ry0: float, rx1: float, ry1: float) -> str:
    """
    检测箭头区域的颜色 —— 去除背景后判断箭头颜色
    返回: "red" (增加↑) / "blue" (减少↓) / "neutral" (无箭头)
    """
    H, W = card.shape[:2]

    x0 = int(rx0 * W)
    y0 = int(ry0 * H)
    x1 = int(rx1 * W)
    y1 = int(ry1 * H)

    if x0 >= W or y0 >= H or x1 <= x0 or y1 <= y0:
        return "neutral"

    x0 = max(0, x0)
    x1 = min(x1, W)
    y0 = max(0, y0)
    y1 = min(y1, H)

    region = card[y0:y1, x0:x1]
    if region.size == 0:
        return "neutral"

    # 背景色范围：RGB (138-147, 121-128, 210-222) → BGR
    # 计算中间值，然后取 ±40 的范围
    b_mid = (210 + 222) / 2  # 216
    g_mid = (121 + 128) / 2  # 124.5
    r_mid = (138 + 147) / 2  # 142.5
    tolerance = 40

    b, g, r = region[:, :, 0], region[:, :, 1], region[:, :, 2]

    # 去除背景色像素
    is_background = (np.abs(b.astype(float) - b_mid) <= tolerance) & \
                    (np.abs(g.astype(float) - g_mid) <= tolerance) & \
                    (np.abs(r.astype(float) - r_mid) <= tolerance)

    foreground_mask = ~is_background
    if np.sum(foreground_mask) < 10:
        return "neutral"

    fg_pixels = region[foreground_mask]
    avg_color = np.mean(fg_pixels, axis=0)
    b_mean, g_mean, r_mean = avg_color[0], avg_color[1], avg_color[2]

    if r_mean > g_mean and r_mean > b_mean:
        return "red"
    elif b_mean > g_mean and b_mean > r_mean:
        return "blue"
    else:
        return "neutral"


def _parse_moves_screen(image_path: str, debug: bool = False) -> list[dict]:
    """
    从 Moves & More 页识别昵称、特性、道具、招式

    返回: (cards列表, layout字典)
    """
    img = cv2.imread(image_path)
    cards = []
    layout = _get_card_coords()
    all_cards = layout['left_cards'] + layout['right_cards']

    moves_output_dir = None
    if debug:
        moves_output_dir = Path(debug_dir) / "moves_cards"
        moves_output_dir.mkdir(parents=True, exist_ok=True)

    for slot_idx, card_info in enumerate(all_cards):
        x0, y0 = card_info['x'], card_info['y']
        w, h = card_info['w'], card_info['h']
        x1, y1 = x0 + w, y0 + h

        card = img[y0:y1, x0:x1]
        cW, cH = card.shape[1], card.shape[0]

        results = read_region(card, min_conf=0.1)
        split_x = cW // 2

        results_left = []
        results_right = []

        for box, text, conf in results:
            center_x = sum(p[0] for p in box) / len(box)
            if center_x < split_x:
                results_left.append((box, text, conf))
            else:
                results_right.append((box, text, conf))

        slot_num = slot_idx + 1
        logger.info(f"[Slot {slot_num}] OCR 识别 {len(results)} 个区域，左列 {len(results_left)}，右列 {len(results_right)}")

        left_groups = _group_by_y(results_left)
        right_groups = _group_by_y(results_right)

        nickname = _extract_text_from_group(left_groups[0]) if len(left_groups) > 0 else ""
        ability = _extract_text_from_group(left_groups[1]) if len(left_groups) > 1 else ""
        held_item = _extract_text_from_group(left_groups[2]) if len(left_groups) > 2 else ""

        moves = []
        for group in right_groups:
            move_text = _extract_text_from_group(group)
            if move_text:
                moves.append(move_text)

        if debug and results:
            card_debug = card.copy()
            pil_img = Image.fromarray(cv2.cvtColor(card_debug, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img)
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/simhei.ttf", 12)
            except:
                font = ImageFont.load_default()

            for box, text, conf in results:
                pts = np.int32(box)
                cv2.polylines(card_debug, [pts], True, (0, 255, 0), 1)
                x, y = int(box[0][0]), int(box[0][1]) - 15
                text_label = f"{text} {conf:.2f}"
                draw.text((x, y), text_label, fill=(0, 255, 255), font=font)

            card_debug = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            card_path = moves_output_dir / f"slot_{slot_num}_ocr.png"
            cv2.imwrite(str(card_path), card_debug)
            logger.debug(f"OCR 标注图已保存：{card_path}")

        cards.append({
            "slot": slot_idx + 1,
            "nickname": nickname,
            "ability": ability,
            "held_item": held_item,
            "moves": moves,
        })
        logger.info(f"槽{slot_num}: {nickname} | {ability} | {held_item}")

    return cards


def _parse_stats_screen(image_path: str, debug: bool = False) -> list[dict]:
    """
    从 Stats 页识别属性值和性格

    返回: cards列表
    """
    import re

    img = cv2.imread(image_path)
    cards = []

    arrow_map = {key: (x, y, x + size_px / 738, y + size_px / 186) for key, x, y, size_px in _STAT_ARROWS}
    stat_names = ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]

    stats_output_dir = None
    if debug:
        stats_output_dir = Path(debug_dir) / "stats_cards"
        stats_output_dir.mkdir(parents=True, exist_ok=True)

    layout = _get_card_coords()
    all_cards = layout['left_cards'] + layout['right_cards']

    for slot_idx, card_info in enumerate(all_cards):
        x0, y0 = card_info['x'], card_info['y']
        w, h = card_info['w'], card_info['h']
        x1, y1 = x0 + w, y0 + h

        card = img[y0:y1, x0:x1]
        cH, cW = card.shape[:2]

        slot_num = slot_idx + 1

        card_w = card.shape[1]
        card_mid = card_w // 2

        card_left = card[:, :card_mid]
        results_left = read_region(card_left)

        card_right = card[:, card_mid:]
        results_right = read_region(card_right)
        results_right = [(box, text, conf) if isinstance(box, str) else
                        ([[p[0] + card_mid, p[1]] for p in box], text, conf)
                        for box, text, conf in results_right]

        results = results_left + results_right

        nickname = results[0][1] if len(results) > 0 else ""

        def extract_from_box(box_x0, box_x1, box_y0, box_y1):
            nums = []
            for box, text, conf in results:
                xs = [p[0] / cW for p in box]
                ys = [p[1] / cH for p in box]
                bx_min, bx_max = min(xs), max(xs)
                by_min, by_max = min(ys), max(ys)

                if bx_max >= box_x0 and bx_min <= box_x1 and by_max >= box_y0 and by_min <= box_y1:
                    match = re.search(r'\d+', text)
                    if match:
                        center_x = (bx_min + bx_max) / 2
                        nums.append((center_x, int(match.group())))
            nums.sort()
            return [n for _, n in nums]

        stats = {}

        for i, y_top in enumerate(_STAT_Y_TOPS):
            nums = extract_from_box(_STAT_LEFT_X, _STAT_LEFT_X + _STAT_BOX_W,
                                   y_top, y_top + _STAT_BOX_H)
            if len(nums) >= 1:
                stats[stat_names[i]] = nums[0]

        for i, y_top in enumerate(_STAT_Y_TOPS):
            nums = extract_from_box(_STAT_RIGHT_X, _STAT_RIGHT_X + _STAT_BOX_W,
                                   y_top, y_top + _STAT_BOX_H)
            if len(nums) >= 1:
                stats[stat_names[3 + i]] = nums[0]

        nature_inc = None
        nature_dec = None

        for key, (rx0, ry0, rx1, ry1) in arrow_map.items():
            color = _detect_stat_color(card, rx0, ry0, rx1, ry1)

            if color == "red":
                nature_inc = key
            elif color == "blue":
                nature_dec = key

        nature = None
        if nature_inc and nature_dec:
            nature = f"{nature_inc}↑/{nature_dec}↓"
        elif nature_inc:
            nature = f"{nature_inc}↑"
        elif nature_dec:
            nature = f"{nature_dec}↓"

        if debug:
            card_debug = card.copy()
            colors = {
                "hp": (0, 255, 0),
                "attack": (255, 0, 0),
                "defense": (0, 255, 255),
                "sp_atk": (0, 0, 255),
                "sp_def": (255, 255, 0),
                "speed": (255, 0, 255),
            }
            stat_names_row = ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]

            for i, y_top in enumerate(_STAT_Y_TOPS):
                x0 = int(_STAT_LEFT_X * cW)
                y0 = int(y_top * cH)
                x1 = int((_STAT_LEFT_X + _STAT_BOX_W) * cW)
                y1 = int((y_top + _STAT_BOX_H) * cH)
                color = colors.get(stat_names_row[i], (255, 255, 255))
                cv2.rectangle(card_debug, (x0, y0), (x1, y1), color, 2)

            for i, y_top in enumerate(_STAT_Y_TOPS):
                x0 = int(_STAT_RIGHT_X * cW)
                y0 = int(y_top * cH)
                x1 = int((_STAT_RIGHT_X + _STAT_BOX_W) * cW)
                y1 = int((y_top + _STAT_BOX_H) * cH)
                color = colors.get(stat_names_row[i+3], (255, 255, 255))
                cv2.rectangle(card_debug, (x0, y0), (x1, y1), color, 2)

            # 画箭头框（虚线）
            for key, (rx0, ry0, rx1, ry1) in arrow_map.items():
                x0 = int(rx0 * cW)
                y0 = int(ry0 * cH)
                x1 = int(rx1 * cW)
                y1 = int(ry1 * cH)
                color = colors.get(key, (128, 128, 128))
                cv2.rectangle(card_debug, (x0, y0), (x1, y1), color, 1, cv2.LINE_AA)
                cv2.putText(card_debug, f"arrow_{key}", (x0, y1+15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

            card_path = stats_output_dir / f"slot_{slot_num}.png"
            cv2.imwrite(str(card_path), card_debug)
            logger.debug(f"Stats 卡片标注图已保存：{card_path}")

        cards.append({
            "slot": slot_idx + 1,
            "nickname": nickname,
            "stats": stats,
            "nature": nature,
        })
        logger.info(f"槽{slot_num}: {nickname} | {stats} | 性格: {nature}")

    return cards


def parse_team(moves_screenshot: str, stats_screenshot: str, debug: bool = False) -> dict:
    """
    从两张截图识别并构建完整队伍

    返回: { 'trainer_name': '', 'roster': [...] }
    """
    detect_cards = _parse_pokemons(moves_screenshot, debug=debug)
    moves_cards = _parse_moves_screen(moves_screenshot, debug=debug)
    stats_cards = _parse_stats_screen(stats_screenshot, debug=debug)

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




def parse_team_init(moves_screenshot: str, stats_screenshot: str, debug: bool = False) -> dict:
    detect_cards = _parse_pokemons(moves_screenshot, debug=debug)
    moves_cards = _parse_moves_screen(moves_screenshot, debug=debug)
    stats_cards = _parse_stats_screen(stats_screenshot, debug=debug)

    return detect_cards, moves_cards, stats_cards
