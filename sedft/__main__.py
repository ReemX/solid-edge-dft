"""python -m sedft FILE.dft ...          dimensions as JSON
   python -m sedft --check FILE.dft ...  parse every JDim / JDimParameters record and
                                         report how many end exactly at the record end"""
import json
import sys

from . import dimparams, jdim, versions
from .psm import Store
from .semantic import extract


def check(path):
    s = Store(path)
    av = versions.app_version(s.ole)
    vj = versions.obj_version(versions.JDIM_GUID, av)
    vdv = versions.obj_version(versions.JDOUBLEVALUE_GUID, av)
    vp = versions.obj_version(versions.JDIMPARAMS_GUID, av)
    bad = []
    counts = {}
    for label, objs, read in (
        ("JDim", s.of_class("CLSID_JDim") + s.of_class("JDim Object"),
         lambda b: jdim.read_jdim(b, vj, vdv)["_end"]),
        ("JDimParameters", s.of_class("JDimParameters Object"),
         lambda b: dimparams.read_params(b, vp)[1]),
    ):
        ok = 0
        for p, oid in objs:
            body = s.body(p)
            try:
                end = read(body)
            except Exception as e:  # report and keep going
                bad.append(f"  {label} {oid}: {type(e).__name__}: {e}")
                continue
            if end == len(body):
                ok += 1
            else:
                bad.append(f"  {label} {oid}: ends at {end}, record is {len(body)} bytes")
        counts[label] = f"{ok}/{len(objs)}"
    print(f"{path}: app {av:.2f}, JDim v{vj}, JDimParameters v{vp}, JDoubleValue v{vdv}: "
          + ", ".join(f"{k} {v}" for k, v in counts.items()))
    for line in bad:
        print(line)
    return not bad


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--check":
        return 0 if all([check(f) for f in argv[1:]]) else 1
    for f in argv:
        print(json.dumps(extract(f), indent=1, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
