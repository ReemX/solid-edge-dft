"""OLE property sets: the custom properties a .dft carries (Document Number, Revision, ...)."""
import struct


def property_set(data: bytes):
    """Parse one OLE property set section into {name or id: value}.

    Solid Edge writes codepage 1200, so VT_LPSTR strings are UTF-16 and their
    length counts bytes. Names come from the dictionary (property id 0).
    """
    sec = struct.unpack_from("<I", data, 44)[0]
    count = struct.unpack_from("<I", data, sec + 4)[0]
    offsets = {}
    for i in range(count):
        pid, off = struct.unpack_from("<II", data, sec + 8 + 8 * i)
        offsets[pid] = sec + off
    names = {}
    if 0 in offsets:
        p = offsets[0]
        n = struct.unpack_from("<I", data, p)[0]
        p += 4
        for _ in range(n):
            pid, chars = struct.unpack_from("<II", data, p)
            p += 8
            names[pid] = data[p : p + 2 * chars].decode("utf-16le").rstrip("\x00")
            p += 2 * chars
            p += (-p) % 4
    out = {}
    for pid, p in offsets.items():
        if pid in (0, 1) or pid & 0x80000000:
            continue
        vt = struct.unpack_from("<I", data, p)[0]
        if vt in (0x1E, 0x1F):
            size = struct.unpack_from("<I", data, p + 4)[0]
            size = size if vt == 0x1E else 2 * size
            value = data[p + 8 : p + 8 + size].decode("utf-16le").rstrip("\x00")
        elif vt == 0x03:
            value = struct.unpack_from("<i", data, p + 4)[0]
        else:
            continue
        out[names.get(pid, pid)] = value
    return out


def custom_properties(ole):
    """Merge every property set that carries named (dictionary) properties."""
    out = {}
    for entry in ole.listdir():
        if len(entry) != 1 or not entry[0].startswith("\x05"):
            continue
        try:
            props = property_set(ole.openstream(entry).read())
        except (struct.error, UnicodeDecodeError):
            continue
        out.update({k: v for k, v in props.items() if isinstance(k, str)})
    return out
