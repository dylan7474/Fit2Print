# Running the front door on phobos (and reaching it from your phone)

## What runs where (2026-10-31)
* **Laptop:** the MASTER copy of every project (model, checks, records). `fit2print serve` can also run here for local use.
* **phobos, the page:** a systemd *user* service `fit2print.service` (lingering is on, so it starts at boot) running `~/f2p_app/venv/bin/fit2print serve` on **port 8750 on all of phobos's addresses** (changed from localhost-only on 2026-10-31 at the owner's request, so any computer on the home network can use it). Source `~/f2p_app/Fit2Print` (installed editable), config `~/f2p_server/config/config-native.toml`, printer settings `~/f2p_server/config/printer.toml` (mode 600), project copies `~/f2p_server/projects/`.
* **phobos, the heavy tools:** the container image `fit2print` (OpenSCAD and Bambu Studio, pinned). The page never runs them directly: it calls two wrapper scripts in `~/f2p_server/bin/` that start the container for one job, mounting only the project's folder: `f2p` (any Fit2Print command) and `f2p-openscad` (drawing the pictures).
* **phobos, the assistant:** Claude Code (`~/.local/bin/claude`, already signed in) started by the page in the project's folder with a short allowlist of tools: read, search, write and edit in the project, **WebFetch and WebSearch** (plain HTTP lookups for datasheets and dimensions, no browser needed; added 2026-10-31), and the `f2p` wrapper. Nothing else can run. Web pages count as untrusted data.
* The printer panel is live; the project data is as of the last `sync`.

## Daily use: one command keeps both sides in step
    fit2print sync-all --remote phobos:f2p_server/projects          # --dry-run to look first
It syncs every project the laptop knows (its config) and brings home any project that was started on the phone page. Everything on the server lives in `~/f2p_server/projects/<project id>/`.
What happens to each kind of file (it never overwrites work):
* **Logs** (print log, check records, the assistant's conversation): merged both ways; each side gains the lines it lacks.
* **Every file of an ordinary project** (brief.md, NEXT.md, fit2print.toml, model.scad, concept sketches, assembly.toml...; the radio is handled separately): both sides can edit them, so each is tracked by what it was at the last sync: if only one side changed since the last sync, that change goes to the other side. If **both** changed, nothing is overwritten: the server's version is saved next to yours as `NEXT.md.from-server-DATE`, the sync reports `CONFLICT`, and you merge them by hand, or settle it with `--prefer local` or `--prefer server`.
* **Photos:** copied both ways, never overwriting.
* **The laptop's own files** (the marker, the model, the check records): copied to the server.
Single project: `fit2print sync PROJECT phobos:f2p_server/projects/<id>`. The laptop copy is the master; run this whenever the laptop is on, the page on phobos keeps working in between.

## Reaching it
It is JUST a website: it has no login, no token and no idea what is in front of it. Open `http://192.168.50.2:8750/` from any computer on the home network; from the laptop, `deploy/open_phobos.sh` does the same through an ssh tunnel. A tunnel (Cloudflare or anything else) points at `http://localhost:8750` like for any other app on phobos, and whatever access control you want is set up on that side, not here.
* phobos's address is `192.168.50.2` today; it is worth giving it a fixed address in the router (a DHCP reservation) so the bookmark keeps working.
* Whoever can reach the page can add print-log entries, start the assistant (which costs money to run and can write inside the project folders) and see the printer's camera. Decide who can reach it accordingly (do not forward port 8750 on the router).
* The page never sends a command to the printer that moves, heats or stops anything. The printer's access code lives only in `config/printer.toml` (mode 600) and is never put in a page or a log.

## Updating, restarting, looking at it
    deploy/phobos.sh            # from the laptop: copy the source to phobos and restart the page  (add --image to rebuild the tools container too)
    ssh phobos 'systemctl --user status fit2print'      # is it running
    ssh phobos 'journalctl --user -u fit2print -n 50 --no-pager'     # what it said
    ssh phobos 'systemctl --user restart fit2print'
The old all-in-one container for the page was retired on 2026-10-31 (it could not run Claude or OpenSCAD); the `fit2print` image remains for the tools.
