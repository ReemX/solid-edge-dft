"""Reader for the Solid Edge PSM object store inside a .dft (or .par/.asm).

Streams used:
  PSMtypetable     b"ePyT" blocks. Block 0 lists classes (GUID, index, count,
                   name, DLL). Block 1 maps a second set of local indices to
                   block-0 indices (0xFFFF / 0xFFFE = no mapping).
  PSMspacemap/*    b"sseg", u16 n, u16 m, an optional prefix, then records:
                   u16 len, u32 cluster offset, u32 object id, u32 B, flags.
                   Flag bit 0x2000 (u16 at record+14+2) set: the object header
                   class is a block-0 index. Clear: it is a block-1 local index.
  PSMsegmenttable  one flag byte per 0x2000-id segment. Used only as a fallback
                   for objects no spacemap lists.
  PSMcluster0      objects: b"QQ", u16 class, u32 id, payload.
"""
import bisect
import re
import struct

import olefile


def type_blocks(t):
    starts = [m.start() for m in re.finditer(rb"ePyT", t)]
    classes = {}
    b0 = t[starts[0] : starts[1] if len(starts) > 1 else len(t)]
    for m in re.finditer(rb"\x01\x00\xff\xff", b0):
        s = m.start()
        q = s + 8
        if q + 2 > len(b0):
            continue
        idx, = struct.unpack_from("<H", b0, s - 4)
        nl, = struct.unpack_from("<H", b0, q)
        name = b0[q + 2 : q + 2 + nl]
        if not (2 < nl < 160 and name.endswith(b"\0")):
            continue
        q += 2 + nl
        dl, = struct.unpack_from("<H", b0, q)
        classes[idx] = (
            name[:-1].decode("latin1"),
            b0[q + 2 : q + 2 + dl].rstrip(b"\0").decode("latin1"),
            struct.unpack_from("<I", b0, s + 4)[0],
        )
    remap = {}
    if len(starts) > 1:
        s = starts[1]
        n, = struct.unpack_from("<H", t, s + 10)
        for k in range(n):
            p = s + 20 + 26 * k
            if p + 26 > len(t):
                break
            local, gidx = struct.unpack_from("<HH", t, p + 16)
            if gidx < 0xFFFE:
                remap[local] = gidx
    return classes, remap


def _chain(d, p):
    out = []
    while p + 2 <= len(d):
        ln, = struct.unpack_from("<H", d, p)
        if ln < 12 or p + 2 + ln > len(d):
            return out, p
        off, oid, b = struct.unpack_from("<III", d, p + 2)
        out.append((off, oid, b, d[p + 14 : p + 2 + ln]))
        p += 2 + ln
    return out, p


def spacemap_records(d, cluster):
    """Return records of one spacemap stream, validated against the cluster."""
    best = []
    for start in range(8, min(len(d), 8192)):
        out, end = _chain(d, start)
        if not out or end != len(d):
            continue
        good = [r for r in out if r[0] + 8 <= len(cluster)
                and cluster[r[0]:r[0] + 2] == b"QQ"
                and struct.unpack_from("<I", cluster, r[0] + 4)[0] == r[1]]
        if len(good) == len(out):
            return out
        if len(good) > len(best):
            best = good
    return best


class Store:
    def __init__(self, path):
        self.ole = olefile.OleFileIO(path)
        self.cluster = self.ole.openstream("PSMcluster0").read()
        self.classes, self.remap = type_blocks(self.ole.openstream("PSMtypetable").read())
        seg = self.ole.openstream("PSMsegmenttable").read()
        n, = struct.unpack_from("<I", seg, 4)
        self.seg_flags = list(seg[8 : 8 + n])
        self.objs = self._load()

    def _resolve(self, local, direct):
        if direct:
            return local
        return self.remap.get(local, local)

    def _load(self):
        c = self.cluster
        objs = {}
        for e in self.ole.listdir():
            if e[0] != "PSMspacemap":
                continue
            for off, oid, _, rest in spacemap_records(self.ole.openstream(e).read(), c):
                local, = struct.unpack_from("<H", c, off + 2)
                direct = len(rest) > 3 and bool(rest[3] & 0x20)
                objs[oid] = (off, oid, self._resolve(local, direct))
        # Fallback for objects no spacemap lists: header scan, keeping the
        # longest run of increasing ids so stray b"QQ" pairs drop out.
        cand = []
        for m in re.finditer(rb"QQ", c):
            p = m.start()
            if p + 8 > len(c):
                break
            local, oid = struct.unpack_from("<HI", c, p + 2)
            if 0 < oid < 0x100000:
                cand.append((p, oid, local))
        tails, tail_idx, prev = [], [], [-1] * len(cand)
        for i, (_, oid, _) in enumerate(cand):
            k = bisect.bisect_left(tails, oid)
            if k == len(tails):
                tails.append(oid)
                tail_idx.append(i)
            else:
                tails[k] = oid
                tail_idx[k] = i
            prev[i] = tail_idx[k - 1] if k else -1
        i = tail_idx[-1] if tail_idx else -1
        while i >= 0:
            p, oid, local = cand[i]
            if oid not in objs:
                seg = oid >> 13
                flag = self.seg_flags[seg] if seg < len(self.seg_flags) else 0
                direct = not (flag & 0x20 or not flag & 0x08)
                objs[oid] = (p, oid, self._resolve(local, direct))
            i = prev[i]
        # Every detected header bounds the object before it, even when its
        # class is unknown (layers and named collections are such objects).
        self.starts = sorted(o[0] for o in objs.values())
        return sorted((o for o in objs.values() if o[2] in self.classes), key=lambda o: o[0])

    def body(self, off):
        """Payload of the object at cluster offset `off` (after the 8-byte header)."""
        i = bisect.bisect_right(self.starts, off)
        end = self.starts[i] if i < len(self.starts) else len(self.cluster)
        return self.cluster[off + 8 : end]

    def class_name(self, gidx):
        return self.classes[gidx][0]

    def of_class(self, name):
        return [(p, oid) for p, oid, g in self.objs if self.classes[g][0] == name]
