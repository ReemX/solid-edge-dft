# Research log: Solid Edge binary RE (2026-10-13)

Working notes, kept close to how they were written. FORMAT.md is the cleaned-up spec.

Tooling: Ghidra 12.1.4, JDK 21. `tools/ghidra/run.sh <dll> [mem]` = headless import + DumpAll.java
-> out/<dll>.c (all funcs, `//@@FUNC addr name`) and out/<dll>.strings.txt.
`tools/ghidra/fn.py out/X.c ADDR` prints one function; `reads.py` reduces a serializer to its reads;
`vtables.py X.dll '.?AU...@@'` lists vtables from RTTI. Per-query MCP decompilation was too slow for
the big DLLs, so everything was bulk-dumped once and grepped.

## Where things live
- Class -> DLL map is IN THE FILE (PSMtypetable stream). CLSID_JDim, JDimParameters, JDimGroup -> ANNOT.DEX.
- JDim COM object = JDimCOMObject (Annot.DEX), ctor FUN_180102110. Data struct at COM+0x138.
  IJPersistImp vtable 0x1806cd558; Load/Save -> JDim::Convert FUN_18035a290 / JDim::Serialize FUN_18035d0f0.
- Source file DIMPERST.CPP. JDim versions 1..0x27 (39); serializeN calls N-1 first then appends.
  Archive struct: +8 stream (vt+0x18 Read(buf,n,&got), vt+0x20 Write), +0x10 flags (bit0 save, bit1 load, bit3 ?).
  FUN_18000bee0(ar, ptr, n) = raw n-byte field.
- JDimParameters::persist_serialize1..44 (Annot.DEX 0x18012f730..0x180138f70), JDimOverrideFlags::Serialize 18012b320.
- Automation vocabulary (from the interop assemblies), enums: DimDispType 1 nominal,2 tol,3 classfit,4 limits,5 basic,6 ref,8 blank,9..14 fits,15 unit tol;
  DimAxisMode 1 default,2 implied,3 explicit,4 coordinate (= aligned/horizontal/vertical setting).
- JDim+9 (record byte) == DisplayType (confirmed by enum).
- Export path: iedraft.dll IEDIM.CPP ACADExportDimension FUN_180029730 -> dimsrvcs HGetDimAssocInfo/HGetDimGeometryInfo.

## JDim serialize3N4 (FUN_180364d40) order
FUN_18035a910(ver,ar,this,this+0x1938) header
FUN_180453a90(this+0xd0, ar, &x)        embedded params block
raw +0x100 (4), +0x108 (4), +0x18f8 (8)
FUN_18035bc60(ver,ar,this,this+0x138)   geometry
FUN_18035c810(ver,ar,this+0x138,this+0x1a48 ...)
FUN_18035ba20(ver,ar,...)
Oracle: parser must end exactly at record end for every corpus JDim.

## JDim modern layout (versions >= 0x11), transcribed from Annot.DEX
Version per file: DocVersion2 stream (u16 minor, u16 major; e2=226 -> "226.02") + DRAFT.VER
(Program\DRAFT.VER: per class GUID, lines "objver appver"; pick newest objver with appver <= file).
JDim GUID {1D1928C0-0000-0000-C000-000000000046}: 39@223.10, 38@222.06, 37@109.16 ...
serialize5 (base, FUN_1803656f0):
  1 AttributeBundle FUN_18035a910 (record +8.. = bundle byte0)
     u8 type(+0), u8 disptype(+1), u8 (+2), u16 (+4), u16 (+6), u32 flags8 (+8),
     u32 +14,+18,+1c,+20,+24,+28,+2c ; f64 +30 ; f64 +58 ; [v>4] f64 +60 ; f64 +68
     [v>7] f32 extra ; [v>8] u32 +70 ; u8 +74 ; [v>10] u32 flagsC (+0c)
     type 8|0xb: [v>0xd] u16 n76, n*(u32,u32,u32) ; then [v>0x11] f64 +90
     type in {1,3,5,6,7,9} and v>0x1d: u16 n76; if n: u32 +38,u32 +3c,f64 +40, n*12B ;
                                    u16 n78; if n: u32 +48,u32 +4c,f64 +50, n*12B ; f64 +90
     other types: [v>0x11] f64 +90
     [v>0x12] u32 +10 ; [v>=0x15] f64 +98 ; [v>=0x21] f64 +a0 ; [v>=0x22] f64 +a8 ; [v>=0x23] u32 +b0 ; [v>=0x25] f64 +b8
  2 params block @+0xd0: v<0xf FUN_180453a90, v<0x11 FUN_180454020, else FUN_1804545b0   (TODO)
  3 f64 +18e8, u32 +100, u32 +108, f64 +18f8
  4 geometry FUN_18035bc60: u32 n; per pt: u32 kind, 4xf64, [v>0xf && flagsC&0x20000004] 2xf64,
     [v>0x15 && flagsC&0x8000000] 6xf64, then geomtag FUN_18035d1f0:
     u8 tag: 'g' 6xf64 | 's' 5xf64+u8 | 't' 5xf64+u8+2xf64 | 0x8c 2xf64 |
             0x7f bspline: u8,u32 np,u32 rat,u8,u8,u32 nk,f64,u8, np*16, rat?np*8, nk*8 | 'x' bspline + 7xf64 | else none
  5 text FUN_18035ca60: 7 slot strings (slots 1..7) + 4 strings (+1a48,+1a50,+1a58,+1a60)
     string = u32 nchars (incl NUL, 0=empty) + nchars*2 UTF-16
  6 [v<0x18] range FUN_18035ba20: [v<0x24] u8 f else u32 f; f&3: f64; f&0xc: f64
 v6: type in {1,8,9,11}: f64 +1928, f64 +1930     v7/8: u32 +18e0     v9: string slot 0xc
 v10/11: f64 +1a90, u32 +1910    v12: f64 +1900    v13-15: string slot 0xd
 v17: [v<0x18 && flagsC&0x80000] GUserText::Serialize   v19: u8 +c8, u8 +c9   v20/21: string +1a68
 v22: u8 m; m&1: f64 +1ae0    v23: u32 n, n*u32    v24: aggregated obj serialize (outer QI IID@1806bccc0) ??
 v25: flagsC&0x20000000: u32 +1b04   v26: u32 +104   v27: f64 +18f0   v28: string slots 0x12,0x13
 v29/30: flags8&0x200: u32 +1b08   v31: string slot 0x14   v32/33: f64 +1b18,+1b20   v34: string slot 0x4a
 v35-37: none   v38: flagsC&0x8000000: u32 n, n*u32   v39: same again

## Status 2026-10-13 ~02:00
- sedft/jdim.py: JDim v39 reader — 499/499 corpus dims parse byte-exact (35 files, SE2023 + SE2026).
- psm.py patched: Store.starts (all headers incl. unknown classes) + Store.body(off). Fixed 2 boundary misses.
- v24 aggregated child = JDoubleValue (EXPRDEX.DLL, JDBLVAL.CPP) v4: f64 value,u16,u16 flags;
  flags&0x10 limits{u32 lf; lf&3 low; lf&0xc high; lf&0x10 discrete u32 n + n f64; ...};
  flags&0x1000/0x2000/0x4000/0x400 GUserText (JUTIL2) ; nested 8 bytes (02 00 00 00 00 00 00 00 const, class TBD)
- Semantics found: +0x18f8 = dimension value (m/rad); v32/33 +0x1b18/+0x1b20 = upper/lower tolerance;
  parents[].ref = oid of dimensioned element (Line Object / JCircle2d / JArc2d), parents[].u70 keypoint (1 start,2 end,4 center),
  guid_idx = element interface (45 line, 43 circle, 51 arc); geometry tags g=line s=circle t=arc.
  +0x18e0 = StyleID (HGetStyleInterface, stylspt.dll). 0x80000074 = family default?; small ints index StyleManager usage table
  (StyleManager object: 16B entries u32 idx,u32 oid,u32 refcount,u32 family; 0x80000074 = dim style family).
  JDimParameters = DIMENSION STYLE (DIMSTYL.CPP), not per-dim.  Class-0x15 objects = layers/collections (name + oid list).
- sedft/dimparams.py + dimparams_table.py (generated): JDimParameters v4 base + 5..44, chain linear except v8->v6.
  529/529 corpus records byte-exact (v44, one SE 2023 file v43). Font name @0x1c8 ("Solid Edge ISO"), text height @0x198 (0.0035).
- StyleManager body: u32 nNamed, u32 maxID, entries {u32 id, u32 oid, u32 b, u32 parentID, GUserText name, u32, u16,u16,u16};
  then unnamed table u32 n, u32 max, entries {u32 id, u32 oid, u32 refcount, u32 parent named id}.
  JDim StyleID: 0x8000000|n = named style n ("ISO (mm)" = 0x74 in Draft1); positive = unnamed/override style.
- GUserText = u32 nchars (no NUL) + UTF-16.  SerializeString/wstr = u32 n (incl NUL) + UTF-16.
- extra public sample files: SE v15.21 (JDim v18), v19.16, ST5 105.20 (v33), ST7 107.x (v34), 226.02. All byte-exact:
  JDim 732/732, JDimParameters 626/626 across 41 files. Old class name "JDim Object" (v15) = CLSID_JDim.
- JDoubleValue has own version (GUID {D97A3FB0-1601-11CE-B7EE-08003601E53B}; v4@110.10, v3@109.08, v2@109.06, v1):
  v1/v2 limits flags u8, v3+ u32; v2 lf&0x20/0x40 u32s; v3 lf&0x100 list; v4 nested 8B. Order = v1 whole, then v2,v3,v4.
- Naming: FwkSupp automation getters log own names "CDDimStyle::IDimStyleAutoImp::get_X" and call internal IID
  {6A6EC051-011E-4DE8-9FCC-1F3F2B6CA64D} slot -> served by HDimStyle (HANNOT.DAX) helper. (name -> slot table).
- NAMING DONE (sedft/dimstyle_names.py: 164/180 DimStyle props -> JDimParameters member offset; struct = JDimParameters+0x90,
  HANNOT HDimStyle dispatcher FUN_1800c6e80). e.g. PrimaryUnits +0xb8, RoundOffType +0x9a, PrimaryDecimalRoundOff +0xba,
  Delimiter +0x9d, LeadingZeros +0xbc, TrailingZeros +0xbd, AngularUnits +0x188, AngularDecimalRoundOff +0x18a,
  Height +0x198, Font +0x1c8, TextOrientation +0x2c9, LimitTextArrangement +0x2cb, DimensionScale +0x678,
  PrimaryLinearToleranceDecimalRoundOff +0x122.
- Dimension props -> JDim text slot or attribute-bundle expression (HANNOT HDIM.CPP FUN_180010fb0).
  Text slots: 1..7 = ids 0x1b..0x21, 4 PrimaryToleranceSymbol, 5/6 SecondaryUpper/Lower, 8 Prefix, 9 Suffix,
  10 Superfix, 11 Subfix, 13 OverrideChamferAngle, 14-17 Prefix/Suffix/Superfix/Subfix DisplayedText, 18 HoleClass,
  19 ShaftClass, 58 SubfixString2, 59 Subfix2Displayed. Bundle: +2 BreakPosition, +4 w4 (MeasurementAxisEx:
  w4&2 -> explicit?, w4&1 -> implied(2), else default 1), w4 bit2 MeasurementAxisDirection, +0x14 BreakDistance,
  +0x18 TrackDistance, +0x1c TrackAngle(type5), +0x20 LeaderDistance; flags8: &1 Constraint(driving) &2 ZOrder? &0x40 DisplayByName
  &0x2000 Inspection &0x10 HidePMI.

## Semantic layer (sedft/semantic.py) — validated 2026-10-13
- Value = JDim +0x18f8 adjusted per GetValue (Annot FUN_1804242d0): only when flags8&3 && !(flagsC&0x2000):
  diameter types {4,5,9} x2 (2D sketch dims store radius; view dims store diameter); angular complement rules on w4 bits 3..6;
  arc length = angle * arc radius (geometry 't' radius). Status +0x1910 (0/3/4 ok).
- Text = sprintf("%.*lf", code-2, v+eps), delimiter swap (+0x9d: 1 '.', 2 ',', 3 ' '), zero suppression
  (JDimSupressDigit: lead flag 0 strips leading '0', trail flag 0 strips trailing zeros + dangling sep); codes 1/2 = round to 10/1.
- Tolerance: +0x1b18 upper, +0x1b20 lower magnitude (m); slots 2/3 = SE tolerance strings ("0.100 mm").
- Kind: linear dims axis vector +0x1928/+0x1930 (v6, types 1,8,9,11): slanted -> aligned, H/V -> linear (= rule B).
  SE DXF aligned/rotated labels do NOT follow MeasurementAxisEx (exporter quirk).
- Sheets: JSheet body starts with MasterGroup member list: u32 ids (z-order) terminated by 0, FFFFFFFF a b = range a..b.
  732/732 dims on exactly one sheet; sheet name = first UTF-16 string after list. Layers: JLayerManager (u32 active,
  u32 n, oids); layer = GUserText name, u32 flags, u32 cnt, oids. Per-sheet JLayerSettings (lyrmgr): u32 n, n*(u32 layer, u8 hidden).
- Validation: computed text literally on the sheet image for 716/716 verifiable dims (705 exact + 11 split runs);
  10 correctly hidden (Training PerimDims); others are on sheets without a snapshot. Old EMF matcher was wrong on ~30.
- Not implemented at this point: DMS angles, fractional inches (added later, see FORMAT.md §10), JDim params block for v<0x11 (pre-SE v15).

## SE-rendered checks 2026-10-13 (byte-patched copies of a test sheet + edits in the SE UI)
- A_dms, B_frac, C_dec (5 decimals, zero suppression), D_ftin: reader text = SE rendering.
- se_E_gui: class fit "60 D9" OK; alpha tolerance was WRONG (numeric 0/0) -> fixed (strings carry it);
  chamfer "27,17 X 45°" OK after computing the angle from parent Line Objects.
- Open: non-45 chamfer complement, ChamferUse45DegreeCharacter, real vault drawings.
