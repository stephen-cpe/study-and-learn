"""Validate preview.html: inlined animation data matches manifest.json, and every
referenced asset path exists. (Run from anywhere.)"""
import json
import re
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)

html = open(os.path.join(OUT, 'preview.html'), encoding='utf-8').read()
m = re.search(r'const ANIMATIONS\s*=\s*(\[.*?\n\]);', html, re.S)
blob = m.group(1)
blob = re.sub(r'([{,]\s*)([A-Za-z_]+):', r'\1"\2":', blob)     # quote JS keys
blob = blob.replace("'", '"')
data = json.loads(blob)

man = json.load(open(os.path.join(OUT, 'manifest.json')))
print('entries: html %d  manifest %d' % (len(data), len(man['animations'])))
by = {e['name']: e for e in data}
bad = 0
for e in man['animations']:
    h = by.get(e['name'])
    if h is None:
        print('MISSING', e['name'])
        bad += 1
        continue
    for k in ('filename', 'mode', 'frames', 'durations_ms', 'total_ms',
              'frame_count', 'start_pose', 'end_pose'):
        if h.get(k) != e[k]:
            print('MISMATCH', e['name'], k, '\n  html:', h.get(k), '\n  man :', e[k])
            bad += 1
print('field mismatches:', bad)

# referenced paths
paths = set(re.findall(r'(?:\.\./)?(?:gifs|frames|source|references)/[A-Za-z0-9_./-]+', html))
missing = []
for p in paths:
    q = os.path.normpath(os.path.join(OUT, p.replace('/', os.sep)))
    if not os.path.exists(q):
        missing.append(p)
print('referenced paths: %d, missing: %d' % (len(paths), len(missing)))
for p in missing:
    print('  MISSING PATH', p)
print('OK' if bad == 0 and not missing else 'NEEDS FIXES')
