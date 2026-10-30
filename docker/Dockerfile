# Fit2Print toolkit image: Python checks + a pinned OpenSCAD snapshot + a pinned Bambu Studio command line.
# Build from the repo root:  docker build -f docker/Dockerfile -t fit2print .
# Both outside tools are AppImages unpacked at build time (no FUSE needed) and called through their command lines only.
# Checksums are trust-on-first-use (recorded 2026-10-30 from the vendors' own download URLs).
FROM debian:trixie-slim AS tools
ARG DEBIAN_FRONTEND=noninteractive
RUN printf 'Acquire::Retries "5";\nAcquire::http::Pipeline-Depth "0";\n' > /etc/apt/apt.conf.d/80net \
 && apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
ARG OPENSCAD_URL=https://files.openscad.org/snapshots/OpenSCAD-2026.10.29-x86_64.AppImage
ARG OPENSCAD_SHA256=20c48bc9bf5300016327e3364bf9b501809f0017d280d9db8df8cde07bc3445c
ARG BAMBU_URL=https://github.com/bambulab/BambuStudio/releases/download/v02.08.02.61/BambuStudio_ubuntu24.04-v02.08.02.61-20260820225108.AppImage
ARG BAMBU_SHA256=d501b103fac5424513ec0e8d6bc145fb30719de2c7d94d7320d723740c81a7fd
WORKDIR /dl
RUN curl -fsSL -o openscad.AppImage "$OPENSCAD_URL" && echo "$OPENSCAD_SHA256  openscad.AppImage" | sha256sum -c - \
 && curl -fsSL -o bambu.AppImage "$BAMBU_URL" && echo "$BAMBU_SHA256  bambu.AppImage" | sha256sum -c - \
 && chmod +x *.AppImage \
 && ./openscad.AppImage --appimage-extract >/dev/null && mv squashfs-root /opt-openscad \
 && ./bambu.AppImage --appimage-extract >/dev/null && mv squashfs-root /opt-bambu \
 && rm -f *.AppImage

RUN chmod -R a+rX /opt-openscad /opt-bambu

FROM debian:trixie-slim
ARG DEBIAN_FRONTEND=noninteractive
# xvfb: Bambu Studio is a graphical program and wants a display even when it only slices. The libraries are what its AppImage expects from the system.
# (Pipeline-Depth 0: on phobos's network pipelined apt downloads got "400 Bad Request" from the CDN.)
RUN printf 'Acquire::Retries "5";\nAcquire::http::Pipeline-Depth "0";\n' > /etc/apt/apt.conf.d/80net \
 && apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip ca-certificates xvfb xauth \
      libgl1 libglu1-mesa libegl1 libgtk-3-0t64 libwebkit2gtk-4.1-0 libsecret-1-0 libdbus-1-3 libxkbcommon0 libfontconfig1 fonts-dejavu-core \
      libnotify4 libsm6 libxtst6 libxss1 libasound2t64 libgstreamer-plugins-base1.0-0 libcurl4t64 libx11-xcb1 libxcb-glx0 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=tools /opt-openscad /opt/openscad
COPY --from=tools /opt-bambu /opt/bambu
RUN printf '#!/bin/sh\nexec /opt/openscad/AppRun "$@"\n' > /usr/local/bin/openscad \
 && printf '#!/bin/sh\nexec xvfb-run -a /opt/bambu/AppRun "$@"\n' > /usr/local/bin/bambu-studio \
 && chmod +x /usr/local/bin/openscad /usr/local/bin/bambu-studio
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir numpy scipy trimesh pillow
COPY pyproject.toml deps.toml README.md /src/
COPY src /src/src
COPY profiles /src/profiles
COPY templates /src/templates
RUN /opt/venv/bin/pip install --no-cache-dir /src && cp -r /src/deps.toml /src/profiles /src/templates /opt/
ENV PATH=/opt/venv/bin:$PATH HOME=/tmp FIT2PRINT_HOME=/opt
RUN useradd -m -u 1000 f2p
USER f2p
WORKDIR /work
ENTRYPOINT ["fit2print"]
CMD ["doctor"]
