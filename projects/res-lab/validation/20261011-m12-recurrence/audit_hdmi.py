"""Read every captured HDMI frame and retain suspect transition samples.

The magenta score targets this scene's observed half-purple fault; it is not a
general proof of image validity. The contact sheet still needs visual review.
"""
import json
import pathlib
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).resolve().parent
dest = HERE / sys.argv[1]
report = dest / 'all-frame-transition-audit.json'
assert not report.exists()
raw = dest / 'hdmi.rgb'
frame_bytes = 576 * 1024 * 3
assert raw.stat().st_size % frame_bytes == 0
count = raw.stat().st_size // frame_bytes
assert count > 20
frames = np.memmap(raw, np.uint8, 'r', shape=(count, 576, 1024, 3))
baseline = frames[20, 45:520, 70:954].astype(np.int16)
scores = []
for index, frame in enumerate(frames):
    rgb = frame[45:520, 70:954].astype(np.int16)
    purple = (rgb[:, :, 0] > 1.7 * rgb[:, :, 1] + 15) & (rgb[:, :, 2] > 1.4 * rgb[:, :, 1] + 15)
    scores.append({'frame': index, 'magenta_fraction': float(purple.mean()),
                   'mean_abs_delta_from_standby20': float(np.abs(rgb - baseline).mean())})
top = sorted(scores, key=lambda score: score['magenta_fraction'], reverse=True)[:8]
contact = Image.new('RGB', (1024, 4 * 310))
draw = ImageDraw.Draw(contact)
for position, score in enumerate(top):
    index = score['frame']
    frame = Image.fromarray(np.asarray(frames[index]))
    path = dest / f'audit-frame-{index:03d}.png'
    assert not path.exists()
    frame.save(path)
    x, y = position % 2 * 512, position // 2 * 310
    contact.paste(frame.resize((512, 288)), (x, y))
    draw.text((x + 4, y + 290), f"Frame {index}: magenta={score['magenta_fraction']:.4f}", fill='white')
contact.save(dest / 'transition-audit-contact.png')
proof = {'frames': count, 'region': [45, 520, 70, 954], 'baseline_frame': 20,
         'limitation': 'Scene-specific half-purple detector; visual review required. No sustained RAW or media-throughput claim.',
         'above_point2': [score['frame'] for score in scores if score['magenta_fraction'] > .2],
         'top': top, 'scores': scores}
report.write_text(json.dumps(proof, indent=2) + '\n')
print(json.dumps({key: proof[key] for key in ('frames', 'above_point2', 'top')}, indent=2))
