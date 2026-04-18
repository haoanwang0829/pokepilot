"""
ROI 区域定义 —— 所有坐标均为归一化值 (0.0~1.0)，相对于画面宽高。
格式: (x, y, w, h)，左上角 + 宽高。
基准分辨率: 1920x1080
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    x: float  # 左上角 x（占画面宽度比例）
    y: float  # 左上角 y（占画面高度比例）
    w: float  # 宽度比例
    h: float  # 高度比例
    label: str = ""

    def to_pixels(self, frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
        """转换为像素坐标 (x1, y1, x2, y2)"""
        x1 = int(self.x * frame_w)
        y1 = int(self.y * frame_h)
        x2 = int((self.x + self.w) * frame_w)
        y2 = int((self.y + self.h) * frame_h)
        return x1, y1, x2, y2

    def crop(self, frame):
        """直接从帧中裁切该区域，返回子图"""
        import cv2
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = self.to_pixels(w, h)
        return frame[y1:y2, x1:x2]


# ---------------------------------------------------------------------------
# 单打 (Single Battle)
# ---------------------------------------------------------------------------

class SingleRegions:
    # ---------- 我方宝可梦（左下角卡片）----------
    MY_NAME      = Region(0.037, 0.872, 0.110, 0.027, "my_name")
    MY_HP_BAR    = Region(0.037, 0.904, 0.113, 0.017, "my_hp_bar")
    MY_HP_TEXT   = Region(0.048, 0.926, 0.100, 0.022, "my_hp_text")   # e.g. "167/167"
    MY_TIMER     = Region(0.052, 0.962, 0.043, 0.018, "my_timer")     # e.g. "06:55"

    # ---------- 对方宝可梦（右上角卡片）----------
    ENEMY_NAME   = Region(0.462, 0.020, 0.065, 0.026, "enemy_name")
    ENEMY_HP_BAR = Region(0.443, 0.047, 0.100, 0.015, "enemy_hp_bar")
    ENEMY_HP_PCT = Region(0.543, 0.044, 0.032, 0.022, "enemy_hp_pct")  # e.g. "100%"

    # ---------- 招式选择面板（右侧，共 4 个）----------
    MOVE_TIME    = Region(0.740, 0.354, 0.040, 0.024, "move_time")
    MOVE_1       = Region(0.601, 0.444, 0.390, 0.054, "move_1")
    MOVE_2       = Region(0.601, 0.505, 0.390, 0.054, "move_2")
    MOVE_3       = Region(0.601, 0.565, 0.390, 0.054, "move_3")
    MOVE_4       = Region(0.601, 0.625, 0.390, 0.054, "move_4")

    # 每个招式按钮内的名称子区域（相对于整体帧）
    MOVE_1_NAME  = Region(0.625, 0.450, 0.200, 0.040, "move_1_name")
    MOVE_2_NAME  = Region(0.625, 0.511, 0.200, 0.040, "move_2_name")
    MOVE_3_NAME  = Region(0.625, 0.571, 0.200, 0.040, "move_3_name")
    MOVE_4_NAME  = Region(0.625, 0.631, 0.200, 0.040, "move_4_name")

    # 招式PP（右侧数字）
    MOVE_1_PP    = Region(0.940, 0.450, 0.050, 0.040, "move_1_pp")
    MOVE_2_PP    = Region(0.940, 0.511, 0.050, 0.040, "move_2_pp")
    MOVE_3_PP    = Region(0.940, 0.571, 0.050, 0.040, "move_3_pp")
    MOVE_4_PP    = Region(0.940, 0.631, 0.050, 0.040, "move_4_pp")

    # ---------- 底部事件文字（特性发动、天气等）----------
    EVENT_TEXT   = Region(0.100, 0.870, 0.700, 0.055, "event_text")


# ---------------------------------------------------------------------------
# 双打 (Double Battle)
# ---------------------------------------------------------------------------

class DoubleRegions:
    # ---------- 我方宝可梦 1（左下，左边）----------
    MY1_NAME     = Region(0.008, 0.872, 0.090, 0.027, "my1_name")
    MY1_HP_BAR   = Region(0.008, 0.904, 0.093, 0.017, "my1_hp_bar")
    MY1_HP_TEXT  = Region(0.018, 0.926, 0.083, 0.022, "my1_hp_text")

    # ---------- 我方宝可梦 2（左下，右边）----------
    MY2_NAME     = Region(0.105, 0.872, 0.090, 0.027, "my2_name")
    MY2_HP_BAR   = Region(0.105, 0.904, 0.093, 0.017, "my2_hp_bar")
    MY2_HP_TEXT  = Region(0.115, 0.926, 0.083, 0.022, "my2_hp_text")

    # ---------- 对方宝可梦 1（上方，左边）----------
    ENEMY1_NAME  = Region(0.152, 0.020, 0.090, 0.026, "enemy1_name")
    ENEMY1_HP_BAR= Region(0.152, 0.047, 0.110, 0.015, "enemy1_hp_bar")
    ENEMY1_HP_PCT= Region(0.262, 0.044, 0.032, 0.022, "enemy1_hp_pct")

    # ---------- 对方宝可梦 2（上方，右边）----------
    ENEMY2_NAME  = Region(0.440, 0.020, 0.090, 0.026, "enemy2_name")
    ENEMY2_HP_BAR= Region(0.440, 0.047, 0.110, 0.015, "enemy2_hp_bar")
    ENEMY2_HP_PCT= Region(0.550, 0.044, 0.032, 0.022, "enemy2_hp_pct")

    # ---------- 招式面板（与单打位置相同）----------
    COMMAND_TIME = Region(0.740, 0.354, 0.040, 0.024, "command_time")
    MOVE_1       = Region(0.601, 0.444, 0.390, 0.054, "move_1")
    MOVE_2       = Region(0.601, 0.505, 0.390, 0.054, "move_2")
    MOVE_3       = Region(0.601, 0.565, 0.390, 0.054, "move_3")
    MOVE_4       = Region(0.601, 0.625, 0.390, 0.054, "move_4")

    MOVE_1_NAME  = Region(0.625, 0.450, 0.200, 0.040, "move_1_name")
    MOVE_2_NAME  = Region(0.625, 0.511, 0.200, 0.040, "move_2_name")
    MOVE_3_NAME  = Region(0.625, 0.571, 0.200, 0.040, "move_3_name")
    MOVE_4_NAME  = Region(0.625, 0.631, 0.200, 0.040, "move_4_name")


# ---------------------------------------------------------------------------
# 对战前选宝可梦界面
# ---------------------------------------------------------------------------

class TeamSelectRegions:
    # 我方 6 只宝可梦的名称行（左侧列表）
    MY_SLOT = [
        Region(0.042, 0.158, 0.170, 0.028, f"my_slot_{i+1}") for i in range(6)
    ]
    # 对方 6 只（右侧列表，部分遮挡，先只读名称）
    ENEMY_SLOT = [
        Region(0.760, 0.158, 0.170, 0.028, f"enemy_slot_{i+1}") for i in range(6)
    ]
