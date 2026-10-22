#!/usr/bin/env python3
"""把 E→F 實測到的矩陣套在代表性色塊上,說明「整幀平均差很小」不等於「看不出來」。

矩陣取自 user_project 那一組的最小平方擬合(results.json)。
色塊是人為挑的顯示域數值,不是量測到的實拍色。
"""
import json, os
import numpy as np
from analyze import lab

here = os.path.dirname(os.path.abspath(__file__))
M = np.array(json.load(open(os.path.join(here, 'results.json')))
             ['user_project']['pairs']['E_offOriginal->F_offNormalMatrix']['best_fit_3x3'])

SWATCHES = {
    '中性灰':   [.50, .50, .50],
    '膚色':     [.62, .46, .39],
    '淡藍天':   [.45, .58, .78],
    '青':       [.15, .62, .66],
    '橙':       [.85, .45, .12],
    '淡綠葉':   [.28, .48, .22],
    '紅衣':     [.72, .18, .16],
    '洋紅':     [.70, .20, .55],
    '飽和綠':   [.20, .65, .22],
    '飽和藍':   [.16, .24, .72],
}

if __name__ == '__main__':
    out = {}
    print('%-8s %-20s %-20s %s' % ('', 'OFF(原樣)', '換 normal 矩陣', 'ΔE76'))
    for n, v in SWATCHES.items():
        a = np.array(v)
        b = np.clip(M @ a, 0, 1)
        d = float(np.linalg.norm(lab(b) - lab(a)))
        out[n] = {'off': [round(x, 3) for x in a], 'normal': [round(float(x), 3) for x in b],
                  'dE76': round(d, 1)}
        print('%-8s %-20s %-20s %5.1f' % (n, ' '.join('%.3f' % x for x in a),
                                          ' '.join('%.3f' % x for x in b), d))
    json.dump(out, open(os.path.join(here, 'swatch_demo.json'), 'w'), indent=1, ensure_ascii=False)
