#!/usr/bin/env bash
#
# Container smoke test: exercises the built image, not the source tree.
#
# Everything here needs the real seaf-cli and seaf-daemon from the image, so
# it cannot run in the unit test job. Usage:
#
#     tests/smoke.sh [image]            # native architecture
#     PLATFORM=linux/amd64 tests/smoke.sh   # the AppImage is x86_64 only
#
set -uo pipefail

IMAGE="${1:-snegov/seafile-client:ci}"
PLATFORM_ARG=""
[ -n "${PLATFORM:-}" ] && PLATFORM_ARG="--platform ${PLATFORM}"

WORK=$(mktemp -d "${PWD}/.smoke-XXXXXX")
trap 'rm -rf "$WORK"; docker rm -f dsc-smoke >/dev/null 2>&1 || true' EXIT

failures=0

pass() { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; failures=$((failures + 1)); }

check() {  # check <description> <expected> <actual>
    if [ "$2" = "$3" ]; then pass "$1"; else
        fail "$1"; printf '        expected %s, got %s\n' "$2" "$3"
    fi
}

run() { docker run --rm $PLATFORM_ARG "$@"; }

echo "== imports and pinned client version"
# The exit status matters as much as the output: a traceback also prints a
# non-empty last line, and must not be mistaken for a version.
if out=$(run "$IMAGE" python3 -c "
import os, seafile, pysearpc, dsc.client, dsc.misc, dsc.paths, dsc.secrets, dsc.config
print('VERSION', os.environ['SEAFILE_CLI_VERSION'])" 2>&1); then
    version=$(printf '%s\n' "$out" | sed -n 's/^VERSION //p')
    case "$version" in
        [0-9]*.[0-9]*) pass "imports resolve, seafile client version is $version" ;;
        *) fail "no usable version reported, output was: $out" ;;
    esac
else
    fail "imports or SEAFILE_CLI_VERSION failed: $out"
fi

echo "== the real daemon starts, reports ready, and stops"
out=$(run "$IMAGE" python3 -c "
from dsc.client import SeafileClient
c = SeafileClient('example.invalid', 'u', 'pw', '/dsc', token='tok')
c.init_config()
c.start_daemon()
ready = c.daemon_ready
c.stop_daemon()
print('READY', ready, 'STOPPED', not c.daemon_ready)" 2>&1 | tail -1)
check "daemon lifecycle" "READY True STOPPED True" "$out"

echo "== docker stop shuts the daemon down gracefully"
docker rm -f dsc-smoke >/dev/null 2>&1 || true
docker run -d $PLATFORM_ARG --name dsc-smoke "$IMAGE" python3 -c "
import argparse, logging, time
import start
logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
from dsc.client import SeafileClient

def watch():
    print('WATCHING', flush=True)
    while True:
        time.sleep(0.2)

c = SeafileClient('example.invalid', 'u', 'pw', '/dsc', token='tok')
# The daemon is real; the server is not. Nothing here may reach the network,
# so library lookup is stubbed and only the lifecycle is exercised.
c.watch_status = watch
c.get_library_id = lambda name: None
c.get_local_libraries = lambda: set()

start.install_signal_handlers()
raise SystemExit(
    start.run(c, argparse.Namespace(libraries='none', server='s'), '/dsc/seafile')
)
" >/dev/null

# Wait for the daemon to be up and the process to be in its watch loop. If it
# never gets there the shutdown assertions mean nothing, so say so loudly
# instead of measuring the shutdown of something that already exited.
watching=0
for _ in $(seq 1 60); do
    if docker logs dsc-smoke 2>&1 | grep -q WATCHING; then watching=1; break; fi
    sleep 1
done

if [ "$watching" -eq 0 ]; then
    fail "the container never reached its watch loop, shutdown not measured"
    printf '        container log:\n'
    docker logs dsc-smoke 2>&1 | sed 's/^/        /' | tail -20
    docker rm -f dsc-smoke >/dev/null
    echo
    echo "smoke test failed: $failures check(s)"
    exit 1
fi

started=$(date +%s)
docker stop dsc-smoke >/dev/null
elapsed=$(( $(date +%s) - started ))
code=$(docker inspect -f '{{.State.ExitCode}}' dsc-smoke)

check "graceful shutdown exit code" "0" "$code"
if [ "$elapsed" -lt 10 ]; then
    pass "docker stop returned in ${elapsed}s, inside the 10s grace period"
else
    fail "docker stop took ${elapsed}s, the process was killed"
fi
if docker logs dsc-smoke 2>&1 | grep -q "Seafile daemon is stopped"; then
    pass "the daemon was stopped on the way out"
else
    fail "the daemon was not stopped on the way out"
fi
docker rm -f dsc-smoke >/dev/null

echo "== the HEALTHCHECK command through the real entrypoint"
# Runs through main(), unlike the fixture above: HOME/UID/GID come from the
# same drop_privileges() path a real deployment uses, so .ccnet ends up
# under /dsc like it does in production, not under root's home directory.
docker rm -f dsc-smoke >/dev/null 2>&1 || true
docker run -d $PLATFORM_ARG --name dsc-smoke \
    -e SERVER_HOST=example.invalid -e USERNAME=u -e PASSWORD=p -e LIBRARY_ID=x \
    "$IMAGE" >/dev/null

ready=0
for _ in $(seq 1 30); do
    if docker logs dsc-smoke 2>&1 | grep -q "Seafile daemon is ready"; then ready=1; break; fi
    sleep 1
done

if [ "$ready" -eq 0 ]; then
    fail "the daemon never became ready, HEALTHCHECK not measured"
else
    if docker exec dsc-smoke runuser -u seafile -- python3 /dsc/healthcheck.py; then
        pass "HEALTHCHECK command exits 0 while the daemon is up"
    else
        fail "HEALTHCHECK command did not exit 0 while the daemon was up"
    fi
fi
docker rm -f dsc-smoke >/dev/null

echo "== the HEALTHCHECK command reports unhealthy when the daemon is down"
docker rm -f dsc-smoke >/dev/null 2>&1 || true
docker run -d $PLATFORM_ARG --name dsc-smoke "$IMAGE" sleep 60 >/dev/null
if docker exec dsc-smoke runuser -u seafile -- python3 /dsc/healthcheck.py; then
    fail "HEALTHCHECK command exited 0 with no daemon running"
else
    pass "HEALTHCHECK command exits nonzero with no daemon running"
fi
docker rm -f dsc-smoke >/dev/null

echo "== configuration errors stop the container with a useful message"
out=$(docker run --rm $PLATFORM_ARG -e SERVER_HOST=h -e USERNAME=u -e LIBRARY_ID=x "$IMAGE" 2>&1; echo "rc=$?")
check "no credentials exits 2" "rc=2" "$(echo "$out" | tail -1)"

out=$(docker run --rm $PLATFORM_ARG -e SERVER_HOST=h -e USERNAME=u -e LIBRARY_ID=x \
    -e PASSWORD=p -e PASSWORD_FILE=/run/secrets/pw "$IMAGE" 2>&1)
if echo "$out" | grep -q "PASSWORD_FILE are both set"; then
    pass "conflicting secret sources are rejected by name"
else
    fail "conflicting secret sources not reported: $(echo "$out" | tail -1)"
fi

out=$(docker run --rm $PLATFORM_ARG -e SERVER_HOST=h -e USERNAME=u -e PASSWORD=p \
    -e LIBRARY_ID=x -e UPLOAD_LIMIT=-5 "$IMAGE" 2>&1)
if echo "$out" | grep -q "UPLOAD_LIMIT must be 0 or greater"; then
    pass "a negative limit is rejected by name"
else
    fail "negative limit not reported: $(echo "$out" | tail -1)"
fi

out=$(docker run --rm $PLATFORM_ARG -e SERVER_HOST=h -e USERNAME=u -e PASSWORD=p \
    -e LIBRARY_ID=x -e SEAFILE_UID=0 "$IMAGE" 2>&1; echo "rc=$?")
if echo "$out" | grep -q "uid must not be 0" && [ "$(echo "$out" | tail -1)" = "rc=2" ]; then
    pass "SEAFILE_UID=0 is rejected"
else
    fail "SEAFILE_UID=0 not rejected: $out"
fi

out=$(docker run --rm $PLATFORM_ARG -e SERVER_HOST=h -e USERNAME=u -e PASSWORD=p \
    -e LIBRARY_ID=x -e SEAFILE_GID=0 "$IMAGE" 2>&1; echo "rc=$?")
if echo "$out" | grep -q "gid must not be 0" && [ "$(echo "$out" | tail -1)" = "rc=2" ]; then
    pass "SEAFILE_GID=0 is rejected"
else
    fail "SEAFILE_GID=0 not rejected: $out"
fi

echo "== a mounted secret is read and stays out of the environment"
printf 's3cret-from-file\n' > "$WORK/pw"
out=$(docker run --rm $PLATFORM_ARG -v "$WORK/pw:/run/secrets/pw:ro" \
    -e PASSWORD_FILE=/run/secrets/pw "$IMAGE" python3 -c "
import os
from dsc.secrets import resolve_secret
secret = resolve_secret('PASSWORD', os.getenv('PASSWORD'), os.getenv('PASSWORD_FILE'))
print(secret, 'PASSWORD' in os.environ)" 2>&1 | tail -1)
check "secret file read, password absent from the environment" \
    "s3cret-from-file False" "$out"

echo "== the process drops root after setup and reaches the target uid/gid"
out=$(run "$IMAGE" python3 -c "
import os
from dsc.misc import setup_uid, create_dir, drop_privileges
from dsc import const
setup_uid(1000, 1000)
create_dir(const.DEFAULT_APP_DIR)
drop_privileges(1000, 1000)
print(os.getuid(), os.getgid(), os.environ['USER'])" 2>&1 | tail -1)
check "process runs as the target non-root user after drop_privileges" \
    "1000 1000 seafile" "$out"

echo "== a default container gets the documented defaults"
out=$(run "$IMAGE" python3 -c "
import start
from dsc.misc import config_value
d = start.defaults_from_env()
print(*(config_value(d[k]) for k in (
    'upload_limit', 'download_limit', 'delete_confirm_threshold',
    'uid', 'gid', 'disable_verify_certificate')))" 2>&1 | tail -1)
check "documented defaults" "0 0 500 1000 1000 false" "$out"

echo
if [ "$failures" -eq 0 ]; then
    echo "smoke test passed"
else
    echo "smoke test failed: $failures check(s)"
fi
exit $((failures > 0))
