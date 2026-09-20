"""Render the article's typography cover. Optional: requires Pillow."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
FONT = Path('/System/Library/Fonts/Supplemental')
image = Image.new('RGB', (2000, 840), '#f6f7f4')
draw = ImageDraw.Draw(image)

def font(size, bold=False):
    return ImageFont.truetype(str(FONT / ('Arial Bold.ttf' if bold else 'Arial.ttf')), size)

def text(x, y, value, size, color='#172d34', bold=False):
    draw.text((x, y), value, font=font(size, bold), fill=color)

draw.rectangle((0, 0, 2000, 12), fill='#167a67')
text(100, 72, 'PYTHON  /  SEC FORM 4', 27, '#167a67', True)
text(100, 155, 'Build an insider-buying', 77, bold=True)
text(100, 244, 'screener', 77, bold=True)
text(103, 357, 'Purchase value is only the first column.', 36, '#506469')

# Every displayed number comes from the saved September 18 capture.
draw.rounded_rectangle((100, 451, 1900, 729), radius=22, fill='#ffffff', outline='#d7e0dc', width=2)
for x, label in [(142, 'TICKER'), (380, 'PURCHASE VALUE'), (880, 'HOLDING CHANGE'), (1450, 'OWNERSHIP')]:
    text(x, 480, label, 23, '#647672', True)
draw.line((140, 530, 1858, 530), fill='#dce6e0', width=2)
for y, ticker, value, pct, ownership in [(553, 'TENX', '$101,760', '+2330.7%', 'Direct'), (635, 'INBX', '$500,000', '+1.2%', 'Indirect')]:
    text(142, y, ticker, 39, bold=True)
    text(380, y, value, 39)
    text(880, y, pct, 39, '#167a67', True)
    text(1450, y, ownership, 35)
text(103, 770, 'Recorded September 18, 2026  ·  Code + saved API responses on GitHub', 24, '#647672')
text(1740, 769, 'AlphAI', 30, '#167a67', True)
image.save(OUT / 'cover.png', optimize=True)
