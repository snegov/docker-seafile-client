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
out=$(run "$IMAGE" python3 -c "
import os, seafile, pysearpc, dsc.client, dsc.misc, dsc.paths, dsc.secrets, dsc.config
print(os.environ.get('SEAFILE_CLI_VERSION', 'unset'))" 2>&1 | tail -1)
if [ -n "$out" ] && [ "$out" != "unset" ]; then
    pass "imports resolve, seafile client version is $out"
else
    fail "imports or SEAFILE_CLI_VERSION missing: $out"
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

# Wait for the daemon to be up and the process to be in its watch loop.
for _ in $(seq 1 60); do
    docker logs dsc-smoke 2>&1 | grep -q WATCHING && break
    sleep 1
done

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
