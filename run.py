#!/usr/bin/env python3
"""inventory-watch entry point.

Usage:
  python run.py --inspect   Print the live CSV's headers (schema setup aid).
  python run.py --run       Fetch, archive, diff, and write the changelog.
"""
import sys
sys.path.insert(0, "src")
from watch import inspect, run_live  # noqa: E402

if __name__ == "__main__":
    if "--inspect" in sys.argv:
        inspect()
    elif "--run" in sys.argv:
        run_live()
    else:
        print(__doc__)
