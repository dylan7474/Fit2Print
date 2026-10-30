# Running the front door on phobos (and reaching it from your phone)

## What runs where (2026-10-30)
* **Laptop:** the MASTER copy of every project (model, checks, records). `fit2print serve` can also run here for local use.
* **phobos:** a container `fit2print` (image `fit2print:0.3`) serving the page, **bound to 127.0.0.1:8750 only**, so the only way to it is something running on phobos itself (the Cloudflare tunnel connector). It holds a working copy of each project under `~/f2p_server/projects/`, the config under `~/f2p_server/config/` and the access token in `~/f2p_server/token` (mode 600).
* The printer panel is live (the container talks to the printer directly, read-only). The project data is as of the last `sync`.

## Daily use
    # on the laptop, whenever it is on: bring the phone's new log entries and photos home, push the latest state out
    fit2print sync ~/src/dylan7474/Phonosphere/cad phobos:f2p_server/projects/phonosphere
    fit2print sync ~/src/dylan7474/Fit2Print/samples/pizero_case phobos:f2p_server/projects/pizero
The laptop copy is the master: the server copy only ever ADDS log entries and photos, `sync` pulls those home first, then pushes (nothing on the server is deleted).
Projects started from the phone page are created on phobos in `projects/new/` and are not synced home yet (pull them with `rsync`; a proper import comes later).

## The first visit and the token
Open the page once as `https://YOUR-HOST/?t=TOKEN`; it sets a cookie (HttpOnly, SameSite=Strict) and the token is not needed again on that device.
Read it on phobos with `cat ~/f2p_server/token`. To change it: write a new one into that file and re-create the container (below).

## Re-creating the container
    cd ~/f2p_server && docker rm -f fit2print
    docker run -d --name fit2print --restart unless-stopped --memory 1g --cpus 1 -p 127.0.0.1:8750:8750 \
      -v $PWD/config:/config:ro -v $PWD/projects:/projects fit2print \
      serve --host 0.0.0.0 --port 8750 --config /config/config.toml --printer /config/printer.toml --token "$(cat token)"
To update the code: copy the Fit2Print folder to `~/f2p_build`, `docker build -f docker/Dockerfile -t fit2print:NEW -t fit2print:latest .`, then re-create as above.

## Remote access with a Cloudflare Zero Trust published application
1. **A tunnel on phobos.** In Zero Trust: Networks > Tunnels > create a tunnel, choose Docker, and run the connector it gives you on phobos with `--network host` so that the service address `http://localhost:8750` reaches the container's published port.
2. **A public hostname** for the tunnel, for example `fit2print.YOURDOMAIN`, with service type **HTTP** and URL `localhost:8750`.
3. **An Access application (self-hosted)** for that exact hostname, with a policy that **allows only you** (your email, with a one-time PIN or your identity provider) and a session length you are comfortable with. Do not add a Bypass or Everyone policy.
4. Keep the token as a second layer: open the first visit as `https://fit2print.YOURDOMAIN/?t=TOKEN` after you have signed in through Access.
5. Do not publish port 8750 any other way, and do not change `127.0.0.1:8750` to a network address.

## What is and is not protected
* The page can add print-log entries and photos to your projects and show the printer's camera. That is why it is behind both an Access login and a token, and why uploads are limited to real jpg/png images under 15 MB with server-chosen names.
* It never sends a command to the printer that moves, heats or stops anything.
* The printer's access code lives only in `config/printer.toml` (mode 600) and is never put in a page or a log.
* Not yet verified by us: the Cloudflare side. Check from your phone on mobile data that the page asks for your Access login before showing anything.
