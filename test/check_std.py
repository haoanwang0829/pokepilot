import cv2
import numpy as np
from pathlib import Path

d = Path(r'F:\pokepilot-main\debug_output\my_team\pokemon')

print('=== All type icons std ===')
print('threshold: min_std=30.0')
print()

for slot in range(6):
    for t in ['type1', 'type2']:
        path = d / f'slot_{slot}_{t}.png'
        if path.exists():
            img = cv2.imread(str(path))
            if img is not None:
                avg_std = float(np.mean(img.std(axis=(0,1))))
                status = "OK" if avg_std >= 30.0 else "FAIL"
                print(f'slot_{slot}_{t}: std={avg_std:.1f}  [{status}]')

print()
print('=== type2 sorted by std ===')
type2_list = []
for slot in range(6):
    path = d / f'slot_{slot}_type2.png'
    if path.exists():
        img = cv2.imread(str(path))
        if img is not None:
            avg_std = float(np.mean(img.std(axis=(0,1))))
            type2_list.append((slot, avg_std))

type2_list.sort(key=lambda x: x[1], reverse=True)
for slot, std in type2_list:
    print(f'  slot_{slot}_type2: std={std:.2f}')