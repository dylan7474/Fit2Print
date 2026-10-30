# Running Fit2Print in a container

    docker build -f docker/Dockerfile -t fit2print:0.1 -t fit2print:latest .
    docker/run.sh doctor
    docker/run.sh toolpath plate.3mf          # files in the current folder; they are mounted at /work

The image (2.6 GB) holds Debian 13, Python 3.13 in a venv (numpy, scipy, trimesh, pillow, fit2print), a **pinned OpenSCAD snapshot (2026.10.29)** and
the **pinned Bambu Studio command line (02.08.02.61)**, both unpacked from their AppImages and checksummed. Bambu Studio runs under `xvfb`
because it is a graphical program. It runs as an ordinary user, holds no secrets, and keeps your files outside: you mount a folder.
To run a Phonosphere check, mount its `cad/` and run the script there, for example:

    docker run --rm --memory 4g -v $PWD/cad:/cad --entrypoint sh fit2print -c "cd /cad && python3 check_assembly.py"

## First test on phobos (2026-10-30)
Debian 13, 4 cores, 8 GB (about 4 GB free), 86 GB disk free. Same numbers as the laptop on everything tried:

| Test | Laptop | Container on phobos |
|---|---|---|
| toolpath: lug_coupon_fixed / top_plates / lug_coupon_old | bridge 5.8 / 6.2 / 3.2 mm | 5.8 / 6.2 / 3.2 mm |
| OpenSCAD: back_lower_R volume | 177.01 cm3 | 177.01 cm3 (10 s with start-up) |
| Bambu Studio: slice lug_coupon_fixed (make_plate) | OK, 14 min, 8 g, bridge 5.8 mm | OK, 14 min, 8 g, bridge 5.8 mm (9 s) |
| check_assembly: the whole virtual build | ALL CLEAR, about 3 min | ALL CLEAR, 235 s |

## Things learned building it
* Debian's own OpenSCAD is too old for the Manifold engine, so a snapshot is used. Snapshots are removed from the server after a while: **keep the checksummed AppImage** if the build must be repeatable later.
* On phobos's network pipelined apt downloads failed with "400 Bad Request": the Dockerfile sets `Acquire::http::Pipeline-Depth 0`.
* `chmod -R a+rX` on the unpacked AppImages, or the ordinary user cannot run them.
* `doctor` now **runs** each program (`verify` in `deps.toml`) rather than only looking for it on the PATH: it had said "found" for a tool that could not run.
* The checksums are trust-on-first-use. Bambu Studio is AGPL and OpenSCAD GPL: fine to run privately; sharing the image carries source obligations.
