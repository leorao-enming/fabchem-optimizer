# Published IPA/water VLE tables

Parsed from the publishers' PDFs by `scripts/c1_extract_vle_tables.py` (row counts and pure
end points checked). The PDFs are copyrighted and live in the author's Obsidian Vault, not in
this repo. Compositions are stored as published.

| file | source | pressure | composition columns |
|---|---|---|---|
| `barbieri2024_{60,80}kpa.csv` | Barbieri, De Guido, Moioli, *J. Chem. Thermodyn.* 198 (2024) 107342, Tables 4-5 | 60, 80 kPa | `x_ipa`, `y_ipa` |
| `marzal1996_{30,60,100}kpa.csv` | Marzal, Monton, Rodrigo, *J. Chem. Eng. Data* 41 (1996) 608, Tables 3-5 (DOI 10.1021/je9503113) | 30, 60, 100 kPa | `x_water`, `y_water` |

Stated uncertainties: Barbieri U(x_ipa) 0.0215 (60 kPa) / 0.0300 (80 kPa), U(T) 0.073 / 0.036 K;
Marzal composition accuracy +-0.001, T +-0.01 K. Moioli 2021 (103.5-300 kPa) is not included.
