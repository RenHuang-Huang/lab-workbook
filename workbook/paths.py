"""Writable application directory for source and portable Windows builds."""
import sys
from pathlib import Path

ROOT=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
