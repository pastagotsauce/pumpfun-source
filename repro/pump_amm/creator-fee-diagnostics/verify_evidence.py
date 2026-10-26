#!/usr/bin/env python3
"""Check immutable saved receipts and the original migration error block."""
import json
from verify_creator import verify_saved, verify_original

if __name__ == "__main__":
    print(json.dumps({**verify_saved(), **verify_original()}, indent=2))
