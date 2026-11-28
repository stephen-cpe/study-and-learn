"""48 px playback strip: every hello frame as the browser's 48 px view shows it
(nearest-neighbour halving, light and dark stages) to judge hand followability."""
from PIL import Image
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(os.path.dirname(HERE), 'frames', 'hello')

names = sorted(os.listdir(FR))
tiles = []
for n in names:
    im = Image.open(os.path.join(FR, n)).convert('RGBA')
    tiles.append(im.resize((48, 48), Image.NEAREST))

for bgc, tag in (((240, 240, 242), 'light'), ((24, 26, 34), 'dark')):
    sheet = Image.new('RGB', (len(tiles) * 54 + 6, 66), bgc)
    for i, t in enumerate(tiles):
        cell = Image.new('RGBA', (48, 48), bgc + (255,))
        cell.alpha_composite(t)
        sheet.paste(cell.convert('RGB'), (6 + i * 54, 12))
    sheet = sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST)
    out = os.path.join(HERE, '_hello_48_%s.png' % tag)
    sheet.save(out)
    print('saved', out, sheet.size)
