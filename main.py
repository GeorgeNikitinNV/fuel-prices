#!/usr/bin/env python3

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from fuel_prices.cli import app


if __name__ == "__main__":
    app()
