#!/usr/bin/env python3
"""inventory-watch entry point: --inspect prints headers, --run diffs the inventory, --pages watches agency pages."""
import sys
sys.path.insert(0, "src")

if __name__ == "__main__":
    if "--inspect" in sys.argv:
        from watch import inspect
        inspect()
    elif "--run" in sys.argv:
        from watch import run_live
        run_live()
    elif "--pages" in sys.argv:
        from pages import run_live
        run_live()
    else:
        print(__doc__)
