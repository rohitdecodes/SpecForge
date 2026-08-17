from src.extraction.rules import extract_all
import json

cases = [
    r'49-94-0013 Milw 5"x.045"x7/8" Metal Cut Off Disc',
    r'49-94-0029 Milw 6-1/2"x1/8"x5/8" DKO Metal Cut Off Disc',
    r'49-94-0058 Milw 12"x1/8"x20mm Metal Cut Off Disc',
    'KDFM404KPS Dishwasher SS',
    'PDSH4816AF Dishwasher SS - Display Only',
    r'801274 10w LED 6" Retro 50k',
    r'1x6-16\' Coastline Sq Edge - Vintage Azek PVC Decking',
    'DCB518ASTS06G Diablo 1/2"x18" - Sanding Belt 6pc',
]

for c in cases:
    print('===', c)
    r = extract_all(c)
    for k, v in r.items():
        if v['value'] is not None:
            print(f'  {k:18s} = {v["value"]!r:20s} conf={v["confidence"]} span={v["span"]}')
    print()
