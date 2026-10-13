# solid-edge-dft

A reader for Solid Edge draft files (.dft) that gets dimensions out of the file's object
store instead of scraping the preview picture. Each dimension comes back with its type,
value, the exact text Solid Edge draws for it, tolerances, fit classes, prefix and suffix
text, style, sheet and layer.

The format isn't documented anywhere, so the record layouts were transcribed from the
Solid Edge 2026 binaries (Annot.DEX, dimsrvcs.dll, EXPRDEX.DLL, STYLMGR.DEX, lyrmgr.dex
and a few others) with Ghidra. The spec is in [docs/FORMAT.md](docs/FORMAT.md) and the
working notes are in [docs/RESEARCH-LOG.md](docs/RESEARCH-LOG.md).

Tested on 41 drawings saved by releases from v15 (2003) to 2026, plus the 90 drafts that
ship with Solid Edge 2026:

- all 732 dimension records and 626 style records parse to the exact end of the record
- the computed text matches what's on the sheet for every dimension that could be checked
  against the sheet picture (716 of them)
- DMS angles, fractions, feet-inches, zero suppression, limits, fits, alpha tolerances and
  a 45° chamfer were checked by editing a test sheet in Solid Edge and comparing with what
  it drew

None of those drawings are in this repo.

## Use

Python 3.9+ and `olefile`.

```
pip install olefile
python -m sedft drawing.dft           # JSON: dimensions, sheets, styles, metadata
python -m sedft --check *.dft         # parse every record, report any that don't end cleanly
```

```python
import sedft
for d in sedft.extract("drawing.dft")["dimensions"]:
    print(d["sheet"], d["type"], d.get("displayText") or d["text"])
```

## What's not done

- JDim versions 1 and 2 (files from before Solid Edge V5).
- Chamfers that aren't 45°: the angle comes from the two parent lines, but which of the two
  complementary angles Solid Edge shows hasn't been checked, and neither has the style's
  "use 45° character" option. Such dimensions carry a `chamferAngleComplementUnverified` note.
- The JDoubleValue v4 nested object is 8 constant bytes in every file seen. The reader checks
  the size against the record end and tries other sizes if needed.
- Geometry other than what dimensions reference (lines, arcs, views) isn't decoded beyond
  what's needed here.

## tools/ghidra

The scripts used for the binary work. `run.sh` does a headless Ghidra import and dumps every
decompiled function of a DLL into one text file (on Windows, point it at
`analyzeHeadless.bat` with `ANALYZE=`). `fn.py` pulls one function out of that dump, `reads.py` reduces a
serializer to its sequence of reads, and `vtables.py` lists a class's vtables from MSVC RTTI.
You need your own Solid Edge install to run them; no Solid Edge binaries or decompiled
output are included.

Solid Edge is a trademark of Siemens. This project isn't affiliated with or endorsed by
Siemens.
