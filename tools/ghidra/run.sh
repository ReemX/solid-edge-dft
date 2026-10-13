#!/bin/bash
# usage: run.sh <path to dll> [maxmem]
# Headless Ghidra import + analysis + DumpAll.java: writes out/<dll>.c (every function,
# each preceded by "//@@FUNC <addr> <name>") and out/<dll>.strings.txt (strings with xrefs).
# Needs GHIDRA_INSTALL_DIR (and a JDK 21 on PATH or JAVA_HOME).
set -e
here="$(cd "$(dirname "$0")" && pwd)"
dll="$1"; n="$(basename "$dll")"; export MAXMEM=${2:-2G}
work="${WORK:-$PWD}"
mkdir -p "$work/proj/$n" "$work/out"
"${ANALYZE:-$GHIDRA_INSTALL_DIR/support/analyzeHeadless}" "$work/proj/$n" "$n" -import "$dll" -overwrite \
  -scriptPath "$here" -postScript DumpAll.java "$work/out" < /dev/null > "$work/out/$n.log" 2>&1
echo "exit $? $n"
