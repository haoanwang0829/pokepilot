"""
OCR 效果测试 —— 在截图上跑 EasyOCR，可视化识别结果

用法:
    python -m pokepilot.tools.test_ocr --image screenshots/team/frame_20260410_220344.png
    python -m pokepilot.tools.test_ocr --image screenshots/team/frame_20260410_220347.png
"""

import argparse
import cv2
import numpy as np
from pathlib import Path
import easyocr


_reader_cache: dict[str, easyocr.Reader] = {}

def get_reader(lang: str) -> easyocr.Reader:
    if lang not in _reader_cache:
        langs = ["ch_sim", "en"] if lang == "ch" else ["en"]
        print(f"加载 EasyOCR 模型（{langs}）...")
        _reader_cache[lang] = easyocr.Reader(langs, gpu=False)
    return _reader_cache[lang]


def run(image_path: str, lang: str = "en") -> None:
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(image_path)

    reader  = get_reader(lang)
    results = reader.readtext(image_path)
    # results: list of (box, text, conf)
    # box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]

    print(f"\n图片: {image_path}  ({img.shape[1]}x{img.shape[0]})")
    print(f"识别到 {len(results)} 个文字区域\n")

    # 按 y 坐标排序
    items = sorted(results, key=lambda r: r[0][0][1])

    for box, text, conf in items:
        x = int(box[0][0])
        y = int(box[0][1])
        print(f"  ({x:4d},{y:4d})  {conf:.2f}  {text}")

    # 可视化
    vis = img.copy()
    for box, text, conf in items:
        pts = np.array(box, dtype=np.int32)
        cv2.polylines(vis, [pts], True, (0, 255, 0), 2)
        label = f"{text[:18]}({conf:.2f})"
        cv2.putText(vis, label, (int(box[0][0]), int(box[0][1]) - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

    out_dir = Path("debug_output")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / (Path(image_path).stem + f"_ocr_{lang}.jpg")
    cv2.imwrite(str(out_path), vis)
    print(f"\n可视化已保存: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--lang",  default="en", choices=["en", "ch"],
                        help="en=纯英文  ch=中英混合")
    args = parser.parse_args()
    run(args.image, args.lang)
