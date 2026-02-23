#!/usr/bin/env python3
from PIL import Image, ImageDraw
import os

# Create a white image
width, height = 900, 700
img = Image.new('RGB', (width, height), color='white')
draw = ImageDraw.Draw(img)

# Define colors
dark_blue = (25, 118, 210)
green = (56, 142, 60)
gray = (100, 100, 100)
light_gray = (240, 240, 240)

# Draw header
draw.rectangle([(0, 0), (width, 80)], fill=dark_blue)
draw.text((30, 20), 'BACKTEST RESULTS COMPARISON - 10 Year Gold (XAUUSD)', fill='white')

# Y position tracker
y_pos = 120

# Baseline section
draw.rectangle([(20, y_pos), (450, y_pos + 180)], fill=light_gray, outline=dark_blue, width=2)
draw.text((35, y_pos + 10), 'BASELINE STRATEGY (EMA 12/26)', fill=dark_blue)
y_pos += 35

baseline_data = [
    'Total Trades: 1,557',
    'Total P&L: $38,176',
    'Win Rate: 33.0%',
    'Average Trade: $24.52',
    'Largest Win: $828.46',
    'Largest Loss: -$200.00'
]

for line in baseline_data:
    draw.text((45, y_pos), line, fill='black')
    y_pos += 25

# ML-Optimized section (reset y_pos)
y_pos = 120
draw.rectangle([(470, y_pos), (880, y_pos + 180)], fill=light_gray, outline=green, width=2)
draw.text((485, y_pos + 10), 'ML-OPTIMIZED (EMA 8/20)', fill=green)
y_pos += 35

optimized_data = [
    'Total Trades: 2,171',
    'Total P&L: $275,147',
    'Win Rate: 26.4%',
    'Average Trade: $126.74',
    'Largest Win: $1,050.00',
    'Largest Loss: -$200.00'
]

for line in optimized_data:
    draw.text((485, y_pos), line, fill='black')
    y_pos += 25

# Improvement section
y_pos = 330
draw.rectangle([(20, y_pos), (880, y_pos + 120)], fill=(76, 175, 80), outline=green, width=3)
draw.text((30, y_pos + 15), 'KEY FINDING', fill='white')
draw.text((30, y_pos + 45), 'ML-Optimized Strategy: +621% Better Performance', fill='white')
draw.text((30, y_pos + 70), 'Additional Profit: $236,971 | Extra Trades: +614 (+39.4%)', fill='white')

# Parameters section
y_pos = 480
draw.text((30, y_pos), 'OPTIMIZED PARAMETERS:', fill=dark_blue)
y_pos += 30

params = [
    'Fast EMA: 8  (vs baseline 12)',
    'Slow EMA: 20  (vs baseline 26)',
    'Stop Loss: 0.5%  (vs baseline 2.0%)',
    'Take Profit: 3.52%  (vs baseline 5.0%)'
]

for param in params:
    draw.text((45, y_pos), param, fill='black')
    y_pos += 25

# Save the image
img.save('/workspaces/EMA_Crossover_LongOnly/results.png', 'PNG')
print('✓ PNG file created successfully: results.png')
print('  Location: /workspaces/EMA_Crossover_LongOnly/results.png')

# Verify file
import os
if os.path.exists('/workspaces/EMA_Crossover_LongOnly/results.png'):
    size = os.path.getsize('/workspaces/EMA_Crossover_LongOnly/results.png')
    print(f'  File size: {size} bytes')
    print('✓ File verified - ready to open!')
