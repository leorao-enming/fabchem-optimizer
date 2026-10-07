"""Extract the published VLE tables of two C1 source papers into data/vle/*.csv.

Moioli 2021 is not extracted (its two-column layout did not parse reliably).

Needs poppler's `pdftotext` and the publisher PDFs (kept in the Vault's
07 Sources/Research/, not in this repo). Every table is checked after parsing:
expected row count, pure-component end points, monotonic liquid composition.

Usage: python scripts/c1_extract_vle_tables.py <barbieri2024.pdf> <marzal1996.pdf>

Composition columns are stored exactly as published: Barbieri gives the mole
fraction of 2-propanol (x_ipa, y_ipa); Marzal gives water (x_water, y_water).
"""

from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "vle"


def pdf_text(pdf: str) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", pdf, "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout


def write(name: str, header: list[str], rows: list[tuple]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / name, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    print(f"  {name}: {len(rows)} rows")


def barbieri(pdf: str) -> None:
    pat = re.compile(r"^\s*(60|80)\s+(\d{3}\.\d{2})\s+(\d\.\d{4})\s+(\d\.\d{4})", re.M)
    rows = [(int(p), float(t), float(x), float(y)) for p, t, x, y in pat.findall(pdf_text(pdf))]
    for p, n, tb in ((60, 20, (342.85, 359.01)), (80, 20, (349.57, 366.57))):
        sub = [r for r in rows if r[0] == p]
        assert len(sub) == n, (p, len(sub))
        assert sub[0][1:3] == (tb[0], 1.0) and sub[-1][1:3] == (tb[1], 0.0), (sub[0], sub[-1])
        write(f"barbieri2024_{p}kpa.csv", ["P_kPa", "T_K", "x_ipa", "y_ipa"], sub)


def marzal(pdf: str) -> None:
    pat = re.compile(r"(\d\.\d{3})\s+(\d\.\d{3})\s+(\d{3}\.\d{2})")
    left: list[tuple] = []
    right: list[tuple] = []
    for line in pdf_text(pdf).splitlines():
        for m in pat.finditer(line):
            (right if m.start() > 55 else left).append(tuple(map(float, m.groups())))

    def split(seq):
        out, cur = [], []
        for r in seq:
            if r[0] == 0.0 and cur and cur[-1][0] == 1.0:
                out.append(cur)
                cur = []
            cur.append(r)
        out.append(cur)
        return out

    tables = {30: split(left)[0], 60: split(left)[1], 100: split(right)[0]}
    expect = {30: (25, 327.85, 342.33), 60: (26, 342.73, 359.14), 100: (27, 354.85, 372.78)}
    for p, t in tables.items():
        n, t_ipa, t_water = expect[p]
        assert len(t) == n and t[0][2] == t_ipa and t[-1][2] == t_water, (p, len(t))
        assert all(a[0] < b[0] for a, b in zip(t, t[1:], strict=False))
        write(
            f"marzal1996_{p}kpa.csv",
            ["P_kPa", "T_K", "x_water", "y_water"],
            [(p, r[2], r[0], r[1]) for r in t],
        )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    barbieri(sys.argv[1])
    marzal(sys.argv[2])
