from PIL import Image, ImageDraw, ImageFont

W, H = 760, 460
img = Image.new('RGB', (W, H), '#f4f5f7')
d = ImageDraw.Draw(img)

try:
    title = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 36)
    label = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 28)
    small = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 20)
except Exception:
    title = label = small = ImageFont.load_default()

# Header
header_h = 88
d.rectangle([(0, 0), (W, header_h)], fill='#ffffff')
d.line([(0, header_h), (W, header_h)], fill='#d4d8de', width=2)
d.text((32, 26), 'PS2 Toolkit', fill='#2f343d', font=title)

# Instruction
d.text((210, 126), 'Drag PS2 Toolkit to Applications', fill='#4c5563', font=label)

# Arrow
d.line([(350, 255), (430, 255)], fill='#5f6df5', width=10)
d.polygon([(430, 255), (405, 235), (405, 275)], fill='#5f6df5')

# Bottom hint
d.text((230, 400), 'Install by dragging the app icon to Applications', fill='#7a8392', font=small)

img.save('packaging/dmg/background.png')
print('saved packaging/dmg/background.png')
