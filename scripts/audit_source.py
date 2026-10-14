#!/usr/bin/env python3
"""Thin workflow entry point; implementation lives in src/pypsa_col."""

import sys
from pypsa_col.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["audit-source", *sys.argv[1:]]))
