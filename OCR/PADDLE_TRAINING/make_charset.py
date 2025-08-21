#!/usr/bin/env python3
import sys, os, json, re
from pathlib import Path

base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/dev/shm/data")
out  = base / "charset.txt"

chars = set()
for lf in [base/"train.txt", base/"val.txt"]:
    if not lf.exists(): continue
    with open(lf, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            # format: "<path>\t<label>"
            parts = line.split("\t", 1)
            if len(parts) != 2: continue
            label = parts[1]
            for ch in label:
                chars.add(ch)

# Option: ordonner par fréquence simple / Unicode
charset = sorted(chars)
out.write_text("\n".join(charset), encoding="utf-8")
print(f"[OK] charset({len(charset)}) → {out}")
