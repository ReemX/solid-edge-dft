"""JSheet member lists: u32 ids (z-order) terminated by 0; 0xFFFFFFFF a b = inclusive range a..b."""
import struct

from . import jdim


def members(body):
    out, i = [], 0
    while i + 4 <= len(body):
        x, = struct.unpack_from("<I", body, i)
        i += 4
        if x == 0:
            break
        if x == 0xFFFFFFFF:
            if i + 8 > len(body):
                break
            a, b = struct.unpack_from("<II", body, i)
            if b < a or b - a > 1_000_000:
                break
            i += 8
            out.extend(range(a, b + 1))
        else:
            out.append(x)
    return out, i


def sheet_of(store):
    """oid -> sheet oid, plus sheet oid -> member list."""
    own, lists = {}, {}
    for p, oid in store.of_class("JSheet Object"):
        m, _ = members(store.body(p))
        lists[oid] = m
        for x in m:
            own.setdefault(x, []).append(oid)
    return own, lists


def layers(store):
    """Layer oid -> (name, members). JLayerManager: u32 active, u32 n, n layer oids.
    Layer object: GUserText name, u32 flags, u32 count, count member oids (LYRMGR.DEX)."""
    lm = store.of_class("JLayerManager Object")
    if not lm:
        return {}
    r = jdim.R(store.body(lm[0][0]))
    oids = []
    try:
        _active, n = r.u32(), r.u32()
        for _ in range(n):
            oids.append(r.u32())
    except jdim.Short:
        pass
    pos = {}
    for p in store.starts:
        cls, oid = struct.unpack_from("<HI", store.cluster, p + 2)
        pos[oid] = p
    out = {}
    for oid in oids:
        if oid not in pos:
            continue
        lr = jdim.R(store.body(pos[oid]))
        try:
            name = jdim.guser_text(lr)
            _flags, cnt = lr.u32(), lr.u32()
            out[oid] = (name, [lr.u32() for _ in range(cnt)])
        except Exception:
            out[oid] = ("?", [])
    return out


def hidden_layers(sheet_body, layer_oids):
    """JLayerSettings in the sheet body: u32 n, n x (u32 layer oid, u8 hidden). Located by
    matching entries against the document's layer oids (lyrmgr JLayerSettings::Serialize)."""
    b = sheet_body
    for i in range(0, len(b) - 9):
        n, = struct.unpack_from("<I", b, i)
        if not (1 <= n <= len(layer_oids)) or i + 4 + 5 * n > len(b):
            continue
        ents = [(struct.unpack_from("<I", b, i + 4 + 5 * k)[0], b[i + 8 + 5 * k]) for k in range(n)]
        if all(o in layer_oids and f in (0, 1) for o, f in ents):
            return {o for o, f in ents if f}
    return set()


def view_sheet_parents(store, own, sheet_oids, named):
    """Internal (drawing-view) sheets -> owning working sheet.

    A view sheet is tied to its Drawing View by an association relation object that
    references both; the Drawing View is a member of a working sheet."""
    c = store.cluster
    internal = [s for s in sheet_oids if s not in named]
    if not internal:
        return {}
    parent = {}
    want = {struct.pack("<I", s): s for s in internal}
    for p in store.starts:
        b = store.body(p)
        hits = [s for k, s in want.items() if k in b]
        if not hits:
            continue
        refs = {struct.unpack_from("<I", b, o)[0] for o in range(0, len(b) - 3)}
        for s in hits:
            if s in parent:
                continue
            for r in refs:
                for sh in own.get(r, []):
                    if sh != s and sh in named:
                        parent[s] = sh
                        break
                if s in parent:
                    break
    return parent
