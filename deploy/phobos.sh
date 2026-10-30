#!/bin/sh
# Update the Fit2Print front door on phobos from this laptop's source, then restart it. Usage: deploy/phobos.sh [--image]
#   --image  also rebuild the tools container (needed only when docker/Dockerfile, profiles or the templates the container uses changed)
set -e
cd "$(dirname "$0")/.."
tar cf - --exclude=.git --exclude='samples/*/stl' --exclude='samples/*/renders' . | ssh -o BatchMode=yes phobos 'tar xf - -C ~/f2p_app/Fit2Print'
if [ "$1" = "--image" ]; then
  ssh -o BatchMode=yes phobos 'rm -rf ~/f2p_build && mkdir ~/f2p_build && cp -r ~/f2p_app/Fit2Print/. ~/f2p_build/ && cd ~/f2p_build && docker build -q -f docker/Dockerfile -t fit2print:latest . >/dev/null && echo "tools image rebuilt"'
fi
ssh -o BatchMode=yes phobos 'systemctl --user restart fit2print && sleep 4 && systemctl --user is-active fit2print'
