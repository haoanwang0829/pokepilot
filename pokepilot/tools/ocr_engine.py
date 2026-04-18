"""
OCR 引擎封装 —— 基于 EasyOCR，支持整图和裁切区域识别
"""
import cv2
import numpy as np
import easyocr

_reader_cache: dict[str, easyocr.Reader] = {}


def get_reader(langs: list[str] | None = None) -> easyocr.Reader:
    if langs is None:
        langs = ["ch_sim", "en"]
    key = ",".join(langs)
    if key not in _reader_cache:
        print(f"加载 OCR 模型 {langs}...")
        _reader_cache[key] = easyocr.Reader(langs, gpu=False)
    return _reader_cache[key]


def read_region(img: np.ndarray, min_conf: float = 0.25) -> list[tuple[list, str, float]]:
    """
    对 numpy 图像跑 OCR，返回 [(box, text, conf), ...]
    box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    """
    reader = get_reader()
    if img is None or img.size == 0:
        return []
    results = reader.readtext(img)
    return [(box, text, conf) for box, text, conf in results if conf >= min_conf]


def crop(img: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
    """安全裁切，超出边界自动 clamp"""
    H, W = img.shape[:2]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    return img[y0:y1, x0:x1]


def read_crop_text(img: np.ndarray, x0: int, y0: int, x1: int, y1: int,
                   min_conf: float = 0.25, pad: int = 8) -> str:
    """
    裁切指定区域并 OCR，把区域内所有文字按 x 顺序拼成一个字符串返回。
    pad: 四周额外留白像素，给 EasyOCR 更多上下文（中文尤其需要）
    """
    H, W = img.shape[:2]
    patch = crop(img, max(0, x0 - pad), max(0, y0 - pad),
                      min(W, x1 + pad), min(H, y1 + pad))
    results = read_region(patch, min_conf)
    if not results:
        return ""
    # 按文字框左上角 x 排序，左到右拼接
    results_sorted = sorted(results, key=lambda r: r[0][0][0])
    return " ".join(text for _, text, _ in results_sorted).strip()
