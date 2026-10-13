"""JDimParameters (dimension style) reader driven by dimparams_table.TABLE."""
from . import jdim
from .dimparams_table import TABLE


# persist_serializeN calls this earlier version first (vtable slot); all others call N-1.
CALLS = {8: 6, 5: 4}


def chain(v):
    out = []
    while v >= 4:
        out.append(v)
        v = CALLS.get(v, v - 1)
    return set(out)


def read_params(body, v, positions=None):
    r = jdim.R(body)
    f = {}
    active = chain(v)
    for ver, kind, off, size in TABLE:
        if ver not in active:
            continue
        key = off if off is not None else f"{kind}@{r.p:#x}"
        if positions is not None:
            positions[key] = r.p
        if kind == "R":
            f[key] = r.take(size)
        elif kind == "WS":
            n = r.u32()
            if n > max(size, 1):
                raise ValueError(f"string len {n} > {size} at v{ver} off {off}")
            f[key] = r.take(2 * n).decode("utf-16le").rstrip("\0")
        elif kind == "GT":
            f[key] = jdim.guser_text(r)
        elif kind == "HOLE":
            present = r.u8()
            f[key] = [jdim.guser_text(r) for _ in range(6)] if present else None
        elif kind == "OVR":
            nbits, nbytes = r.u32(), r.u32()
            f["ovr"] = (nbits, r.take(nbytes))
    return f, r.p
