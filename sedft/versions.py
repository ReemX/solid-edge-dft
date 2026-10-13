"""Per-class format versions.

Every persisted class has its own format version, chosen by the release that saved the
file. Solid Edge ships the mapping as `Program\\DRAFT.VER`; the rows for the three classes
this reader needs are copied here so no Solid Edge install is required.

Each table: (object version, first application version that writes it), newest first.
Application version = `DocVersion2` major + minor / 100 (223.10 = Solid Edge 2026).
"""
import struct

JDIM_GUID = "{1D1928C0-0000-0000-C000-000000000046}"
JDOUBLEVALUE_GUID = "{D97A3FB0-1601-11CE-B7EE-08003601E53B}"
JDIMPARAMS_GUID = "{09D6BBB0-0000-0000-C000-000000000046}"

TABLES = {
    JDIM_GUID: [
        (39, 223.1), (38, 222.06), (37, 109.16), (36, 109.08), (35, 108.07),
        (34, 107.13), (33, 105.1), (32, 105.08), (31, 104.18), (30, 104.05),
        (29, 103.03), (28, 102.08), (27, 21.09), (26, 21.06), (25, 20.07),
        (24, 20.03), (23, 20.02), (22, 19.08), (21, 19.02), (20, 18.1),
        (19, 17.01), (18, 15.04), (17, 15.02), (16, 14.14), (15, 14.08),
        (14, 12.07), (13, 10.04), (12, 10.01), (11, 8.05), (10, 8.03), (9, 7.06),
        (8, 6.1), (7, 6.04), (6, 5.05), (5, 5.01), (4, 4.04), (3, 4.01),
        (2, 1.21), (1, 1.0),
    ],
    JDOUBLEVALUE_GUID: [(4, 110.1), (3, 109.08), (2, 109.06), (1, 1.0)],
    JDIMPARAMS_GUID: [
        (44, 224.06), (43, 222.06), (42, 222.04), (41, 109.12), (40, 109.11),
        (39, 109.05), (38, 109.02), (37, 108.07), (36, 107.05), (35, 106.04),
        (34, 105.08), (33, 105.03), (32, 104.07), (31, 104.06), (30, 103.15),
        (29, 102.11), (28, 102.05), (27, 20.08), (26, 20.02), (25, 19.11),
        (24, 19.01), (23, 18.15), (22, 18.08), (21, 18.07), (20, 18.02),
        (19, 17.01), (18, 15.02), (17, 14.17), (16, 12.08), (15, 12.06),
        (14, 11.04), (13, 10.04), (12, 10.01), (11, 9.03), (10, 8.05), (9, 8.01),
        (8, 7.08), (7, 7.05), (6, 7.02), (5, 6.04), (3, 5.03), (2, 1.21),
        (1, 1.0),
    ],
}


def app_version(ole):
    """Saving release from the `DocVersion2` stream: u16 minor, u16 major."""
    minor, major = struct.unpack("<HH", ole.openstream("DocVersion2").read()[:4])
    return major + minor / 100.0


def obj_version(guid, appver, table=None):
    """Newest object version whose application version is <= the saving release."""
    rows = (table or TABLES)[guid.upper()]
    for ov, av in rows:
        if av <= appver + 1e-9:
            return ov
    return rows[-1][0]


def read_ver_file(path):
    """Parse a DRAFT.VER from a Solid Edge install: class GUID -> [(objver, appver)]."""
    lines = [l.strip() for l in open(path, encoding="latin1")]
    n_app = int(lines[1])
    i = 3 + 2 * n_app
    out = {}
    while i < len(lines):
        g = lines[i].upper()
        i += 1
        rows = []
        while i < len(lines) and not lines[i].startswith("{"):
            if lines[i]:
                ov, av = lines[i].split()
                rows.append((int(ov), float(av)))
            i += 1
        out[g] = rows
    return out
