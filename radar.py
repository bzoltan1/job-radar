#!/usr/bin/env python3
"""Job Radar: Modular Systems & Linux Platform Career Engine."""

import os
import sys

# Ensure radar package is importable from script directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from radar.cli import main

if __name__ == "__main__":
    main()
