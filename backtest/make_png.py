#!/usr/bin/env python3
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import os

# Load data
baseline = pd.read_csv('backtest_results_fixed.csv')
ml_opt = pd.read_csv('backtest_results_ml_optimized_fixed.csv')

# Calculate metrics
baseline_pnl = baseline['pnl'].sum()
ml_pnl = ml_opt['pnl'].sum()
baseline_wr = (baseline['pnl'] > 0).sum() / len(baseline) * 100
ml_wr = (ml_opt['pnl'] > 0).sum() / len(ml_opt) * 100

# Create image (1200 x 800 pixels)
img = Image.new('RGB', (1200, 800), color='white')
draw = ImageDraw.Draw(img)

# Try to load a font, fall back to default
try:
    title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
    header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
except:
    title_font = ImageFont.load_default()
    header_font = ImageFont.load_default()
    text_font = ImageFont.load_default()

# Title
draw.text((600, 30), "Backtest Results: Baseline vs ML-Optimized", font=title_font, fill='black', anchor='mm')
draw.text((600, 70), "Corrected Position Sizing (10 Year Backtest)", font=text_font, fill='gray', anchor='mm')

# Left box - Baseline
left_x = 100
draw.rectangle([left_x, 120, left_x+500, 750], outline='steelblue', width=3)
draw.text((left_x+250, 150), "BASELINE (EMA 12/26)", font=header_font, fill='steelblue', anchor='mm')

baseline_text = f"""
SL: 2.0% | TP: 5.0%

Total Trades:      {len(baseline):,}
Total P&L:         ${baseline_pnl:,.0f}
Win Rate:          {baseline_wr:.1f}%
Winning Trades:    {(baseline['pnl'] > 0).sum()}
Losing Trades:     {(baseline['pnl'] < 0).sum()}

Avg Win:           ${baseline[baseline['pnl'] > 0]['pnl'].mean():.2f}
Avg Loss:          ${baseline[baseline['pnl'] < 0]['pnl'].mean():.2f}

Max Win:           ${baseline['pnl'].max():.0f}
Max Loss:          ${baseline['pnl'].min():.0f}

Avg Trade:         ${baseline['pnl'].mean():.2f}
"""

y_pos = 200
for line in baseline_text.strip().split('\n'):
    if line:
        draw.text((left_x+20, y_pos), line, font=text_font, fill='black')
        y_pos += 35

# Right box - ML-Optimized
right_x = 650
draw.rectangle([right_x, 120, right_x+500, 750], outline='darkgreen', width=3)
draw.text((right_x+250, 150), "ML-OPTIMIZED (EMA 8/20)", font=header_font, fill='darkgreen', anchor='mm')

ml_text = f"""
SL: 0.5% | TP: 3.52%

Total Trades:      {len(ml_opt):,}
Total P&L:         ${ml_pnl:,.0f}
Win Rate:          {ml_wr:.1f}%
Winning Trades:    {(ml_opt['pnl'] > 0).sum()}
Losing Trades:     {(ml_opt['pnl'] < 0).sum()}

Avg Win:           ${ml_opt[ml_opt['pnl'] > 0]['pnl'].mean():.2f}
Avg Loss:          ${ml_opt[ml_opt['pnl'] < 0]['pnl'].mean():.2f}

Max Win:           ${ml_opt['pnl'].max():.0f}
Max Loss:          ${ml_opt['pnl'].min():.0f}

Avg Trade:         ${ml_opt['pnl'].mean():.2f}
"""

y_pos = 200
for line in ml_text.strip().split('\n'):
    if line:
        draw.text((right_x+20, y_pos), line, font=text_font, fill='black')
        y_pos += 35

# Save
output = 'backtest_comparison.png'
img.save(output)
print(f"✓ File created: {output}")
print(f"✓ Size: {os.path.getsize(output):,} bytes")
print(f"✓ Location: /workspaces/EMA_Crossover_LongOnly/{output}")
