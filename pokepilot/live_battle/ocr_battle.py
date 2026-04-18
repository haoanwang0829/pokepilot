"""
对战实时 OCR —— 从战场截图识别关键信息

1. 对手宝可梦名字（模糊匹配到 roster）
2. 我方宝可梦名字（模糊匹配到 roster）
3. 对话框文本（战场事件、招式效果等）

用法:
    python -m pokepilot.battle.ocr_battle <screenshot>
"""

import sys
import json
from pathlib import Path
from difflib import get_close_matches

import cv2
import numpy as np

from pokepilot.tools.ocr_engine import read_crop_text

_ROOT = Path(__file__).parent.parent.parent
_ROSTER_PATH = _ROOT / "data" / "champions_roster.json"

# 预加载 roster 中所有唯一的宝可梦名字（用于模糊匹配）
_POKEMON_NAMES: set[str] = set()
try:
    roster_data = json.loads(_ROSTER_PATH.read_text(encoding="utf-8"))
    _POKEMON_NAMES = {p["name"] for p in roster_data.get("pokemon", [])}
except Exception:
    pass

# ── 截图区域坐标（归一化，基于 1920×1080）──────────────────────────────────

# 我方宝可梦名字区域（左下角，只取文字部分，不含 HP 条纹）
MY_POKEMON = (0.0208, 0.8565, 0.1500, 0.9000)

# 对手宝可梦名字区域（右上角，只取文字部分）
OPP_POKEMON = (0.8200, 0.0287, 0.9964, 0.0850)

# 对话框文本区域（中间下方）
DIALOG_BOX = (0.1469, 0.7250, 0.9057, 0.8620)


def _denorm(img: np.ndarray, rx0: float, ry0: float, rx1: float, ry1: float) -> tuple[int, int, int, int]:
    """将归一化坐标转换为像素坐标"""
    H, W = img.shape[:2]
    return (
        int(rx0 * W),
        int(ry0 * H),
        int(rx1 * W),
        int(ry1 * H),
    )


def _normalize_name(ocr_text: str) -> str | None:
    """
    从 OCR 文字匹配到最接近的宝可梦名字。
    返回 roster 中的宝可梦名字，或 None（未匹配到）。
    """
    text = ocr_text.strip().lower()
    if not text:
        return None

    # 精确匹配
    if text in _POKEMON_NAMES:
        return text

    # 模糊匹配（取最相似的，相似度需 > 0.6）
    matches = get_close_matches(text, _POKEMON_NAMES, n=1, cutoff=0.6)
    return matches[0] if matches else None


def extract_battle_info(screenshot: str) -> dict:
    """
    从对战截图提取关键信息。
    返回 {
        "my_pokemon":  str | None,    # 我方出场宝可梦名字（已匹配）
        "opp_pokemon": str | None,    # 对手出场宝可梦名字（已匹配）
        "dialog_text": str,           # 对话框文本（战场事件）
        "ocr_raw": {
            "my_text": str,           # OCR 原始文字
            "opp_text": str,
        }
    }
    """
    img = cv2.imread(screenshot)
    if img is None:
        raise FileNotFoundError(screenshot)

    # 提取各区域文字
    my_x0, my_y0, my_x1, my_y1       = _denorm(img, *MY_POKEMON)
    opp_x0, opp_y0, opp_x1, opp_y1   = _denorm(img, *OPP_POKEMON)
    dlg_x0, dlg_y0, dlg_x1, dlg_y1   = _denorm(img, *DIALOG_BOX)

    my_text_raw  = read_crop_text(img, my_x0, my_y0, my_x1, my_y1, min_conf=0.3)
    opp_text_raw = read_crop_text(img, opp_x0, opp_y0, opp_x1, opp_y1, min_conf=0.3)
    dlg_text     = read_crop_text(img, dlg_x0, dlg_y0, dlg_x1, dlg_y1, min_conf=0.3)

    # 清理文字（去掉多余空格/换行，只取第一个单词作为宝可梦名字）
    my_text  = " ".join(my_text_raw.split()).lower().split()[0] if my_text_raw else ""
    opp_text = " ".join(opp_text_raw.split()).lower().split()[0] if opp_text_raw else ""
    dialog_text = " ".join(dlg_text.split())

    # 匹配到 roster
    my_pokemon_matched  = _normalize_name(my_text) if my_text else None
    opp_pokemon_matched = _normalize_name(opp_text) if opp_text else None

    return {
        "my_pokemon":  my_pokemon_matched,
        "opp_pokemon": opp_pokemon_matched,
        "dialog_text": dialog_text,
        "ocr_raw": {
            "my_text": my_text,
            "opp_text": opp_text,
        }
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python -m pokepilot.battle.ocr_battle <screenshot>")
        sys.exit(1)

    screenshot = sys.argv[1]
    info = extract_battle_info(screenshot)
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
