"""JDim reader transcribed from Solid Edge 2026 Annot.DEX (DIMPERST.CPP).

Every read below mirrors one archive read in JDim::Convert -> persist_serializeN.
Offsets in comments (+0x..) are the in-memory member offsets the reads fill;
they are the keys used to map fields to meaning via the getters.
"""
import struct


class Short(Exception):
    pass


class R:
    def __init__(self, b, pos=0):
        self.b, self.p = b, pos

    def take(self, n):
        if self.p + n > len(self.b):
            raise Short(f"need {n} at {self.p:#x}, have {len(self.b) - self.p}")
        v = self.b[self.p : self.p + n]
        self.p += n
        return v

    def u8(self): return self.take(1)[0]
    def u16(self): return struct.unpack("<H", self.take(2))[0]
    def u32(self): return struct.unpack("<I", self.take(4))[0]
    def i32(self): return struct.unpack("<i", self.take(4))[0]
    def f32(self): return struct.unpack("<f", self.take(4))[0]
    def f64(self): return struct.unpack("<d", self.take(8))[0]

    def wstr(self):
        n = self.u32()
        if n == 0:
            return ""
        return self.take(2 * n).decode("utf-16le").rstrip("\0")


# ---------------------------------------------------------------- pieces
def attribute_bundle(r, v):
    a = {}
    a["type"] = r.u8()          # +0  DimTypeConstants
    a["disp"] = r.u8()          # +1  DimDispTypeConstants
    a["b2"] = r.u8()            # +2
    a["w4"] = r.u16()           # +4  flags
    a["w6"] = r.u16()           # +6  flags
    a["flags8"] = r.u32()       # +8
    for o in (0x14, 0x18, 0x1C, 0x20, 0x24, 0x28, 0x2C):
        a[f"f{o:02x}"] = r.f32()
    a["d30"] = r.f64()
    a["d58"] = r.f64()
    if v > 4:
        a["d60"] = r.f64()
    a["d68"] = r.f64()
    if v > 2:
        if v > 7:
            a["f_extra"] = r.f32()
        if v >= 9:
            a["u70"] = r.u32()
        if v > 3:
            a["b74"] = r.u8()
        if v > 10:
            a["flagsC"] = r.u32()
    t = a["type"]
    if t in (8, 0xB):
        if v > 0xD:
            n = r.u16()
            a["arr76"] = [(r.u32(), r.u32(), r.u32()) for _ in range(n)]
        if v > 0x11:
            a["d90"] = r.f64()
    elif t in (1, 3, 5, 6, 7, 9) and v > 0x1D:
        n = r.u16()
        if n:
            a["u38"], a["u3c"], a["d40"] = r.u32(), r.u32(), r.f64()
            a["jog76"] = [(r.u32(), r.u32(), r.u32()) for _ in range(n)]
        n = r.u16()
        if n:
            a["u48"], a["u4c"], a["d50"] = r.u32(), r.u32(), r.f64()
            a["jog78"] = [(r.u32(), r.u32(), r.u32()) for _ in range(n)]
        a["d90"] = r.f64()
    elif v > 0x11:
        a["d90"] = r.f64()
    if v > 0x12:
        a["u10"] = r.u32()
    if v >= 0x15:
        a["d98"] = r.f64()
    if v >= 0x21:
        a["da0"] = r.f64()
    if v >= 0x22:
        a["da8"] = r.f64()
    if v >= 0x23:
        a["ub0"] = r.u32()
    if v >= 0x25:
        a["db8"] = r.f64()
    return a


def parents(r, v=39):
    """Geometry parents. Per-parent layout by JDim version: v>=17 FUN_180235220 (38 B),
    v15-16 FUN_180234ee0 (30 B, no trailing f64), v<15 FUN_180234c50 (22 B)."""
    n = r.u32()
    if n > 4:
        raise ValueError(f"too many geometry parents {n}")
    out = []
    for _ in range(n):
        p = {}
        p["ref"] = r.u32()
        p["guid_idx"] = r.u16()
        p["flags"] = r.u32()
        p["d78"] = r.f64()
        p["u68"] = r.u32()
        if v >= 15:
            p["u6c"], p["u70"] = r.u32(), r.u32()
        else:
            p["u6c"], p["u70"] = 0, 0
        if v >= 17:
            p["d80"] = r.f64()
        out.append(p)
    return out


def bspline(r):
    s = {"b38": r.u8(), "np": r.u32(), "rat": r.u32()}
    s["b39"], s["b3a"] = r.u8(), r.u8()
    s["nk"] = r.u32()
    s["d18"] = r.f64()
    s["b3b"] = r.u8()
    s["poles"] = [(r.f64(), r.f64()) for _ in range(s["np"])]
    if s["rat"]:
        s["weights"] = [r.f64() for _ in range(s["np"])]
    s["knots"] = [r.f64() for _ in range(s["nk"])]
    return s


def geomtag(r):
    tag = r.u8()
    c = chr(tag) if 32 <= tag < 127 else tag
    if c == "g":
        return ("g", [r.f64() for _ in range(6)])
    if c == "s":
        return ("s", [r.f64() for _ in range(5)] + [r.u8()])
    if c == "t":
        return ("t", [r.f64() for _ in range(5)] + [r.u8()] + [r.f64(), r.f64()])
    if tag == 0x8C:
        return ("pt", [r.f64(), r.f64()])
    if tag == 0x7F:
        return ("bsp", bspline(r))
    if c == "x":
        s = bspline(r)
        s["extra"] = [r.f64() for _ in range(7)]
        return ("xbsp", s)
    return (c, None)


def geometry(r, v, flagsC):
    n = r.u32()
    pts = []
    for _ in range(n):
        p = {"kind": r.u32(), "d": [r.f64() for _ in range(4)]}
        if v > 0xF and flagsC & 0x20000004:
            p["e"] = [r.f64(), r.f64()]
        if v > 0x15 and flagsC & 0x8000000:
            p["c"] = [r.f64() for _ in range(6)]
        p["geom"] = geomtag(r)
        pts.append(p)
    return pts


def range_limits(r, v):
    if v < 4:
        return None
    f = r.u8() if v < 0x24 else r.u32()
    out = {"flags": f}
    if f & 3:
        out["low"] = r.f64()
    if f & 0xC:
        out["high"] = r.f64()
    return out


def guser_text(r):
    """GUserText::Serialize (JUTIL2.dll): u32 nchars (no NUL), nchars UTF-16 units."""
    n = r.u32()
    return r.take(2 * n).decode("utf-16le") if n else ""


def double_value(r, dvv, nested_len=8):
    """JDoubleValue (EXPRDEX.DLL JDBLVAL.CPP) aggregated into JDim from JDim v24.

    dvv = JDoubleValue's own version (DRAFT.VER): v1 base, v2/v3 append limit
    extras, v4 appends a nested IJPersist object. The value object of the
    dimension's variable: value, range limits, discrete values, formula text.
    """
    dv = {"value": r.f64(), "w38": r.u16(), "flags": r.u16()}
    f = dv["flags"]
    lim = None
    if f & 0x10:                                   # limits block
        lf = r.u8() if dvv < 3 else r.u32()
        lim = {"flags": lf}
        if lf & 3:
            lim["low"] = r.f64()
        if lf & 0xC:
            lim["high"] = r.f64()
        if lf & 0x10:                              # discrete values
            n = r.u32()
            lim["discrete"] = [r.f64() for _ in range(n)]
        if f & 0x20:
            lim["d18"] = r.f64()
        dv["limits"] = lim
    if f & 0x1000:
        dv["formula"] = guser_text(r)
    if f & 0x2000:
        dv["text98"] = guser_text(r)
    if f & 0x4000:
        dv["texta0"] = guser_text(r)
    if f & 0x400:
        dv["text60"] = guser_text(r)
    if dvv >= 2 and lim is not None:
        if lim["flags"] & 0x20:
            lim["u20"] = r.u32()
        if lim["flags"] & 0x40:
            lim["u24"] = r.u32()
    if dvv >= 3 and lim is not None and lim["flags"] & 0x100:
        n = r.u32()
        lim["list30"] = [r.f64() for _ in range(n)]
    if dvv >= 4:
        # v4 nested IJPersist object (object +0xe0, wired at runtime, class not identified).
        # 8 bytes (02 00 00 00 00 00 00 00) in every file seen; read_jdim verifies the size
        # against the record end and retries other sizes if needed.
        dv["nested"] = r.take(nested_len)
    return dv


# ---------------------------------------------------------------- JDim
def read_jdim(body, v, dvv=4):
    """body = object payload after the 8-byte QQ header."""
    r = R(body)
    d = {"v": v}
    d["attr"] = a = attribute_bundle(r, v)
    flagsC = a.get("flagsC", 0)
    if v < 3:
        raise NotImplementedError("JDim v1/v2 (pre-V5 files)")
    d["parents"] = parents(r, v)
    if v >= 5:
        d["d18e8"] = r.f64()
    d["u100"] = r.u32()
    d["u108"] = r.u32()
    d["d18f8"] = r.f64()
    d["geom"] = geometry(r, v, flagsC)
    d["slots"] = {k: r.wstr() for k in range(1, 8)}
    d["str4"] = [r.wstr() for _ in range(4)]
    if v < 0x18:
        d["range"] = range_limits(r, v)
    if v >= 6 and a["type"] < 12 and (0xB02 >> a["type"]) & 1:
        d["d1928"], d["d1930"] = r.f64(), r.f64()
    if v >= 7:
        d["u18e0"] = r.u32()
    if v >= 9:
        d["slots"][0xC] = r.wstr()
    if v >= 10:
        d["d1a90"], d["u1910"] = r.f64(), r.u32()
    if v >= 12:
        d["d1900"] = r.f64()
    if v >= 13:
        d["slots"][0xD] = r.wstr()
    if v >= 17 and v < 0x18 and flagsC & 0x80000:
        d["usertext17"] = guser_text(r)
    if v >= 19:
        d["bc8"], d["bc9"] = r.u8(), r.u8()
    if v >= 20:
        d["s1a68"] = r.wstr()
    if v >= 22:
        m = r.u8()
        if m & 1:
            d["d1ae0"] = r.f64()
    if v >= 23:
        n = r.u32()
        d["l1ae8"] = [r.u32() for _ in range(n)]
    d["_pos_v24"] = r.p

    def tail(rr, out):
        if v >= 25 and flagsC & 0x20000000:
            out["u1b04"] = rr.u32()
        if v >= 26:
            out["u104"] = rr.u32()
        if v >= 27:
            out["d18f0"] = rr.f64()
        if v >= 28:
            out["slots"][0x12], out["slots"][0x13] = rr.wstr(), rr.wstr()
        if v >= 29 and a["flags8"] & 0x200:
            out["u1b08"] = rr.u32()
        if v >= 31:
            out["slots"][0x14] = rr.wstr()
        if v >= 32:
            out["d1b18"], out["d1b20"] = rr.f64(), rr.f64()
        if v >= 34:
            out["slots"][0x4A] = rr.wstr()
        for k in (38, 39):
            if v >= k and flagsC & 0x8000000:
                n = rr.u32()
                out[f"l{k}"] = [rr.u32() for _ in range(n)]

        return rr.p

    if v < 24:
        r.p = tail(r, d)
        d["_end"], d["_len"] = r.p, len(body)
        return d
    start = r.p
    sizes = [8] + [k for k in range(0, min(len(body) - start, 4096) + 1, 4) if k != 8]
    for n in (sizes if dvv >= 4 else [0]):
        rr = R(body, start)
        trial = {"slots": d["slots"]}
        try:
            trial["value"] = double_value(rr, dvv, n)
            end = tail(rr, trial)
        except (Short, UnicodeDecodeError):
            continue
        if end == len(body):
            if n != 8 and dvv >= 4:
                trial["value"]["nestedNonStandard"] = True
            d.update(trial)
            d["_end"], d["_len"] = end, len(body)
            return d
    # no consistent layout: keep the default reading and report the mismatch
    rr = R(body, start)
    d["value"] = double_value(rr, dvv)
    try:
        tail(rr, d)
    except Short:
        pass
    d["_end"], d["_len"] = rr.p, len(body)
    return d
