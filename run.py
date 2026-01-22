#!/usr/bin/env python3
"""Entry point for running AviaTrade from the project root."""

import sys
from pathlib import Path

# Add src directory to Python path for development
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from src.aviatrade.cli.main import main

if __name__ == "__main__":
    main()
