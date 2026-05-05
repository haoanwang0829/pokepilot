import cv2
import numpy as np
from pathlib import Path

type_names = {1:'normal',2:'fighting',3:'flying',4:'poison',5:'ground',6:'rock',7:'bug',8:'ghost',9:'steel',10:'fire',11:'water',12:'grass',13:'electric',14:'psychic',15:'ice',16:'dragon',17:'dark',18:'fairy'}

d = Path(r'F:\pokepilot-main\sprites\sprites\types\generation-ix\scarlet-violet\small')

type2 = cv2.imread(r'F:\pokepilot-main\debug_output\my_team\pokemon\slot_0_type2.png')
type2_r = cv2.resize(type2, (32, 32))

print('slot_0_type2 与各属性图标的相似度（diff越小越相似）')
print('='*50)

results = []
for tid in range(1, 19):
    ref_path = d / f'{tid}.png'
    if ref_path.exists():
        ref = cv2.imread(str(ref_path))
        ref = cv2.resize(ref, (32, 32))
        diff = float(cv2.absdiff(type2_r, ref).mean())
        results.append((diff, tid, type_names[tid]))

results.sort(key=lambda x: x[0])

for i, (diff, tid, name) in enumerate(results):
    marker = ' <-- BEST' if i == 0 else ''
    print(f'{name:10s} ({tid:2d}): diff={diff:.2f}{marker}')