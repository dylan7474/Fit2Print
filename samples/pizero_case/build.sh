#!/bin/sh
# Build the printable STLs from case.scad (run from this folder). The stl/ folder is not committed.
set -e
mkdir -p stl
for p in base lid_print; do openscad -q --backend=manifold -D "part=\"$p\"" -o stl/$p.stl case.scad; done
ls -la stl
