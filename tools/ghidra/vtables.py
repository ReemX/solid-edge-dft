# usage: vtables.py <pe> <ClassName> [n]  — list vtables (per COL offset) of an MSVC x64 class
import sys, struct, pefile
pe = pefile.PE(sys.argv[1]); d = pe.__data__; base = pe.OPTIONAL_HEADER.ImageBase
off2rva = pe.get_rva_from_offset; rva2off = pe.get_offset_from_rva
name = (sys.argv[2] if sys.argv[2].startswith('.?') else '.?AV%s@@' % sys.argv[2]).encode(); n = int(sys.argv[3]) if len(sys.argv) > 3 else 40
i = d.find(name + b'\0'); td_rva = off2rva(i - 16)
text = [s for s in pe.sections if s.Characteristics & 0x20000000]
def is_code(va):
    r = va - base; return any(s.VirtualAddress <= r < s.VirtualAddress + s.Misc_VirtualSize for s in text)
p = -1
while True:
    p = d.find(struct.pack('<I', td_rva), p + 1)
    if p < 0: break
    col = p - 12
    sig, vboff, cdoff, tdr, chd, selfr = struct.unpack_from('<IIIIII', d, col)
    if sig != 1 or tdr != td_rva: continue
    col_va = base + off2rva(col)
    q = -1
    while True:
        q = d.find(struct.pack('<Q', col_va), q + 1)
        if q < 0: break
        vt = q + 8; ents = []
        for k in range(n):
            va, = struct.unpack_from('<Q', d, vt + 8 * k)
            if not is_code(va): break
            ents.append(va)
        print(f'vtable {hex(base+off2rva(vt))} (this-offset {vboff:#x}) {len(ents)} entries')
        for k, va in enumerate(ents): print(f'  [{k:3}] +{8*k:#05x} {va:#x}')
