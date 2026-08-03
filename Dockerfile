FROM debian:bookworm-slim

# Seafile discontinued its APT repository; linux-clients.seafile.com no longer
# resolves to a reachable host. Upstream now ships the CLI as an AppImage.
ARG SEAFILE_CLI_VERSION=9.0.19
ARG SEAFILE_CLI_SHA256=4af848362d8493be218b903e17e3fbbd282e9ea94af000211ce05c3f44e48715
ARG SEAFILE_CLI_URL=https://sos-ch-dk-2.exo.io/seafile-downloads/Seafile-cli-x86_64-${SEAFILE_CLI_VERSION}.AppImage

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl binutils squashfs-tools python3.11-venv && \
    rm -rf /var/lib/apt/lists/*

# An AppImage is an ELF runtime with a squashfs image appended. Unpack the
# squashfs directly rather than executing the AppImage: running it needs FUSE,
# and so a privileged container. Verify the download before unpacking it.
RUN curl -fsSL -o /tmp/seaf-cli.AppImage "$SEAFILE_CLI_URL" && \
    echo "${SEAFILE_CLI_SHA256}  /tmp/seaf-cli.AppImage" | sha256sum -c - && \
    offset=$(LC_ALL=C readelf -h /tmp/seaf-cli.AppImage | awk '\
        /Start of section headers/ {s=$5} \
        /Size of section headers/  {z=$5} \
        /Number of section headers/{n=$5} \
        END {print s + z * n}') && \
    unsquashfs -q -d /opt/seafile-cli -o "$offset" /tmp/seaf-cli.AppImage && \
    rm /tmp/seaf-cli.AppImage

# The bundled AppRun expects APPDIR, which only the AppImage runtime sets.
# seaf-cli also requires seaf-daemon on PATH, so keep usr/bin ahead of it.
RUN printf '%s\n' \
        '#!/bin/sh' \
        'APPDIR=/opt/seafile-cli' \
        'export PATH="$APPDIR/usr/bin${PATH:+:$PATH}"' \
        'export LD_LIBRARY_PATH="$APPDIR/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"' \
        'export PYTHONPATH="$APPDIR/usr/lib/python3.9/site-packages${PYTHONPATH:+:$PYTHONPATH}"' \
        'exec python3 "$APPDIR/usr/bin/seaf-cli" "$@"' \
        > /usr/local/bin/seaf-cli && \
    chmod +x /usr/local/bin/seaf-cli

# Use virtual environment
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv --system-site-packages $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# The APT package used to install the seafile/pysearpc RPC bindings system-wide.
# The AppImage keeps them in its own tree, so put them on the venv path: dsc
# imports seafile directly, not only through seaf-cli. They are pure Python, so
# the 3.9 build works unchanged on this interpreter.
RUN python3 -c "import pathlib, site; \
    pathlib.Path(site.getsitepackages()[0], 'seafile-appimage.pth') \
        .write_text('/opt/seafile-cli/usr/lib/python3.9/site-packages\n')"

# Install app requirements
WORKDIR /dsc
COPY requirements.txt ./
# venv creation bootstraps its own setuptools via ensurepip, which
# requirements.txt does not cover. 66.1.1 carries CVE-2024-6345 and
# CVE-2025-47273; 78.1.1 fixes both.
RUN pip install --no-cache-dir --upgrade "setuptools>=78.1.1" && \
    pip install --no-cache-dir -r requirements.txt

# Copy app
COPY dsc ./dsc/
COPY start.py ./start.py
COPY healthcheck.py ./healthcheck.py

# Create seafile user and init seafile client
RUN chmod +x /dsc/start.py /dsc/healthcheck.py && \
    useradd -U -d /dsc -s /bin/bash seafile && \
    usermod -G users seafile && \
    mkdir -p /dsc/seafile-data && \
    chown seafile:seafile -R /dsc

# Smoke checks: seaf-cli has no --version flag, so assert its subcommands, and
# confirm the app's own imports resolve.
RUN seaf-cli --help | grep -q 'download-by-name' && \
    seaf-cli sync --help | grep -q '\--token' && \
    seaf-cli list --help | grep -q '\--json' && \
    python3 -c "import seafile, pysearpc, dsc.client, dsc.misc, healthcheck"

# Record the pinned client version in the image so it can be checked at
# runtime; seaf-cli itself has no --version flag.
ENV SEAFILE_CLI_VERSION=${SEAFILE_CLI_VERSION}

VOLUME /dsc/seafile-data

# The container's own process already runs as the seafile user (see
# dsc.misc.drop_privileges), but a HEALTHCHECK is a fresh process started by
# the Docker daemon, which starts it as root. runuser drops it to the same
# unprivileged user before it ever touches the RPC socket.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD runuser -u seafile -- python3 /dsc/healthcheck.py

CMD ["./start.py"]
