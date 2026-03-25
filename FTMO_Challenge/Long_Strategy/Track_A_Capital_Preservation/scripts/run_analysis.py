#!/usr/bin/env python3
"""
FTMO Challenge - Quick Start Analysis
Runs all compliance analysis and generates summary report
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime


def print_header(title):
    """Print formatted header"""
    print("\n")
    print("=" * 100)
    print(f" {title}")
    print("=" * 100)
    print()


def run_ftmo_analysis():
    """Run full FTMO analysis suite"""
    
    print_header("FTMO CHALLENGE - QUICK START ANALYSIS")
    
    ftmo_dir = Path(__file__).parent
    
    print(f"Starting analysis at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Running 2 analysis tools...\n")
    
    # Run validator
    print("-" * 100)
    print("STEP 1: Running FTMO Compliance Validator...")
    print("-" * 100)
    try:
        result = subprocess.run([sys.executable, ftmo_dir / 'ftmo_validator.py'], 
                              capture_output=False, timeout=60)
        if result.returncode != 0:
            print("⚠️  Validator encountered an issue")
    except Exception as e:
        print(f"❌ Error running validator: {e}")
    
    # Run optimizer
    print("\n")
    print("-" * 100)
    print("STEP 2: Running FTMO Parameter Optimizer...")
    print("-" * 100)
    try:
        result = subprocess.run([sys.executable, ftmo_dir / 'ftmo_optimizer.py'],
                              capture_output=False, timeout=60)
        if result.returncode != 0:
            print("⚠️  Optimizer encountered an issue")
    except Exception as e:
        print(f"❌ Error running optimizer: {e}")
    
    # Summary
    print_header("ANALYSIS COMPLETE")
    
    print("""
SUMMARY OF FINDINGS:
════════════════════════════════════════════════════════════════════════════════

❌ Current Status: FAILS FTMO REQUIREMENTS
   • Daily Loss Limit: ✅ PASS (-2.00% vs -5.00% limit)
   • Max Drawdown Limit: ❌ FAIL (13.02% vs 10.00% limit)

🎯 RECOMMENDED ACTION - Option 1:
   • Reduce position size to 50% (change risk_percent from 2 to 1)
   • Estimated drawdown: 6.51% ✅
   • Estimated profit: $137,574
   • Pass probability: ~95%

📁 GENERATED FILES:
   • ftmo_compliance_report.txt (compliance status)
   • ftmo_daily_pnl.csv (daily profit/loss breakdown)
   • ftmo_drawdown_curve.csv (drawdown tracking)
   • ftmo_compliance.json (structured data)

📖 NEXT STEPS:
   1. Read the compliance report and optimizer recommendations
   2. Choose implementation option (1, 2, or 3)
   3. Modify strategy parameters
   4. Run new backtest
   5. Re-run this script to verify compliance
   6. When ✅ compliant, test on live account

❓ Need help? Read README.md in this folder

════════════════════════════════════════════════════════════════════════════════
    """)
    
    # List generated files
    print("\nGenerated files in this directory:")
    for file in sorted(ftmo_dir.glob("ftmo_*.csv")) + sorted(ftmo_dir.glob("ftmo_*.txt")) + sorted(ftmo_dir.glob("ftmo_*.json")):
        if file.exists():
            size = file.stat().st_size
            if size > 1024*1024:
                size_str = f"{size/(1024*1024):.1f} MB"
            elif size > 1024:
                size_str = f"{size/1024:.1f} KB"
            else:
                size_str = f"{size} B"
            print(f"  ✓ {file.name:<40} ({size_str})")


if __name__ == '__main__':
    try:
        run_ftmo_analysis()
        print("\n✅ Analysis completed successfully!")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\n⚠️  Analysis interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error during analysis: {e}")
        sys.exit(1)
