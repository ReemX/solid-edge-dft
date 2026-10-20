# Solid Edge .dft: dimension format, decoded from the binaries

Source of truth: Solid Edge 2026 binaries, decompiled with Ghidra 12.1.4
(`tools/ghidra/`). Reference implementation: the `sedft` package (`jdim.py`, `dimparams.py`
+ generated `dimparams_table.py`, `sheets.py`, `semantic.py`). Raw research log:
`RESEARCH-LOG.md`. Function addresses (`FUN_18...`) refer to the Solid Edge 2026 DLLs as
loaded by Ghidra at their default image base.

Validation corpus: 41 files, SE v15.21 (2003), v19, ST5, ST7, 2023, 2026 (public samples and
private drawings; not included).
- 732/732 JDim records and 626/626 JDimParameters records parse to the exact record end.
- 732/732 dims land on exactly one sheet; 12,215 sheet members all resolve.
- Computed display text is literally on the sheet image for 716/716 verifiable dims.

## 1. Versions

Every persisted class has its own format version, chosen by the release that saved the file.

- Saving release: OLE stream `DocVersion2` = u16 minor, u16 major (`02 00 e2 00` = 226.02).
- `Program\DRAFT.VER` (text, shipped with SE): app name, n releases, n classes, the release
  list, then per class a GUID line followed by `objver appver` lines, newest first.
  Object version = the newest `objver` whose `appver` <= saving release.
- GUIDs: JDim `{1D1928C0-0000-0000-C000-000000000046}`, JDimParameters
  `{09D6BBB0-0000-0000-C000-000000000046}`, JDoubleValue `{D97A3FB0-1601-11CE-B7EE-08003601E53B}`.
  For 226.x: JDim 39, JDimParameters 44, JDoubleValue 4.
- Class name in older typetables: `JDim Object` (v15) = `CLSID_JDim`.

Serializers chain: `persist_serializeN` calls an earlier version first, then appends.
JDim: base `serialize5` (v3/v4 have their own base), then 6, 7/8, 9, ... 39 linearly.
JDimParameters: base v4, then 5..44 linearly except v8 calls v6 (v7 fields never apply after v8).

## 2. Primitives

- raw n bytes, little endian.
- `wstr` (SerializeString): u32 n chars incl. NUL (0 = empty), then n UTF-16 units.
- `GUserText` (JUTIL2): u32 n chars, no NUL, then n UTF-16 units.

## 3. JDim (object payload after the 8-byte `QQ` header)

### 3.1 Attribute bundle (`JDimSerializeAttributeBundle`, 200-byte struct)
```
u8 type        DimTypeConstants: 1 linear 2 radial 3 angular 4 r-diameter 5 c-diameter
               6 arc length 7 arc angle 8 coordinate 9 sym diameter 10 chamfer
               11 angular coordinate 12 curve length
u8 display     DimDispTypeConstants: 1 nominal 2 tolerance 3 classfit 4 limits 5 basic
               6 reference 8 blank 9..14 fits 15 unit tolerance (+/-)
u8 breakPos    1 right 2 center 3 left 4 alt center
u16 w4         flags: bit0 implied axis, bit1 explicit axis, bit2 axis direction,
               bits3..6 angular quadrant rules, bit9 (axis mode)
u16 w6
u32 flags8     bit0 driving, bit0|1 = constrained, 0x40 display by name, 0x2000 inspection
f32 x7         +0x14 break dist, +0x18 track dist, +0x1c track angle (type 5), +0x20 leader dist,
               +0x24, +0x28, +0x2c
f64 +0x30, f64 +0x58, [v>4] f64 +0x60, f64 +0x68
[v>7] f32, [v>=9] u32 +0x70, [v>3] u8 +0x74, [v>10] u32 flagsC
type 8|11: [v>13] u16 n, n x 12 bytes; [v>17] f64
type 1,3,5,6,7,9 and v>29: u16 n; if n: u32,u32,f64, n x 12 bytes (jog points);
                           u16 m; if m: u32,u32,f64, m x 12 bytes; f64
other types: [v>17] f64
[v>18] u32 +0x10, [v>=21] f64, [v>=33] f64, [v>=34] f64, [v>=35] u32, [v>=37] f64
```
MeasurementAxisEx = 3 if w4&2, 2 if w4&1, else ((w4&0x200)|0x80)>>7.

### 3.2 Body (v >= 17)
```
geometry parents: u32 n (<=4), n x {u32 element oid, u16 guid-table idx, u32 flags,
                  f64, u32, u32, u32 keypoint (1 start 2 end 4 center), f64}
f64 +0x18e8, u32 +0x100, u32 +0x108
f64 VALUE (+0x18f8, metres / radians)
geometry cache: u32 n, n x {u32 kind, 4 x f64, [v>15 && flagsC&0x20000004] 2 x f64,
                [v>21 && flagsC&0x8000000] 6 x f64, tag}
   tag u8: 'g' 6 f64 (line: point, dir, t0, t1) | 's' 5 f64 + u8 (circle: centre, r, ...)
           | 't' 5 f64 + u8 + 2 f64 (arc) | 0x8c 2 f64 | 0x7f bspline | 'x' bspline + 7 f64
           bspline: u8, u32 np, u32 rational, u8, u8, u32 nk, f64, u8, np x 16, [rational] np x 8, nk x 8
text slots 1..7 (wstr), then 4 wstr
[v<24] range: [v<36] u8 f else u32 f; f&3 f64 low; f&0xc f64 high
[v>=6, type 1/8/9/11] f64, f64 = measurement AXIS vector
[v>=7] u32 STYLE ID     [v>=9] slot 0xc     [v>=10] f64, u32 constraint status (0/3/4 = ok)
[v>=12] f64             [v>=13] slot 0xd    [17<=v<24 && flagsC&0x80000] GUserText
[v>=19] u8, u8          [v>=20] wstr        [v>=22] u8 m; m&1 f64
[v>=23] u32 n, n x u32  [v>=24] JDoubleValue (section 4)
[v>=25 && flagsC&0x20000000] u32   [v>=26] u32   [v>=27] f64   [v>=28] slots 0x12, 0x13
[v>=29 && flags8&0x200] u32        [v>=31] slot 0x14
[v>=32] f64 UPPER TOL, f64 LOWER TOL (metres, lower as magnitude)
[v>=34] slot 0x4a       [v>=38/39, flagsC&0x8000000] u32 n, n x u32 (each)
```
Text slots: 2/3 primary upper/lower tolerance strings ("0.100 mm"), 4 tolerance symbol,
5/6 secondary tolerances, 8 prefix, 9 suffix, 10 superfix, 11 subfix, 13 chamfer angle override,
14..17 displayed prefix/suffix/superfix/subfix, 18/19 hole/shaft fit class.

## 4. JDoubleValue (EXPRDEX, the dimension's variable)
```
v1: f64 value, u16, u16 flags
    flags&0x10: limits {u8 (dv<3) | u32 lf; lf&3 f64 low; lf&0xc f64 high;
                lf&0x10 u32 n, n f64 discrete; flags&0x20 f64}
    flags&0x1000 GUserText formula; 0x2000 GUserText; 0x4000 GUserText; 0x400 GUserText
v2: limits && lf&0x20 u32; lf&0x40 u32
v3: limits && lf&0x100 u32 n, n f64
v4: nested IJPersist object, 8 bytes (02 00 00 00 00 00 00 00 everywhere seen)
```

## 5. Displayed value (JDim GetValue, Annot FUN_1804242d0)
v = VALUE. Adjust only when flags8&3 and not flagsC&0x2000:
- diameter types 4/5/9: v *= 2 when status ok (2D sketch dims store the radius; drawing-view
  dims are unconstrained and store the diameter).
- angular (3): quadrant rules on w4 bits 3..6 (2pi - v, -pi).
- arc length (6, byte +0xc8 == 0): v = angle x arc radius.
- flagsC&1 && flags8&1 && 2 parents: v = -v.

## 6. Style
- StyleID (`+0x18e0`): `0x80000000|n` = named style n; positive = unnamed override style.
- StyleManager object: u32 nNamed, u32 max, {u32 id, u32 oid, u32, u32 parent, GUserText name,
  u32, u16, u16, u16} x nNamed; u32 nUnnamed, u32 max, {u32 id, u32 oid, u32 refcount,
  u32 parent named id} x nUnnamed.
- Each JDimParameters record is a complete style. Field table: `sedft/dimparams_table.py`
  (member offsets); names: `sedft/dimstyle_names.py` (member offset -> DimStyle property).
  Key members: PrimaryUnits 0xb8 (DimLinearUnitConstants), RoundOffType 0x9a,
  PrimaryDecimalRoundOff 0xba, Delimiter 0x9d, LeadingZeros 0xbc, TrailingZeros 0xbd,
  AngularUnits 0x188, AngularDecimalRoundOff 0x18a, Height 0x198, Font 0x1c8,
  TextOrientation 0x2c9, PrimaryLinearToleranceDecimalRoundOff 0x122.

## 7. Text (dimsrvcs JDimConvertValueToTextA + JDimSupressDigit)
- round-off code c (DimDecimalRoundOffTypeConstants): 1 -> nearest 10, 2 -> integer,
  c>=3 -> sprintf("%.*lf", c-2, v + tolerance).
- decimal point -> Delimiter (1 '.', 2 ',', 3 ' ').
- leading-zeros flag 0 strips leading '0'; trailing-zeros flag 0 strips trailing zeros and a
  dangling separator.
- Angles: degrees, AngularDecimalRoundOff, then '°'. Limits: max and min with primary precision.
- DMS, fractions and feet-inches: see section 10.

## 8. Kind (aligned vs linear)
Axis vector within 0.5 deg of horizontal/vertical: linear (projection); otherwise aligned
(true length along a slanted direction). Solid Edge's own DXF export labels aligned/rotated
inconsistently and does not follow MeasurementAxisEx.

## 9. Sheets, layers, title block
- JSheet body starts with its MasterGroup member list: u32 oids in z-order, terminated by 0;
  `FFFFFFFF a b` = inclusive range a..b. Sheet name = first UTF-16 string after the list.
- Working -> background sheet: `CLSID_JBackgroundSheetWrapper` (u32 sheet oid, u8) in the
  working sheet's member list.
- Layers: `JLayerManager` u32 active, u32 n, n layer oids. Layer object: GUserText name,
  u32 flags, u32 count, count member oids. Per sheet `JLayerSettings`
  (u32 n, n x {u32 layer oid, u8 hidden}) inside the sheet body. Hidden layer = not drawn.
- Text boxes (`CLSID_JTextBox`): f64 x, f64 y (sheet metres), GUserText (logical order, Hebrew
  intact). Title block property fields are `CLSID_JBalloon` with `%{...}` links and cached values.
- Meta: custom OLE property set (`Document Number`, `Revision`).

## 10. Additions (second pass, 2026-10-13)
- **JDoubleValue v4 nested object** (object +0xe0, wired at runtime; class not identifiable
  statically): 8 bytes everywhere seen. The reader verifies the size against the record end and
  retries other sizes, so a different nested payload still parses (flag `nestedNonStandard`).
- **Old JDim versions**: parents are 38 B (v>=17), 30 B (v15-16, no trailing f64), 22 B (v<15);
  v3/v4 base has no f64 at +0x18e8. Supported back to JDim v3; v1/v2 (pre-V5) are not.
- **Texts**: slot 1 = OverrideString (the drawing shows it instead of the value);
  the 4 strings after the 7 slots = prefix, suffix, superfix, subfix; slot 0x0c = ordinate origin
  label, shown for a zero coordinate dim when style DisplayCoordinateOriginText is on.
  Hole-callout codes in those strings: %HS hole size (= the value), %HD hole depth,
  %BS/%BD counterbore size/depth, %SS/%SA countersink size/angle, %TD thread depth.
- **Fits**: slots 0x12/0x13 = hole / shaft class (display types 3, 9-14).
- **Chamfer**: value = stored length; the angle is not stored. SE (CHAMG2D.CPP) takes the angle between
  the two parent lines folded into 0..90 deg and draws "<len> X <angle>"; slot 13 overrides the angle text.
  Line Object body: u16, f64 x1 y1 x2 y2 (metres), u32. GUI-verified "27,17 X 45°"; which complement SE
  shows for non-45 chamfers and the style flag ChamferUse45DegreeCharacter (+0x842, v12+) are untested.
  ChamferDimensionMode is just w4 bits 0/1 (orientation), not a text format.
- **Alpha tolerance** (display 2): SE draws slots 2/3 verbatim; +0x1B18/+0x1B20 stay 0. GUI-verified
  "30 +0.05 -0.02". Class fit (display 3) "60 D9" GUI-verified.
- **Formatting**: DMS (AngularDMSRoundOff +0x189: 10deg..1"), fractions (PrimaryFractionRoundOff
  +0xbb: 1/2**(c-1), reduced), feet-inches, round-half-even when RoundUp (+0x9e) == 2.
  Derived from dimsrvcs; no corpus file uses them.
- **View sheets**: a drawing view's internal sheet is tied to its Drawing View by an association
  relation; dims there are reported on the view's working sheet (`viewSheet` keeps the raw one).
- **Multi-sheet**: every working sheet is exported, each dim with its own background's table.
- **Fail-soft**: damaged records yield partial entries (prefix: type, display, parents, value)
  or `unreadableRecord`; damaged styles/sheets/layers degrade to defaults with notes.
  Fault injection (random truncation of 7 object classes, 160 runs): no crash.
- Extra validation: the 90 drafts shipped with SE 2026 (templates, libraries, Training):
  1,106 styles and 47 dims byte-exact, ordinate origins "X1"/"Y1" match the sheet.

## 11. Vault drawings (2026-10-20)
Checked against the sheet picture of 9 production drawings (SE ST-era to 2026):
- **Rounding, RoundUp 2 (half-even)**: a near-tie is a tie. Inch sizes land on ties in mm and are
  stored with float noise on either side (19.05 as 19.04999999 or 19.05000000293); SE draws 19.0
  for both, 4.8 for 4.75, 19.0 for 18.95. The window here is 1e-6 of the last shown digit.
  **Half-up (RoundUp 1)** only nudges an exact tie by 1e-10: 325.49999999895 is drawn 325.
- **Display 8 (blank)**: the value is hidden. SE draws only the strings: superfix above,
  prefix + suffix, subfix below. Drafters type whole sizes there (`%DI 5.0 %PM0.1`), or a thread
  over a depth. A blank dimension with no strings draws only its lines.
- **Text codes** drawn as: `%DI` ⌀, `%PM` ±, `%DG` °, `%SQ` □, `%DP` ↧ (depth). `%TS` is the
  thread size, filled from the hole feature ("1/4-28 UNF"), not from the dimension.
- **Not printed**: a dimension owned by no sheet, or one dragged off the paper. The paper is the
  extent of the background sheet's Line objects (its border: A2 594x420, A3 420x297, to 0.5 mm).
  The reader reports `position` (mean of the sheet points, mm) and `printed`.
