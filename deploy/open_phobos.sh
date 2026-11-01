#!/bin/sh
# Open the Fit2Print page that runs on phobos, in your browser, through a private ssh tunnel (nothing is exposed on the network).
# The laptop's own copy uses port 8750, so the tunnel uses 8751.
set -e
PORT=8751
if ! ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  ssh -o BatchMode=yes -f -N -L $PORT:127.0.0.1:8750 phobos
fi
URL="http://localhost:$PORT/"
echo "phobos page: $URL   (opening it in the browser)"
${BROWSER:-google-chrome-stable} "$URL" >/dev/null 2>&1 &
