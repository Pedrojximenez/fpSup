"""Offline white-ink gaps for the inspected stock, earlier and latest photos."""
from pathlib import Path
import json
from PIL import Image

HERE = Path(__file__).resolve().parent
R4 = HERE.parent / 'run4'
ROOT = HERE.parents[5]


def measure(path):
    im = Image.open(path).convert('RGB')
    assert im.size == (1024, 682)
    columns = {}
    for x in range(190):
        ys = [y for y in range(630, 682) if min(im.getpixel((x, y))) > 200]
        if ys:
            columns[x] = ys
    runs = []
    for x, ys in columns.items():
        if not runs or x != runs[-1][2]:
            runs.append([x, min(ys), x + 1, max(ys) + 1])
        else:
            runs[-1][1] = min(runs[-1][1], min(ys))
            runs[-1][2] = x + 1
            runs[-1][3] = max(runs[-1][3], max(ys) + 1)
    integer = [r for r in runs if r[3] - r[1] >= 23]
    assert len(integer) == 2, ('expected two large digits', path, runs)
    end = integer[-1][2]
    dots = [r for r in runs if r[0] >= end and r[2] - r[0] <= 3 and r[3] - r[1] <= 4]
    assert dots, ('decimal point not visible', path, runs)
    dot = dots[0]
    return dict(image=str(path), integer=integer, decimal_point=dot,
                blank_columns=dot[0] - end, all_white_runs=runs)


if __name__ == '__main__':
    report = HERE / 'spacing-comparison.json'
    assert not report.exists()
    paths = {
        'stock_5994': ROOT / 'projects/res-lab/validation/20261009-oncamera/screenshots/1904-20261015-combined-before-fix.jpg',
        'stock_2997': R4 / 'stock-footer-first-QS/1935-20261015-stock-footer-QS-first-B.jpg',
        'earlier_2997': R4 / 'fix9-final-black-edge/1931-20261015-fps-final-latin-black-edge-B.jpg',
    }
    captures = json.loads((HERE / 'post-refresh/result.json').read_text())
    assert captures['final_screen'] == 'LV_CINE_MEDIUM'
    # Latest rate checked visually in the actual photo, rather than inferred
    # from the previous turn's 29.97 setting. No rate setter is issued here.
    paths['after_5994'] = Path(captures['screenshots'][-1])
    result = {name: measure(path) for name, path in paths.items()}
    assert result['after_5994']['blank_columns'] < result['earlier_2997']['blank_columns']
    assert abs(result['after_5994']['blank_columns'] - result['stock_5994']['blank_columns']) <= 1
    out = dict(latest_displayed_rate='59.94', layout='medium CINE LV',
               method='min RGB > 200, half-open white-ink bounding boxes in original JPEG; blank columns between integer ink and decimal point',
               caveat='Earlier custom picture is 29.97; latest custom and original stock 59.94 are the same-rate gap comparison. Full font/style equality is not implied.',
               stock_style_equality_claimed=False, measurements=result)
    report.write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps({k: v['blank_columns'] for k, v in result.items()}))
