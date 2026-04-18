"""
宝可梦识别引擎 - 统一接口

输入: 三个矩形图片（sprite、type1、type2）和背景去除参数
输出: 识别的宝可梦信息
"""

from dataclasses import dataclass
import json
from pathlib import Path

import cv2
import numpy as np

# ── 路径 ──────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent.parent
_ROSTER_PATH = _ROOT / "data" / "champions_roster.json"
_CHAMPIONS_DIR = _ROOT / "sprites" / "champions"
_CHAMPIONS_SHINY = _ROOT / "sprites" / "champions_shiny"
_TYPES_DIR = _ROOT / "sprites" / "sprites" / "types" / "generation-ix" / "scarlet-violet" / "small"

# 属性 ID → 名称
_TYPE_NAMES = {
    1: "normal", 2: "fighting", 3: "flying", 4: "poison",
    5: "ground", 6: "rock", 7: "bug", 8: "ghost",
    9: "steel", 10: "fire", 11: "water", 12: "grass",
    13: "electric", 14: "psychic", 15: "ice", 16: "dragon",
    17: "dark", 18: "fairy",
}


@dataclass
class PokemonVariant:
    """单个宝可梦变体"""
    slug: str                           # primary key，如 "pikachu-alola"
    id: int
    name: str
    types: list[str]
    sprite_filename: str | None = None  # sprite 文件名，如 "Menu CP 0025.png"
    sprite_shiny_filename: str | None = None  # shiny sprite 文件名
    sprite: np.ndarray | None = None    # 加载后的 normal sprite 图片
    sprite_shiny: np.ndarray | None = None  # 加载后的 shiny sprite 图片


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _alpha_to_white(img: np.ndarray) -> np.ndarray:
    """将 RGBA 图合成到白色背景，返回 BGR。"""
    if img.ndim == 3 and img.shape[2] == 4:
        alpha = img[:, :, 3:] / 255.0
        bgr = img[:, :, :3].astype(float)
        white = np.ones_like(bgr) * 255
        return (bgr * alpha + white * (1 - alpha)).astype(np.uint8)
    return img


def _has_icon(img: np.ndarray, min_std: float = 60.0) -> bool:
    """颜色标准差低 → 纯色背景（无图标）。std >= min_std 才认为有图标"""
    return float(img.std()) >= min_std


def _remove_bg(img: np.ndarray, bg_color=None, tolerance: int = 30) -> np.ndarray:
    """
    去除单色背景（对手队伍用）。
    bg_color: None 时自动检测四角颜色；指定时使用该颜色
    """
    if bg_color is None:
        # 自动检测四角颜色
        corners = [
            img[:5, :5],
            img[:5, -5:],
            img[-5:, :5],
            img[-5:, -5:],
        ]
        bg_color = np.median(np.concatenate([c.reshape(-1, 3) for c in corners], axis=0), axis=0)

    bg_color = np.array(bg_color, dtype=np.uint8)
    lo = np.clip(bg_color.astype(int) - tolerance, 0, 255).astype(np.uint8)
    hi = np.clip(bg_color.astype(int) + tolerance, 0, 255).astype(np.uint8)
    mask_bg = cv2.inRange(img, lo, hi)
    mask_fg = cv2.bitwise_not(mask_bg)

    # 形态学清理
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask_fg = cv2.morphologyEx(mask_fg, cv2.MORPH_OPEN, kernel)

    result = np.full_like(img, 255)
    result[mask_fg > 0] = img[mask_fg > 0]
    return result


def _remove_bg_multi(img: np.ndarray, bg_colors: list, tolerance: int = 60) -> np.ndarray:
    """
    去除多色背景（我方队伍用）。
    bg_colors: [(B,G,R), ...] 背景颜色列表
    """
    mask_bg_total = np.zeros(img.shape[:2], dtype=np.uint8)
    for bg_color in bg_colors:
        bg_color = np.array(bg_color, dtype=np.uint8)
        lo = np.clip(bg_color.astype(int) - tolerance, 0, 255).astype(np.uint8)
        hi = np.clip(bg_color.astype(int) + tolerance, 0, 255).astype(np.uint8)
        mask_bg = cv2.inRange(img, lo, hi)
        mask_bg_total = cv2.bitwise_or(mask_bg_total, mask_bg)

    # 取反得到前景掩码
    mask_fg = cv2.bitwise_not(mask_bg_total)

    # 形态学清理
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask_fg = cv2.morphologyEx(mask_fg, cv2.MORPH_OPEN, kernel)

    result = np.full_like(img, 255)
    result[mask_fg > 0] = img[mask_fg > 0]
    return result


# ── 宝可梦检测器 ────────────────────────────────────────────────────────────────

class PokemonDetector:
    """宝可梦识别引擎"""

    def __init__(self):
        """初始化，加载库和参考数据"""
        # 加载属性图标
        self.type_refs = self._load_type_refs()

        # 加载精灵图
        self.sprite_refs = self._load_sprite_refs()

        # 从 roster 构建 PokemonVariant 字典
        roster = json.loads(_ROSTER_PATH.read_text(encoding="utf-8"))["pokemon"]
        self.variants: dict[str, PokemonVariant] = {}

        for pokemon_data in roster:
            slug = pokemon_data["slug"]
            variant = PokemonVariant(
                slug=slug,
                id=pokemon_data["id"],
                name=pokemon_data["name"],
                types=pokemon_data.get("types", []),
                sprite_filename=pokemon_data.get("sprite"),
                sprite_shiny_filename=pokemon_data.get("sprite_shiny"),
                sprite=None,
                sprite_shiny=None,
            )
            self.variants[slug] = variant

        # 加载 sprite 图片到对应的 variant
        self._load_sprites_into_variants()

        print(f"[PokemonDetector] 加载: {len(self.sprite_refs)} 精灵图, {len(self.type_refs)} 属性图标, {len(self.variants)} 宝可梦变体")

    def _load_type_refs(self, size: int = 32) -> dict[int, np.ndarray]:
        """加载 18 张属性图标"""
        refs = {}
        for tid, name in _TYPE_NAMES.items():
            p = _TYPES_DIR / f"{tid}.png"
            if not p.exists():
                continue
            img = cv2.imread(str(p), cv2.IMREAD_COLOR)
            if img is not None:
                refs[tid] = cv2.resize(img, (size, size))
        return refs

    def _load_sprite_refs(self) -> dict[str, np.ndarray]:
        """加载精灵图"""
        refs = {}
        for directory in (_CHAMPIONS_DIR, _CHAMPIONS_SHINY):
            if not directory.exists():
                continue
            for path in directory.glob("*.png"):
                img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
                if img is None:
                    continue
                refs[path.stem] = _alpha_to_white(img)
        return refs

    def _load_sprites_into_variants(self):
        """从 sprite_refs 加载图片到对应的 variant（根据 sprite_filename）"""
        for variant in self.variants.values():
            # 加载普通版 sprite（去掉扩展名来匹配 sprite_refs key）
            if variant.sprite_filename:
                key = variant.sprite_filename.replace(".png", "")
                if key in self.sprite_refs:
                    variant.sprite = self.sprite_refs[key]

            # 加载闪光版 sprite
            if variant.sprite_shiny_filename:
                key = variant.sprite_shiny_filename.replace(".png", "")
                if key in self.sprite_refs:
                    variant.sprite_shiny = self.sprite_refs[key]

    def _match_type(self, icon: np.ndarray, size: int = 32, threshold: float = 60.0, min_std: float = 60.0) -> int | None:
        """识别属性图标，返回 type_id 或 None"""
        if icon is None or icon.size == 0:
            return None

        if not _has_icon(icon, min_std=min_std):
            return None

        icon_r = cv2.resize(icon, (size, size))
        best_id, best_score = None, float("inf")
        for tid, ref in self.type_refs.items():
            diff = cv2.absdiff(icon_r, ref).mean()
            if diff < best_score:
                best_score, best_id = diff, tid

        return best_id if best_score < threshold else None

    def _match_sprite(self, sprite: np.ndarray, candidates: list[PokemonVariant] | None = None, target_size: int = 96) -> tuple[PokemonVariant | None, float]:
        """识别精灵，返回 (variant, score)。也比较闪光版本"""
        sprite_r = cv2.resize(sprite, (target_size, target_size))

        search = candidates if candidates else list(self.variants.values())
        best_variant, best_score, is_shiny = None, float("inf"), False

        for variant in search:
            # 比较普通版
            if variant.sprite is not None:
                ref_r = cv2.resize(variant.sprite, (target_size, target_size))
                score = cv2.absdiff(sprite_r, ref_r).mean()
                if score < best_score:
                    best_score, best_variant = score, variant

            # 也比较闪光版
            if variant.sprite_shiny is not None:
                ref_r = cv2.resize(variant.sprite_shiny, (target_size, target_size))
                score = cv2.absdiff(sprite_r, ref_r).mean()
                if score < best_score:
                    best_score, best_variant = score, variant
                    is_shiny = True

        return best_variant, best_score, is_shiny

    def detect(
        self,
        sprite: np.ndarray,
        type1_img: np.ndarray,
        type2_img: np.ndarray,
        bg_removal: str = "none",
        bg_colors: list = None,
    ) -> dict:
        """
        识别宝可梦。

        Args:
            sprite: sprite 图片矩形
            type1_img: type1 图片矩形
            type2_img: type2 图片矩形
            bg_removal: 背景去除方式
                - "none": 不去除背景
                - "auto": 自动检测单色背景（对手队伍）
                - "multi": 多色背景（我方队伍，需要指定 bg_colors）
            bg_colors: 多色背景的颜色列表 [(B,G,R), ...]

        Returns:
            {
                "id": 25,
                "name": "pikachu",
                "slug": "pikachu-alola",
                "types": ["electric", "fairy"],
                "score": 1.23,
                "candidates_searched": 100,
            }
        """
        # 处理背景
        if bg_removal == "auto":
            sprite_clean = _remove_bg(sprite)
        elif bg_removal == "multi" and bg_colors:
            sprite_clean = _remove_bg_multi(sprite, bg_colors, tolerance=40)
        else:
            sprite_clean = sprite

        # 识别属性
        tid1 = self._match_type(type1_img)
        tid2 = self._match_type(type2_img)
        types_found = [_TYPE_NAMES[t] for t in [tid1, tid2] if t]

        # 按属性过滤候选
        candidates = None
        if types_found:
            candidates = [
                v for v in self.variants.values()
                if all(t in v.types for t in types_found) and "Mega" not in v.slug
            ]

        # 如果候选为空，再尝试不排除 Mega
        if not candidates:
            if types_found:
                candidates = [
                    v for v in self.variants.values()
                    if all(t in v.types for t in types_found)
                ]
            else:
                candidates = None

        # 识别精灵
        variant, score, is_shiny = self._match_sprite(sprite_clean, candidates)

        n_searched = len(candidates) if candidates else len(self.variants)

        if variant:
            # 构建相对于项目根目录的完整精灵图路径
            if is_shiny and variant.sprite_shiny_filename:
                sprite_key = f"sprites/champions_shiny/{variant.sprite_shiny_filename}"
            elif variant.sprite_filename:
                sprite_key = f"sprites/champions/{variant.sprite_filename}"
            else:
                sprite_key = None
            return {
                "id": variant.id,
                "name": variant.name,
                "slug": variant.slug,
                "sprite_key": sprite_key,
                "types": variant.types,
                "score": round(score, 2),
                "candidates_searched": n_searched,
            }
        else:
            return {
                "id": None,
                "name": "unknown",
                "slug": "unknown",
                "sprite_key": None,
                "types": [],
                "score": round(score, 2),
                "candidates_searched": n_searched,
            }
