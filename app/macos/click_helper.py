import sys
import time
import os
import importlib

# Importing CoreGraphics via ctypes may segfault on some systems.
# Running in a separate process isolates crashes from the main GUI.
try:
    # Ensure the macos module dir is importable when executed as a script
    here = os.path.dirname(__file__)
    if here not in sys.path:
        sys.path.insert(0, here)
    ic = importlib.import_module('input_control')
except Exception as e:
    print(f"ERR: import input_control failed: {e}", file=sys.stderr)
    sys.exit(2)


def main():
    if len(sys.argv) != 3:
        print("usage: click_helper.py <x> <y>", file=sys.stderr)
        return 2
    try:
        x = float(sys.argv[1])
        y = float(sys.argv[2])
    except Exception as e:
        print(f"ERR: invalid coords: {e}", file=sys.stderr)
        return 2
    try:
        ic.move_mouse(x, y)
        time.sleep(0.03)
        ic.click_mouse(x, y)
        time.sleep(0.03)
        return 0
    except Exception as e:
        print(f"ERR: click failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
