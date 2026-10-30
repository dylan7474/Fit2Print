#!/bin/sh
# Run Fit2Print in the container against the current folder:   docker/run.sh toolpath plate.3mf
# Memory is capped so it cannot squeeze the other services on a shared server.
exec docker run --rm --memory "${F2P_MEM:-3g}" -v "$PWD":/work fit2print "$@"
