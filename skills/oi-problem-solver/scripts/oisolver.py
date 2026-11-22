#!/usr/bin/env python3
"""Thin launcher for the optional OISolver package tooling.

The Skill protocols remain usable without the package.  This launcher never
copies helper implementations into the Skill directory, keeping one source of
truth for deterministic tooling.
"""
import sys

try:
    from oisolver.cli import main
except ImportError:
    print("OISolver package is not installed; install the repository or run with PYTHONPATH=src. Protocol-only use remains available.", file=sys.stderr)
    raise SystemExit(2)

raise SystemExit(main())
