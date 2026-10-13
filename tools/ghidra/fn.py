import sys,re
# usage: fn.py file.c ADDR_OR_NAME [maxlines]
src=open(sys.argv[1],encoding='utf-8',errors='replace').read()
parts=src.split('//@@FUNC ')
key=sys.argv[2].lower().replace('fun_','')
for p in parts[1:]:
    head=p.split('\n',1)[0].lower()
    if key in head:
        lines=p.split('\n'); print('//@@FUNC '+'\n'.join(lines[:int(sys.argv[3]) if len(sys.argv)>3 else 400])); break
