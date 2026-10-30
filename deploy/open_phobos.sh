#!/bin/sh
# Open the Fit2Print page that runs on phobos, in your browser, through a private ssh tunnel (nothing is exposed on the network).
# The laptop's own copy uses port 8750, so the tunnel uses 8751.
set -e
PORT=8751
if ! ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  ssh -o BatchMode=yes -f -N -L $PORT:127.0.0.1:8750 phobos
fi
T=$(ssh -o BatchMode=yes phobos 'cat ~/f2p_server/token')
URL="http://localhost:$PORT/?t=$T"
echo "phobos page: http://localhost:$PORT/   (opening it in the browser; the token is in the link so you are signed in)"
${BROWSER:-google-chrome-stable} "$URL" >/dev/null 2>&1 &
