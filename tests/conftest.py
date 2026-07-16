"""Put src/ on the import path so tests import the same way the Jetson does.

The edge code runs as `python3 -m edge.mode3_posture` from src/, so `edge` and
`common` are top-level packages. Tests live outside src/, so without this they
would import nothing.
"""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
