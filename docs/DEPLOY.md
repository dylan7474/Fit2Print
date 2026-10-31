# Running the front door on phobos (and reaching it from your phone)

## What runs where (2026-10-31)
* **Laptop:** the MASTER copy of every project (model, checks, records). `fit2print serve` can also run here for local use.
* **phobos, the page:** a systemd *user* service `fit2print.service` (lingering is on, so it starts at boot) running `~/f2p_app/venv/bin/fit2print serve` on **port 8750 on all of phobos's addresses** (changed from localhost-only on 2026-10-31 at the owner's request, so any computer on the home network can use it). The token is required for every address except localhost. Source `~/f2p_app/Fit2Print` (installed editable), config `~/f2p_server/config/config-native.toml`, printer settings `~/f2p_server/config/printer.toml` (mode 600), token `~/f2p_server/token` (mode 600), project copies `~/f2p_server/projects/`.
* **phobos, the heavy tools:** the container image `fit2print` (OpenSCAD and Bambu Studio, pinned). The page never runs them directly: it calls two wrapper scripts in `~/f2p_server/bin/` that start the container for one job, mounting only the project's folder: `f2p` (any Fit2Print command) and `f2p-openscad` (drawing the pictures).
* **phobos, the assistant:** Claude Code (`~/.local/bin/claude`, already signed in) started by the page in the project's folder with a short allowlist of tools, one of which is the `f2p` wrapper. Nothing else can run.
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

## Using it from another computer on the home network
Open `http://192.168.50.2:8750/` (the token is in `~/f2p_server/token` on phobos: `cat` it); a cookie remembers the device after that. From the laptop, `deploy/open_phobos.sh` does the same through an ssh tunnel.
* It is plain **http** on your own network, so the token travels unencrypted on that wifi/cable: fine at home, not for anywhere untrusted. (Behind the Cloudflare tunnel it is https.)
* Do **not** forward port 8750 on the router. The page can add entries to your projects, drive the assistant (which costs money to run) and show the printer's camera; the token is what protects it.
* phobos's address is `192.168.50.2` today; it is worth giving it a fixed address in the router (a DHCP reservation) so the bookmark keeps working.
* The Cloudflare tunnel connector still reaches it as `http://localhost:8750`.

## Optional: no token on the home network (`--trust-lan`)
`fit2print serve --trust-lan` lets a device on the home network (a private address) in without the token, like unprotected apps on the same network. A request that came through a proxy such as the Cloudflare tunnel carries proxy headers (Cf-Ray, X-Forwarded-For ...) and reaches us from this machine, so it is NEVER treated as the home network and still needs the token. It is off by default; **on phobos it is ON (the owner asked for no token at home, 2026-10-31)**. To turn it off, remove `--trust-lan` from the `ExecStart` line of `~/.config/systemd/user/fit2print.service`, then `systemctl --user daemon-reload && systemctl --user restart fit2print`. Anything on the home network (a guest's phone, a smart TV) could then use the page.

## The first visit and the token
Open the page once as `https://YOUR-HOST/?t=TOKEN`; it sets a cookie (HttpOnly, SameSite=Strict) and the token is not needed again on that device.
Read it on phobos with `cat ~/f2p_server/token`. To change it: write a new one into that file and restart the service.

## Updating, restarting, looking at it
    deploy/phobos.sh            # from the laptop: copy the source to phobos and restart the page  (add --image to rebuild the tools container too)
    ssh phobos 'systemctl --user status fit2print'      # is it running
    ssh phobos 'journalctl --user -u fit2print -n 50 --no-pager'     # what it said
    ssh phobos 'systemctl --user restart fit2print'
The old all-in-one container for the page was retired on 2026-10-31 (it could not run Claude or OpenSCAD); the `fit2print` image remains for the tools.

## Remote access with a Cloudflare Zero Trust published application (no token needed)
The page needs no token on the internet path either. Cloudflare Access signs a login proof onto every request it lets through, and the page checks that signature against your team's public keys, so it only accepts a request that really passed YOUR Access login. If the Access application is ever missing or misconfigured, the proof is absent and the page refuses (it does not rely on Cloudflare's settings being right).
1. **A tunnel on phobos.** Zero Trust > Networks > Tunnels > create a tunnel, choose Docker, run the connector it gives you on phobos with `--network host`, so that `http://localhost:8750` reaches the page.
2. **A public hostname** for the tunnel, for example `fit2print.YOURDOMAIN`: service type **HTTP**, URL `localhost:8750`.
3. **An Access application (self-hosted)** for that exact hostname, with a policy that **allows only your email** (your Cloudflare one-time PIN or identity provider). No Bypass, no Everyone.
4. **Tell the page about it**: add to `~/f2p_server/config/config-native.toml` on phobos
       [access]
       team_domain = "YOURTEAM"          # the part before .cloudflareaccess.com (Zero Trust > Settings)
       aud = "THE-APPLICATION-AUD-TAG"   # Access > Applications > your app > Overview > Application Audience (AUD) Tag
       allowed_emails = ["you@example.com"]     # optional second check
   then `systemctl --user restart fit2print`. Until this is set, requests through the tunnel are REFUSED (the safe default).
5. Do not forward port 8750 on the router, and do not add another way in.

## What is and is not protected
* The home network (private addresses, no proxy marks) is trusted and needs nothing, like your other apps. Anything on that network can add print-log entries, start the assistant (which costs money) and see the printer's camera.
* Through the tunnel, only a request carrying a valid Cloudflare Access proof for your team, your application, unexpired and (if you set it) for your email.
* A public address reaching the page directly (for example a router port forward) is refused.
* The page never sends a command to the printer that moves, heats or stops anything. The printer's access code lives only in `config/printer.toml` (mode 600) and is never put in a page or a log.
* The old shared token still exists as an option (`--token`/`--token-file`) but phobos no longer uses one.
