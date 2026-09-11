import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from pokepilot.tools.logger_util import setup_logger

logger = setup_logger(__name__)

from pokepilot.common.pokemon_builder import PokemonBuilder
from pokepilot.tools.ocr_engine import read_region
from pokepilot.common.pokemon_detect import get_detector

debug_dir = "debug_output/my_team"
# ─────────────────────────────────────────────────────────────────────────────
# Load configuration from JSON
# ─────────────────────────────────────────────────────────────────────────────
def _load_card_config() -> dict:
    """每次调用时读取布局配置（前端保存后无需重启即生效）"""
    config_path = Path(__file__).parent.parent.parent / "config" / "card_layout.json"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    logger.debug(f"Loaded card config from: {config_path}")
    return config


def _derive_card_config(config: dict) -> dict:
    """从原始配置提取解析所需的派生参数"""
    return {
        'layout': config['layout'],
        'regions': {
            'sprite': config['regions']['sprite'],
            'type1': config['regions']['type1'],
            'type2': config['regions']['type2'],
        },
        'bg_colors_multi': config['bg_colors_multi'],
        'text_regions': config['text_regions'],
    }


def _get_card_config() -> dict:
    """当前卡片布局配置（每次调用实时读文件）"""
    return _derive_card_config(_load_card_config())


def _region_px(region: dict, cW: int, cH: int) -> tuple[int, int, int, int]:
    """把相对坐标 region 转成像素矩形 (x0, y0, x1, y1)"""
    return (
        int(region['rx0'] * cW),
        int(region['ry0'] * cH),
        int(region['rx1'] * cW),
        int(region['ry1'] * cH),
    )


def _extract_regions(img: np.ndarray, card_info: dict, cfg: dict) -> dict:
    """从卡牌框提取三个矩形（sprite、type1、type2），可能超出卡片框边界"""
    x, y, w, h = card_info['x'], card_info['y'], card_info['w'], card_info['h']
    regions = {}
    regions_cfg = cfg['regions']

    for label in ('sprite', 'type1', 'type2'):
        region_cfg = regions_cfg[label]
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


def _identify_pokemon(img: np.ndarray, card_info: dict, slot_idx: int, debug=False, cfg: dict | None = None) -> dict:
    """识别卡牌中的 Pokemon"""
    cfg = cfg or _get_card_config()
    regions = _extract_regions(img, card_info, cfg)

    detector = get_detector()
    result = detector.detect(
        regions['sprite'],
        regions['type1'],
        regions['type2'],
        bg_removal="multi",
        bg_colors=cfg['bg_colors_multi'],
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
        sprite_clean = _remove_bg_multi(regions['sprite'], cfg['bg_colors_multi'], tolerance=40)

        cv2.imwrite(str(pokemon_dir / f"slot_{slot_idx}_sprite_clean.png"), sprite_clean)
        logger.debug(f"三个 region 已保存：{pokemon_dir}/slot_{slot_idx}_*.png (原始和去背景版)")

    return result


def _get_card_coords(cfg: dict) -> dict:
    """
    获取6个卡片的坐标（从配置文件）
    返回格式：{'left_cards': [...], 'right_cards': [...]}
    """
    layout = cfg['layout']
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
    cfg = _get_card_config()
    layout = _get_card_coords(cfg)
    all_cards = layout['left_cards'] + layout['right_cards']

    pokemon_infos = []
    for slot_idx, card_info in enumerate(all_cards):
        pokemon_info = _identify_pokemon(img, card_info, slot_idx, debug=debug, cfg=cfg)
        pokemon_infos.append(pokemon_info)
        logger.info(f"[Slot {slot_idx + 1}] {pokemon_info['slug']:25s} score={pokemon_info['score']:.1f} 属性={pokemon_info['types']}")

    return pokemon_infos


def _read_element_text(card: np.ndarray, region: dict, min_conf: float = 0.1) -> str:
    """逐元素裁剪并 OCR 单行文字，按 x 顺序拼接"""
    cH, cW = card.shape[:2]
    x0, y0, x1, y1 = _region_px(region, cW, cH)
    patch = card[y0:y1, x0:x1]
    results = read_region(patch, min_conf=min_conf)
    if not results:
        return ""
    return " ".join(text for _, text, _ in sorted(results, key=lambda r: r[0][0][0])).strip()


def _read_stat_number(card: np.ndarray, region_x: float, y_top: float, cfg: dict,
                      allowlist: str = "0123456789",
                      num_cfg: dict | None = None) -> int | None:
    """逐数字框裁剪并 OCR 数值，取最左侧第一个数字串（主数值在框左侧）；
    ev_numbers 等其它数字区域通过 num_cfg 传入（含 box_w/box_h）"""
    import re

    stat_num = num_cfg or cfg['text_regions']['stat_numbers']
    cH, cW = card.shape[:2]
    x0 = int(region_x * cW)
    y0 = int(y_top * cH)
    x1 = int((region_x + stat_num['box_w']) * cW)
    y1 = int((y_top + stat_num['box_h']) * cH)
    patch = card[y0:y1, x0:x1]
    results = read_region(patch, min_conf=0.1, allowlist=allowlist)
    if not results:
        return None
    nums = []
    for box, text, conf in results:
        match = re.search(r'\d+', text)
        if match:
            nums.append((box[0][0], int(match.group())))
    if not nums:
        return None
    nums.sort()
    return nums[0][1]


def _parse_moves_screen(image_path: str, debug: bool = False) -> list[dict]:
    """
    从 Moves & More 页识别昵称、特性、道具、招式

    返回: (cards列表, layout字典)
    """
    img = cv2.imread(image_path)
    cfg = _get_card_config()
    text_regions = cfg['text_regions']
    text_nick = text_regions['nickname']
    text_ability = text_regions['ability']
    text_item = text_regions['held_item']
    text_moves = text_regions['moves']

    cards = []
    layout = _get_card_coords(cfg)
    all_cards = layout['left_cards'] + layout['right_cards']

    moves_output_dir = None
    if debug:
        moves_output_dir = Path(debug_dir) / "moves_cards"
        moves_output_dir.mkdir(parents=True, exist_ok=True)

    for slot_idx, card_info in enumerate(all_cards):
        x0, y0 = card_info['x'], card_info['y']
        w, h = card_info['w'], card_info['h']

        card = img[y0:y0 + h, x0:x0 + w]

        # 逐元素单独裁剪 OCR：昵称、特性、道具、4 个招式（区域坐标来自 text_regions 配置）
        nickname = _read_element_text(card, text_nick)
        ability = _read_element_text(card, text_ability)
        held_item = _read_element_text(card, text_item)
        moves = []
        for move_region in text_moves:
            move_text = _read_element_text(card, move_region)
            if move_text:
                moves.append(move_text)

        slot_num = slot_idx + 1
        logger.info(f"[Slot {slot_num}] 昵称={nickname!r} 特性={ability!r} 道具={held_item!r} 招式={moves}")

        if debug:
            card_debug = card.copy()
            cH, cW = card.shape[:2]

            region_colors = {
                "nick": (255, 255, 255),     # 白 - 昵称
                "ability": (255, 0, 255),    # 品红 - 特性
                "item": (255, 255, 0),       # 青 - 道具
            }
            move_color = (0, 165, 255)       # 橙 - 招式

            for label, region in [("nick", text_nick), ("ability", text_ability),
                                  ("item", text_item)] + \
                                [(f"move{i+1}", m) for i, m in enumerate(text_moves)]:
                bx0, by0, bx1, by1 = _region_px(region, cW, cH)
                color = move_color if label.startswith("move") else region_colors[label]
                cv2.rectangle(card_debug, (bx0, by0), (bx1, by1), color, 2)
                cv2.putText(card_debug, label, (bx0, by1 + 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

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
    从 Stats 页识别属性值和能力值加点

    性格不再通过箭头颜色识别，而是由 PokemonBuilder.infer_nature_and_evs
    依据「最终能力值 + 加点 + 种族值」按公式反推（见 build_pokemon / parse_team_init）。

    返回: cards列表，元素 {slot, nickname, stats, evs, nature}
          evs 只含成功读到的加点（未读到 = 未加点或漏读，由推断逻辑兜底）
          nature 此处恒为 ""，占位供前端校对字段
    """
    img = cv2.imread(image_path)
    cfg = _get_card_config()
    text_regions = cfg['text_regions']
    text_nick = text_regions['nickname']
    stat_num = text_regions['stat_numbers']
    ev_num = text_regions.get('ev_numbers')

    cards = []

    stat_names = ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]

    stats_output_dir = None
    if debug:
        stats_output_dir = Path(debug_dir) / "stats_cards"
        stats_output_dir.mkdir(parents=True, exist_ok=True)

    layout = _get_card_coords(cfg)
    all_cards = layout['left_cards'] + layout['right_cards']

    for slot_idx, card_info in enumerate(all_cards):
        x0, y0 = card_info['x'], card_info['y']
        w, h = card_info['w'], card_info['h']

        card = img[y0:y0 + h, x0:x0 + w]
        cH, cW = card.shape[:2]

        slot_num = slot_idx + 1

        # 逐元素单独裁剪 OCR：昵称 + 左右两列各 3 个数字框（allowlist 仅数字）
        nickname = _read_element_text(card, text_nick)

        stats = {}
        evs = {}
        for i, y_top in enumerate(stat_num['y_tops']):
            val = _read_stat_number(card, stat_num['left_x'], y_top, cfg)
            if val is not None:
                stats[stat_names[i]] = val
            if ev_num:
                ev_val = _read_stat_number(card, ev_num['left_x'], y_top, cfg, num_cfg=ev_num)
                if ev_val is not None:
                    evs[stat_names[i]] = ev_val

        for i, y_top in enumerate(stat_num['y_tops']):
            val = _read_stat_number(card, stat_num['right_x'], y_top, cfg)
            if val is not None:
                stats[stat_names[3 + i]] = val
            if ev_num:
                ev_val = _read_stat_number(card, ev_num['right_x'], y_top, cfg, num_cfg=ev_num)
                if ev_val is not None:
                    evs[stat_names[3 + i]] = ev_val

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

            for i, y_top in enumerate(stat_num['y_tops']):
                for xf in (stat_num['left_x'], stat_num['right_x']):
                    x0_px = int(xf * cW)
                    y0_px = int(y_top * cH)
                    x1_px = int((xf + stat_num['box_w']) * cW)
                    y1_px = int((y_top + stat_num['box_h']) * cH)
                    color = colors.get(stat_names[i], (255, 255, 255))
                    cv2.rectangle(card_debug, (x0_px, y0_px), (x1_px, y1_px), color, 2)

            # 画加点数字框（虚线）
            if ev_num:
                for i, y_top in enumerate(ev_num['y_tops']):
                    for xf in (ev_num['left_x'], ev_num['right_x']):
                        x0_px = int(xf * cW)
                        y0_px = int(y_top * cH)
                        x1_px = int((xf + ev_num['box_w']) * cW)
                        y1_px = int((y_top + ev_num['box_h']) * cH)
                        color = colors.get(stat_names[i], (128, 128, 128))
                        cv2.rectangle(card_debug, (x0_px, y0_px), (x1_px, y1_px), color, 1, cv2.LINE_AA)

            card_path = stats_output_dir / f"slot_{slot_num}.png"
            cv2.imwrite(str(card_path), card_debug)
            logger.debug(f"Stats 卡片标注图已保存：{card_path}")

        cards.append({
            "slot": slot_idx + 1,
            "nickname": nickname,
            "stats": stats,
            "evs": evs,
            "nature": "",
        })
        logger.info(f"槽{slot_num}: {nickname} | {stats} | 加点: {evs}")

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

    # 预填性格与 EV：由「最终能力值 + 加点 + 种族值」按公式反推（供草稿校对页展示）
    builder = PokemonBuilder()
    for detect_card, stat_card in zip(detect_cards, stats_cards):
        pokemon_info = builder.db.get_pokemon(detect_card.get('slug', '')) or {}
        base_stats = pokemon_info.get('base_stats') or {}
        stats = stat_card.get('stats') or {}
        if not base_stats or not stats:
            continue
        nature, evs, warnings = builder.infer_nature_and_evs(base_stats, stats, stat_card.get('evs') or {})
        for w in warnings:
            logger.warning(f"槽{stat_card.get('slot')}: {w}")
        stat_card['nature'] = nature
        stat_card['evs'] = evs
        if warnings:
            stat_card['warnings'] = warnings
        logger.info(f"槽{stat_card.get('slot')}: 性格={nature} EV={evs}")

    return detect_cards, moves_cards, stats_cards
