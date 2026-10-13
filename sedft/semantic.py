"""Solid Edge .dft -> semantic dimensions, straight from the object store.

Every rule here is transcribed from Solid Edge 2026 binaries (see docs/): layouts from
Annot.DEX DIMPERST.CPP / DIMSTYL.CPP, values from JDim GetValue (FUN_1804242d0), text from
dimsrvcs JDimConvertValueToTextA / JDimSupressDigit, property names from FwkSupp automation
plus HANNOT helpers.
"""
import math
import re
import struct

from . import dimparams, jdim, sheets, versions
from .dimstyle_names import NAMES as OFF2PROP
from .props import custom_properties
from .psm import Store

DIM_TYPES = {1: "linear", 2: "radius", 3: "angle", 4: "diameter", 5: "diameter",
             6: "arcLength", 7: "arcAngle", 8: "coordinate", 9: "symmetricDiameter",
             10: "chamfer", 11: "angularCoordinate", 12: "curveLength"}
DISPLAY_TYPES = {1: "nominal", 2: "tolerance", 3: "classFit", 4: "limits", 5: "basic",
                 6: "reference", 8: "blank", 9: "classPlusMinus", 10: "holeShaft",
                 11: "fitWithLimits", 12: "holeCallout", 13: "holeShaftTolOnly",
                 14: "holeShaftWithTol", 15: "unitTolerance"}
AXIS_MODES = {1: "default", 2: "implied", 3: "explicit", 4: "coordinate"}
LINEAR_UNITS = {1: ("ftin", 1 / 0.0254), 2: ("m", 1.0), 3: ("mm", 1000.0), 4: ("cm", 100.0),
                5: ("in", 1 / 0.0254), 6: ("ft", 1 / 0.3048)}
EPS = 1e-10  # GetDistanceTolerance() stand-in; only nudges exact .5 ties upward

TWO_PI, HALF_PI, THREE_HALF_PI = 2 * math.pi, math.pi / 2, 3 * math.pi / 2


# ------------------------------------------------------------ style manager
def style_tables(store):
    """Named / unnamed style tables from the StyleManager object (partial on damage)."""
    named, unnamed = {}, {}
    sm = store.of_class("StyleManager")
    if not sm:
        return named, unnamed
    r = jdim.R(store.body(sm[0][0]))
    try:
        n, _mx = r.u32(), r.u32()
        for _ in range(n):
            sid, oid, _b, parent = r.u32(), r.u32(), r.u32(), r.u32()
            name = jdim.guser_text(r)
            r.u32(); r.u16(); r.u16(); r.u16()
            named[sid] = (oid, name, parent)
        n, _mx = r.u32(), r.u32()
        for _ in range(n):
            sid, oid, refc, parent = r.u32(), r.u32(), r.u32(), r.u32()
            unnamed[sid] = (oid, refc, parent)
    except (jdim.Short, UnicodeDecodeError):
        pass
    return named, unnamed


def decode_params(raw):
    """JDimParameters raw field dict -> {DimStyle property: value}."""
    out = {}
    for off, val in raw.items():
        name = OFF2PROP.get(off) if isinstance(off, int) else None
        if not name:
            continue
        if isinstance(val, bytes):
            if len(val) == 8:
                val = struct.unpack("<d", val)[0]
            else:
                val = int.from_bytes(val, "little")
        out[name] = val
    return out


# ------------------------------------------------------------ value logic
def display_value(d):
    """JDim GetValue (Annot FUN_1804242d0), from stored fields only."""
    a = d["attr"]
    t, w4, f8, fC = a["type"], a["w4"], a["flags8"], a.get("flagsC", 0)
    v = d["d18f8"]
    status_ok = (f8 & 3) == 0 or d.get("u1910", 4) in (0, 3, 4)
    notes = []
    if not status_ok:
        notes.append("constraintStatusNotOk")   # SE would recompute from geometry
    if (f8 & 3) == 0 or (fC & 0x2000):
        return v, notes
    if t == 3:
        b3, b4, b5, b6 = (w4 >> 3) & 1, (w4 >> 4) & 1, (w4 >> 5) & 1, (w4 >> 6) & 1
        grouped = (a.get("u10", 0) & 0x10) and (w4 & 4) and d.get("u104", 0)
        if not grouped:
            if (b6 == 0 and b3) or (b6 and not b3):
                v = TWO_PI - v
            if b4 != b5:
                v -= math.pi
        else:
            base = HALF_PI if b4 == b5 else THREE_HALF_PI
            v = (base - v) if (w4 & 8) else (v - base)
            if v < 0:
                v += TWO_PI
            notes.append("groupedAngular")
    elif t == 0xB:
        if w4 & 8:
            v = (TWO_PI - v) if not (w4 & 0x20) or abs(v) > 1e-9 else 0.0
    elif t in (4, 5, 9):
        if status_ok:
            v = 2 * v
    elif t == 2:
        if (fC >> 27) & 1 and a.get("u10", 0) & 1 and (fC & 0xC0) == 0xC0 and status_ok:
            v = 2 * v
    elif t == 6 and d.get("bc8", 0) == 0:
        g = next((x["geom"] for x in d["geom"] if x["geom"][0] == "t"), None)
        if g:
            v = v * g[1][2]
        else:
            notes.append("arcLengthRadiusUnknown")
    if (fC & 1) and (f8 & 1) and status_ok and len(d["parents"]) > 1:
        v = -v
    return v, notes


def round_text(x, code, delim, lead, trail):
    """Roundoff code (DimDecimalRoundOffTypeConstants) -> text, SE rules."""
    if code in (1, 2):
        step = 10 if code == 1 else 1
        n = int(step * 0.5 + x)
        return str(n - n % step)
    dec = max(code - 2, 0)
    s = "%.*f" % (dec, x + EPS)
    if dec:
        sep = {1: ".", 2: ",", 3: " "}.get(delim, ".")
        s = s[: len(s) - dec - 1] + sep + s[len(s) - dec:]
    if not lead:
        s = s.lstrip("0") or "0"
    if not trail and dec:
        s = s.rstrip("0")
        if s[-1:] in (".", ","):
            s = s[:-1]
    return s


def _round_int(x, even):
    """Round to int; SE uses round-half-even when RoundUp member (+0x9e) == 2."""
    n = math.floor(x + 0.5)
    if even and abs(x + 0.5 - n) < 1e-9 and n % 2:
        n -= 1
    return int(n)


def dms_text(deg, code, even):
    """JDimGetAngularText DMS branch: AngularDMSRoundOff 1 10deg, 2 1deg, 3 10', 4 1', 5 10", 6 1"."""
    D = "\u00b0"
    if code in (1, 2):
        step = 10 if code == 1 else 1
        n = _round_int(deg / step, even) * step
        return f"{n}{D}"
    if code in (3, 4):
        step = 10 if code == 3 else 1
        m = _round_int(deg * 60 / step, even) * step
        return f"{m // 60}{D} {m % 60}'"
    step = 10 if code == 5 else 1
    sec = _round_int(deg * 3600 / step, even) * step
    return f"{sec // 3600}{D} {sec % 3600 // 60}' {sec % 60}\""


def fraction_text(x, code, even):
    """JDimValueToFractionText: denominator 2**(code-1), reduced, 'W N/D'."""
    den = 1 << max(code - 1, 0)
    total = _round_int(x * den, even)
    whole, num = divmod(total, den)
    if num == 0:
        return str(whole)
    g = math.gcd(num, den)
    frac = f"{num // g}/{den // g}"
    return f"{whole} {frac}" if whole else frac


_LINES = {}


def line_geom(s, oid):
    """Line Object (2D line): u16, f64 x1, y1, x2, y2 (sheet metres), u32. None if not a line."""
    idx = _LINES.get(id(s))
    if idx is None:
        idx = _LINES[id(s)] = {o: p for p, o in s.of_class("Line Object")}
    p = idx.get(oid)
    if p is None:
        return None
    b = s.body(p)
    return struct.unpack_from("<4d", b, 2) if len(b) >= 34 else None


def value_text(t, v, style):
    if v is None or not math.isfinite(v):
        return None, v
    even = style.get("RoundUp", 0) == 2
    if t in (3, 7, 11):
        deg = math.degrees(v) % 360
        units = style.get("AngularUnits", 3)
        if units == 1:
            return dms_text(deg, style.get("AngularDMSRoundOff", 4), even), deg
        if units == 2:  # radians
            r = math.radians(deg)
            return round_text(r, style.get("AngularDecimalRoundOff", 2), style.get("Delimiter", 1),
                              style.get("PrimaryLeadingZeros", 1), style.get("PrimaryTrailingZeros", 1)), r
        code = style.get("AngularDecimalRoundOff", 2)
        return round_text(deg, code, style.get("Delimiter", 1),
                          style.get("PrimaryLeadingZeros", 1), style.get("PrimaryTrailingZeros", 1)) + "\u00b0", deg
    unit, k = LINEAR_UNITS.get(style.get("PrimaryUnits", 3), ("mm", 1000.0))
    x = abs(v) * k
    return linear_text(x, style), x


def linear_text(x, style):
    """Annot FUN_180325630: x already in style units (inches for ft-in)."""
    even = style.get("RoundUp", 0) == 2
    frac = style.get("RoundOffType", 1) == 2
    label = style.get("PrimaryUnitLabel") or ""
    sublabel = style.get("PrimarySubunitsLabel") or ""

    def num(val):
        if frac:
            return fraction_text(val, style.get("PrimaryFractionRoundOff", 5), even)
        return round_text(val, style.get("PrimaryDecimalRoundOff", 4), style.get("Delimiter", 1),
                          style.get("PrimaryLeadingZeros", 1), style.get("PrimaryTrailingZeros", 1))

    if style.get("PrimaryUnits", 3) == 1:  # feet-inches
        maxsub = style.get("MaximumSubunits", 12) or 12
        if x < maxsub:                      # below one foot: inches only
            return num(x) + sublabel
        feet = int(x // 12)
        return f"{feet}{label}-" + num(x - feet * 12) + sublabel
    return num(x) + label


def axis_mode(w4):
    if w4 & 2:
        return 3
    if w4 & 1:
        return 2
    return (w4 & 0x200 | 0x80) >> 7


# ------------------------------------------------------------ main
def extract(path):
    s = Store(path)
    av = versions.app_version(s.ole)
    vj = versions.obj_version(versions.JDIM_GUID, av)
    vdv = versions.obj_version(versions.JDOUBLEVALUE_GUID, av)
    vp = versions.obj_version(versions.JDIMPARAMS_GUID, av)
    byid = {oid: s.class_name(g) for _, oid, g in s.objs}
    named, unnamed = style_tables(s)
    own, lists = sheets.sheet_of(s)
    lyr = sheets.layers(s)
    layer_of = {m: l for l, (_n, ms) in lyr.items() for m in ms}
    hidden = {}
    for p, oid in s.of_class("JSheet Object"):
        hidden[oid] = sheets.hidden_layers(s.body(p), set(lyr))
    sheet_names = {}
    for p, oid in s.of_class("JSheet Object"):
        b = s.body(p)
        _m, end = sheets.members(b)
        mm = re.search(rb"(?:[\x20-\x7e]\x00){2,}", b[end:])
        sheet_names[oid] = mm.group().decode("utf-16le") if mm else str(oid)
    named_sheets = {o for o, n in sheet_names.items() if n != str(o)}
    view_parent = sheets.view_sheet_parents(s, own, list(sheet_names), named_sheets)
    params = {}
    for p, oid in s.of_class("JDimParameters Object"):
        try:
            raw, _ = dimparams.read_params(s.body(p), vp)
            params[oid] = decode_params(raw)
        except Exception:
            params[oid] = {"_damaged": True}

    # Background sheet of each working sheet: JBackgroundSheetWrapper (u32 sheet oid, u8)
    # sits in the working sheet's member list.
    background = {}
    for p, oid in s.of_class("CLSID_JBackgroundSheetWrapper"):
        bg = struct.unpack_from("<I", s.body(p), 0)[0]
        for sh in own.get(oid, []):
            background[sh] = bg
    # Text boxes: f64 x, f64 y (sheet metres), GUserText.
    boxes = {}
    for p, oid in s.of_class("CLSID_JTextBox"):
        b = s.body(p)
        try:
            x, y = struct.unpack_from("<dd", b, 0)
            t = jdim.guser_text(jdim.R(b, 16))
        except Exception:
            continue
        for sh in own.get(oid, []):
            boxes.setdefault(sh, []).append((x * 1000, y * 1000, t.replace("\r", "\n"), 0.0))

    def style_for(sid):
        if sid & 0x80000000:
            ent = named.get(sid & 0x7FFFFFFF)
            return (ent[1], params.get(ent[0], {})) if ent else (None, {})
        ent = unnamed.get(sid)
        if not ent:
            return None, {}
        parent = named.get(ent[2] & 0x7FFFFFFF, (None, None))[1]
        return (f"{parent} (override)" if parent else "override"), params.get(ent[0], {})

    dims = []
    for p, oid in s.of_class("CLSID_JDim") + s.of_class("JDim Object"):
        body = s.body(p)
        parse_note = None
        try:
            d = jdim.read_jdim(body, vj, vdv)
            if d["_end"] != d["_len"]:
                parse_note = f"recordLength {d['_end']}/{d['_len']}"
        except Exception as e:  # fail soft: keep the fixed prefix (bundle, parents, value, geometry)
            parse_note = f"partialParse: {type(e).__name__}"
            r = jdim.R(body)
            try:
                d = {"attr": jdim.attribute_bundle(r, vj), "slots": {}, "geom": []}
            except Exception as e2:
                dims.append({"id": oid, "sheet": sheet_names.get(own.get(oid, [None])[0]),
                             "error": f"unreadable record: {type(e2).__name__}: {e2}"})
                continue
            try:
                d["parents"] = jdim.parents(r, vj)
                if vj >= 5:
                    r.f64()
                r.u32(); r.u32()
                d["d18f8"] = r.f64()
                d["geom"] = jdim.geometry(r, vj, d["attr"].get("flagsC", 0))
            except Exception:
                d.setdefault("parents", [])
                d.setdefault("d18f8", float("nan"))
        a = d["attr"]
        t = a["type"]
        style_name, style = style_for(d.get("u18e0", 0))
        v, notes = display_value(d)
        if style.get("_damaged") or not style:
            notes = notes + ["styleUnavailable (defaults used)"]
        text, num = value_text(t, v, style)
        ent = {
            "id": oid,
            "type": DIM_TYPES.get(t, t),
            "display": DISPLAY_TYPES.get(a["disp"], a["disp"]),
            "value": num,
            "text": text,
            "style": style_name,
            "axisMode": AXIS_MODES.get(axis_mode(a["w4"]), axis_mode(a["w4"])),
            "driving": bool(a["flags8"] & 1),
            "parents": [{"oid": q["ref"], "class": byid.get(q["ref"]), "keypoint": q["u70"]}
                        for q in d["parents"]],
        }
        sh = own.get(oid, [None])[0]
        if sh in view_parent:
            ent["viewSheet"] = sh
            ent["sheet"] = sheet_names.get(view_parent[sh], view_parent[sh])
        else:
            ent["sheet"] = sheet_names.get(sh, sh)
        lo = layer_of.get(oid)
        ent["layer"] = lyr[lo][0] if lo else None
        ent["visible"] = not (lo and lo in hidden.get(sh, set()))
        if t in (1, 8, 9, 11) and "d1928" in d:
            ax = [d["d1928"], d["d1930"]]
            ent["axis"] = ax
            if t == 1:
                # Slanted measurement axis = true length along that direction (DXF aligned);
                # horizontal/vertical axis = projection (DXF rotated / "linear").
                # Same 0.5 degree threshold as rule B (sketches are often drawn a hair off H/V).
                off = math.degrees(math.atan2(abs(ax[1]), abs(ax[0]))) % 90
                ent["kind"] = "aligned" if min(off, 90 - off) > 0.5 else "linear"
        up, lo = d.get("d1b18"), d.get("d1b20")
        unit, k = LINEAR_UNITS.get(style.get("PrimaryUnits", 3), ("mm", 1000.0))
        if up is None and a["disp"] in (4, 15):
            # Before JDim v32 only SE's own tolerance strings exist ("0.100 mm").
            def _num(sl):
                m = re.match(r"\s*[+-]?([0-9]*[.,]?[0-9]+)", d["slots"].get(sl) or "")
                return float(m.group(1).replace(",", ".")) / k if m else None
            up, lo = _num(2), _num(3)
        if a["disp"] == 2:
            # Alpha tolerance: SE draws slots 2/3 verbatim ("+0.05" / "-0.02"); the numeric
            # fields stay 0 (GUI-verified 2026-10-13). Signed values come from the strings.
            def _signed(sl):
                m = re.fullmatch(r"\s*([+-]?)\s*([0-9]*[.,]?[0-9]+)\s*", d["slots"].get(sl) or "")
                return float(m.group(1) + m.group(2).replace(",", ".")) if m else None
            ut, lt = d["slots"].get(2) or "", d["slots"].get(3) or ""
            u, l = _signed(2), _signed(3)
            if ut or lt:
                ent["tolerance"] = {"upper": u, "lower": l, "unit": unit, "alpha": True,
                                    "upperText": ut, "lowerText": lt}
            up = lo = None
        if a["disp"] in (4, 15) and up is not None and lo is not None:
            ent["tolerance"] = {"upper": up * k, "lower": -lo * k, "unit": unit,
                                "upperText": d["slots"].get(2), "lowerText": d["slots"].get(3)}
            if a["disp"] == 4 and t not in (3, 7, 11):
                ent["limitsText"] = [linear_text(num + up * k, style), linear_text(num - lo * k, style)]
        # Prefix/suffix/superfix/subfix = the 4 strings after the 7 slots (automation text
        # indices 8..11). Hole-callout codes: %HS hole size (= the value), %HD hole depth,
        # %BS/%BD counterbore size/depth, %SS/%SA countersink size/angle, %TD thread depth.
        s4 = d.get("str4") or ["", "", "", ""]
        texts = {k: x for k, x in zip(("prefix", "suffix", "superfix", "subfix"), s4) if x}
        if texts:
            ent["texts"] = texts
        if a["disp"] in (3, 9, 10, 11, 13, 14):          # class-fit displays
            ent["fit"] = {"hole": d["slots"].get(0x12) or None, "shaft": d["slots"].get(0x13) or None}
        chamfer = None
        if t == 10:
            # The angle is not stored: SE (CHAMG2D.CPP JDimComputeChamferAngle) takes the angle
            # between the chamfer line and the reference, folded into 0..90 deg, and draws
            # "<length> X <angle>" (GUI-verified: "27,17 X 45°"). Slot 13 overrides the angle text.
            lines = [line_geom(s, q["ref"]) for q in d["parents"]]
            ang_text = d["slots"].get(13) or None
            if not ang_text and len(lines) >= 2 and all(lines[:2]):
                (ax1, ay1, ax2, ay2), (bx1, by1, bx2, by2) = lines[:2]
                ang = abs(math.atan2(ay2 - ay1, ax2 - ax1) - math.atan2(by2 - by1, bx2 - bx1)) % math.pi
                ang = min(ang, math.pi - ang)
                ent["chamferAngle"] = math.degrees(ang)
                ang_text = value_text(3, ang, style)[0]
                if abs(math.degrees(ang) - 45) > 1e-6:
                    notes = notes + ["chamferAngleComplementUnverified"]
            if ang_text and text:
                chamfer = f"{text} X {ang_text}"
            else:
                notes = notes + ["chamferAngleUnavailable"]
        override = d["slots"].get(1)
        if override:
            ent["override"] = override
        shown = chamfer or text
        if override:
            shown = override
        elif t in (8, 11) and d["slots"].get(0xC) and abs(num or 0) < 1e-9 \
                and style.get("DisplayCoordinateOriginText", 0):
            shown = d["slots"][0xC]          # ordinate origin label ("X1")
        if shown is not None and (texts.get("prefix") or texts.get("suffix")):
            full = texts.get("prefix", "") + shown + texts.get("suffix", "")
            full = full.replace("%HS", " " + shown if "%HS" in texts.get("prefix", "") else shown)
            if "%HS" in texts.get("prefix", ""):
                full = texts["prefix"].replace("%HS", " ") + shown + texts.get("suffix", "")
            ent["displayText"] = full.strip()
            if re.search(r"%[A-Z][A-Z0-9]", ent["displayText"]):
                notes = notes + ["unresolvedTextCode"]
        elif shown != text:
            ent["displayText"] = shown
        if parse_note:
            notes = notes + [parse_note]
        if notes:
            ent["notes"] = notes
        dims.append(ent)
    # Per working sheet that holds dimensions: its background and the text boxes of both
    # (title block fields, notes, general tolerance tables), top of the sheet first.
    sheets_out = {}
    for sh in sorted({view_parent.get(own.get(d["id"], [None])[0], own.get(d["id"], [None])[0])
                      for d in dims} - {None}):
        texts = boxes.get(sh, []) + boxes.get(background.get(sh), [])
        sheets_out[sheet_names.get(sh, sh)] = {
            "background": sheet_names.get(background.get(sh)),
            "texts": [t[2] for t in sorted(texts, key=lambda t: (-t[1], t[0]))],
        }
    props = custom_properties(s.ole)
    meta = {k: v for k, v in (("number", props.get("Document Number")),
                              ("revision", props.get("Revision"))) if v}
    return {"app": av, "versions": {"JDim": vj, "JDimParameters": vp, "JDoubleValue": vdv},
            "meta": meta,
            "styles": {sid: name for sid, (_o, name, _p) in named.items() if _o in params},
            "sheets": sheets_out,
            "dimensions": dims}
