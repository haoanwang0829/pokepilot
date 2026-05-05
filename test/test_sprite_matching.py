"""
精灵图识别测试脚本

遍历 debug_output/my_team/pokemon 中的 slot_N_sprite_clean.png 文件，
使用 PokemonDetector 进行识别，将结果保存到 test/ 目录。

用法：python test_sprite_matching.py
"""

import cv2
import os
from pathlib import Path

from pokepilot.common.pokemon_detect import PokemonDetector

INPUT_DIR = Path(r"F:\pokepilot-main\debug_output\my_team\pokemon")
OUTPUT_DIR = Path(r"F:\pokepilot-main\test")
CHAMPIONS_DIR = Path(r"F:\pokepilot-main\sprites\champions")
CHAMPIONS_SHINY_DIR = Path(r"F:\pokepilot-main\sprites\champions_shiny")

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    detector = PokemonDetector()
    
    sprite_files = sorted(INPUT_DIR.glob("slot_*_sprite_clean.png"))
    
    if not sprite_files:
        print(f"未找到任何 slot_*_sprite_clean.png 文件")
        print(f"搜索目录: {INPUT_DIR}")
        return
    
    print(f"找到 {len(sprite_files)} 个精灵图文件")
    print("=" * 60)
    
    for idx, sprite_path in enumerate(sprite_files, start=1):
        parts = sprite_path.stem.split("_")
        slot_num = int(parts[1])
        
        type1_path = INPUT_DIR / f"slot_{slot_num}_type1.png"
        type2_path = INPUT_DIR / f"slot_{slot_num}_type2.png"
        
        sprite_img = cv2.imread(str(sprite_path))
        type1_img = cv2.imread(str(type1_path)) if type1_path.exists() else None
        type2_img = cv2.imread(str(type2_path)) if type2_path.exists() else None
        
        if sprite_img is None:
            print(f"[{idx}] 无法读取: {sprite_path}")
            continue
        
        print(f"    type1图片存在: {type1_path.exists() if type1_path else False}")
        print(f"    type2图片存在: {type2_path.exists() if type2_path else False}")
        
        result = detector.detect(
            sprite=sprite_img,
            type1_img=type1_img,
            type2_img=type2_img,
            bg_removal="multi",
            bg_colors=[
                [221, 237, 245],
                [200, 95, 115]
            ]
        )
        
        tid1 = detector._match_type(type1_img) if type1_img is not None else None
        tid2 = detector._match_type(type2_img) if type2_img is not None else None
        type_names = {1:"normal",2:"fighting",3:"flying",4:"poison",5:"ground",6:"rock",7:"bug",8:"ghost",9:"steel",10:"fire",11:"water",12:"grass",13:"electric",14:"psychic",15:"ice",16:"dragon",17:"dark",18:"fairy"}
        print(f"    type1识别: {tid1} -> {type_names.get(tid1, 'None')}")
        print(f"    type2识别: {tid2} -> {type_names.get(tid2, 'None')}")
        
        print(f"[{idx:02d}] slot_{slot_num}")
        print(f"    识别结果: {result['name']} (slug: {result['slug']})")
        print(f"    属性: {result['types']}")
        print(f"    匹配分数: {result['score']:.4f}")
        print(f"    候选数: {result['candidates_searched']}")
        
        in_filename = f"in_{idx:03d}.png"
        cv2.imwrite(str(OUTPUT_DIR / in_filename), sprite_img)
        
        if result['sprite_key']:
            sprite_rel_path = result['sprite_key']
            if sprite_rel_path.startswith("sprites/champions/"):
                ref_path = Path(r"F:\pokepilot-main") / sprite_rel_path
            elif sprite_rel_path.startswith("sprites/champions_shiny/"):
                ref_path = Path(r"F:\pokepilot-main") / sprite_rel_path
            else:
                ref_path = CHAMPIONS_DIR / sprite_rel_path
            
            if ref_path.exists():
                matched_img = cv2.imread(str(ref_path))
                out_filename = f"out_{idx:03d}.png"
                cv2.imwrite(str(OUTPUT_DIR / out_filename), matched_img)
                print(f"    匹配图片: {ref_path.name}")
            else:
                print(f"    警告: 找不到匹配图片 {ref_path}")
        
        print("-" * 60)
    
    print(f"\n完成！结果保存在: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()