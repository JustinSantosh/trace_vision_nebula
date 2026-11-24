#!/usr/bin/env python
"""Rebuild the SYNTHETIC demo registry layer for the stored clips (DECISIONS M21).

All the logic lives in tracevision/demo_registry.py (the app also calls it after every upload). This rebuilds
registry/synthetic_demo_registry.csv, the owner records / e-challans for it, re-ranks every runs/clip*/ result and
rebuilds the reports. The evaluation never uses this layer.

Usage  python TRACEVISION_DATA/scripts/generate_demo_registry.py
"""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
runpy.run_module("tracevision.demo_registry", run_name="__main__")
