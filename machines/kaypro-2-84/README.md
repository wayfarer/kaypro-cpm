# Kaypro 2 (1984)

Z80, 64K, CP/M 2.2, two floppy drives — carrying Microsoft BASIC-80 v5, Microsoft FORTRAN-80 v3.44, and Digital Research CBASIC 2 (v2.07). It's modelled after a real machine owned by a mathematics professor.

## A note on the model number

It's a Kaypro **2**, not a Kaypro **II**, and the difference is real rather than a typo:

| | |
|---|---|
| **Kaypro II** (1982) | The original. Shipped S-BASIC and the Perfect Software suite — Perfect Writer, Speller, Filer, Calc. |
| **Kaypro 2** (1984) | Shipped WordStar 3.3 with MailMerge, and Microsoft BASIC. |

Kaypro changed the bundle in 1984, and the Roman-vs-Arabic numeral is how the two machines are told apart (the same split distinguishes the Kaypro IV '83 from the Kaypro 4 '84). This machine has MBASIC, so it's the 1984 one — hence `machines/kaypro-2-84/`. Please don't "correct" it to `kaypro-ii`.

FORTRAN-80 and CBASIC were never part of any Kaypro bundle. They're here because the professor's real machine had them, not because the model shipped with them.

## Drives

| Drive | Backing | Role |
|---|---|---|
| A: | `A/` | System floppy — the software bundle lives on `A/0` |
| B: | `B/` | Work floppy — scripted sessions write here |

## Setup

Fetch MBASIC, FORTRAN-80 and CBASIC onto the A: drive (once):

```bash
bash machines/kaypro-2-84/download_software.sh
```

## Wanted

**WordStar 3.3** — genuinely part of the Kaypro 2/84 bundle, alongside MailMerge. It belongs in `machines/kaypro-2-84/A/0/` as `WS.COM`, but it's harder to source than the Microsoft tools.
