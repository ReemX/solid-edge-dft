"""Reduce a decompiled serializer to its reads and real conditions.

usage: reads.py file.c ADDR
Keeps: RAW/raw-vtable reads (as R(off,n)), helper calls, if/else/loops whose
condition is not just an error check on a result variable. Drops error blocks.
"""
import re
import subprocess
import sys

here = __import__("os").path.dirname(__import__("os").path.abspath(sys.argv[0]))
src = subprocess.run([sys.executable, f"{here}/fn.py", sys.argv[1], sys.argv[2], "100000"],
                     capture_output=True, text=True).stdout
src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)

# join statements split across lines
lines, buf = [], ""
for l in src.split("\n"):
    s = l.strip()
    if not s:
        continue
    buf = (buf + " " + s) if buf else s
    if buf.endswith((";", "{", "}")) or buf.startswith("//") or re.match(r"^\w+:$", buf):
        lines.append(buf)
        buf = ""

ERR = re.compile(r"^(if|else if) \((\(int\))?[ui]Var\d+ < 0\) \{$|^if \(-1 < (\(int\))?[ui]Var\d+\) \{$"
                 r"|^if \(\(-1 < (\(int\))?[ui]Var\d+\) && \(local_\w+(\[0\])? != \w+\)\) \{$"
                 r"|^if \(\(int\)[ui]Var\d+ < 0\) \{$|^if \(lVar\d+ < 0\) \{$|^if \(-1 < lVar\d+\) \{$")
out = []
depth = 0
skip_depth = None
for s in lines:
    opens, closes = s.count("{"), s.count("}")
    if skip_depth is not None:
        depth += opens - closes
        if depth <= skip_depth:
            skip_depth = None
            # "} else {" after an error block: keep the else body
            if s.startswith("}") and "else" in s and s.endswith("{"):
                depth += 0
                out.append("  " * depth + "(else-of-error)")
        continue
    if ERR.match(s):
        skip_depth = depth
        depth += opens - closes
        continue
    if re.search(r"HRerrEx|^local_\w+ = 0;$|^[ui]Var\d+ = [ui]Var\d+( & 0xffffffff)?;$|^return", s):
        depth += opens - closes
        continue
    s2 = re.sub(r"FUN_18000bee0\(param_\d,\(?(?:\w+ \*)?\)?(.+?),(\w+)\)", r"R(\1,\2)", s)
    s2 = re.sub(r"\(\*\*\(code \*\*\)\(\*plVar\d+ \+ 0x18\)\)\(plVar\d+,(.+?),(\w+)(,\w+)?\)", r"R(\1,\2)", s2)
    keep = re.search(r"R\(|FUN_18|::|^(if|else|while|do|for|switch|case|\}|\{)", s2)
    if keep and not re.search(r"\+ 0x20\)\)\(plVar", s2):
        out.append("  " * depth + s2)
    depth += opens - closes

text = "\n".join(out)
# drop empty "} else {" / lone braces noise
text = re.sub(r"\n\s*\}\s*(?=\n)", "", text)
print(text)
