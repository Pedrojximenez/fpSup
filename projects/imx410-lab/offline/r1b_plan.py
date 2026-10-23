#!/usr/bin/env python3
"""From an eval.txt, list the weak candidates (<= 2 effect points per register, or flags only TRANSIENT/DCLP-ONLY)
and write the retest jobs: each (reg, base, value) re-shot in 3 fresh boots.   r1b_plan.py EVAL OUTJSON"""
import json, re, sys, collections
L = open(sys.argv[1]).read().splitlines()
pts = collections.defaultdict(list); seen = collections.defaultdict(set)
for l in L:
    m = re.match(r'(V\d) ([0-9A-F]{4})=(\S+)\s+(.*)', l)
    if not m:
        continue
    b, r, v, rest = m.groups(); seen[r].add(b)
    if 'NO FRAME' in rest:
        continue
    if not re.fullmatch(r'p\[\.\]\s+f10\[\.\]\s+d\[\.\]\s*', rest):
        pts[r].append((b, v, rest))
jobs = []
for r, p in pts.items():
    if len(p) <= 2:
        for b, v, _ in p:
            jobs.append(dict(reg=r, base=b, value=v))
json.dump(jobs, open(sys.argv[2], 'w'), indent=0)
print(len(jobs), 'jobs from', len({j['reg'] for j in jobs}), 'registers')
