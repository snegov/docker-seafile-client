# Improvement Plan

This plan prioritizes user safety and a working release pipeline before public
portfolio polish. The project already has useful adoption evidence: more than
5,800 Docker Hub pulls, external issues, and external contributions.

Security-sensitive findings should be fixed and released before detailed
exploit scenarios are discussed in public issues.

## P0 - Release blockers

### Restore reproducible image builds

- [x] Replace the unavailable Seafile APT repository used in `Dockerfile`.
  Upstream discontinued it; the CLI now ships as an x86_64-only AppImage.
- [x] Install a supported Seafile CLI version from an official source.
- [x] Pin the version and verify its checksum during the build. The checksum is
  trust-on-first-use: upstream publishes no digest or signature alongside the
  AppImage, so this is weaker than the signed APT repository it replaces.
- [x] Remove `apt-key`, which is deprecated and trusts keys globally.
- [x] Add a smoke check that `seaf-cli` runs to the image build. Note that
  `seaf-cli` has no `--version` flag; use `seaf-cli --help` and assert the
  expected subcommands, and record the installed version from the package
  manager instead.
- [ ] Scan the resulting image and review every high or critical finding.
- [ ] Establish a stronger trust anchor for the AppImage than a self-derived
  checksum: an upstream digest or signature, or a verified artifact mirrored
  somewhere we control.

Acceptance criteria:

- A clean `docker build --no-cache .` succeeds in CI.
- The installed Seafile version is explicit and current.
- An invalid artifact checksum fails the build. Upstream publishes no signature
  for the AppImage, so signature verification is not achievable from this
  source.

### Remove shell and path injection risks

- [x] Pass subprocess arguments as arrays instead of joining values into shell
  command strings in `dsc/client.py` and `dsc/misc.py`. The password is no
  longer wrapped in quotes to survive a shell, which also fixes passwords
  containing quotes, `$`, and backticks.
- [x] Replace `su -c` with a mechanism such as `runuser --` that does not need a
  shell. `runuser -u` sets the same `HOME` and a `PATH` that still finds the
  `seaf-cli` wrapper, so the daemon environment is unchanged.
- [x] Treat server-provided library names as untrusted input.
- [x] Resolve every target directory and prove that it remains under
  `/dsc/seafile` before creating or writing it. Symlinks are resolved first,
  so an existing symlink in the libraries directory cannot redirect a write.
- [x] Define how duplicate, absolute, empty, and traversal-style library names
  are handled. See `dsc/paths.py` and the "Some notes" section of the README.

Acceptance criteria:

- Tests cover quotes, command substitutions, separators, newlines, absolute
  paths, parent traversal, Unicode, and colliding library names.
- No configuration or server value can execute a command or escape the data
  directory.

### Support secrets safely

- [x] Implement `PASSWORD_FILE` for Docker Compose and Swarm secrets. Only a
  trailing newline is stripped, so a secret keeps any surrounding spaces.
- [x] Add token-based authentication and `TOKEN_FILE` if supported by the
  installed Seafile CLI. It is: `seaf-cli sync` takes `-T`, and ignores the
  password when a token is given.
- [x] Define precedence and reject conflicting secret sources. Two sources for
  one secret (`PASSWORD` with `PASSWORD_FILE`) are rejected; a token takes
  precedence over a password, as it does in `seaf-cli` itself.
- [x] Ensure secrets are absent from application logs. Both the password and
  the token are masked before a command is logged.
- [x] Document any upstream limitation that exposes a secret in process
  arguments. `seaf-cli` accepts credentials only as arguments, so a secret is
  visible to any process in the container. The account password no longer goes
  there: the client authenticates with an API token, which can be revoked.
  See the README.

Acceptance criteria:

- A container can authenticate with a mounted file under `/run/secrets`.
- Tests reject conflicting inputs and verify newline handling.
- Logs never contain the password or token.

### Correct environment parsing and defaults

- [x] Replace direct `os.getenv()` assignments in `start.py` with typed parsers.
  See `dsc/config.py` and `defaults_from_env()`.
- [x] Preserve the documented defaults for upload limit, download limit, and
  delete-confirm threshold when variables are absent. They were not: an unset
  variable overwrote the argparse default with `None`, so a default container
  sent the literal string `None` for all three.
- [x] Validate UID, GID, limits, threshold, and booleans before daemon startup.
  UID and GID are now integers; as strings they never equalled the integers
  they were compared against, so `usermod` ran on every start.
- [x] Reject negative and malformed numeric values with useful messages.
- [x] Do not pass `None` as a Seafile configuration value. Booleans are also
  rendered as `true`/`false` rather than Python's `True`/`False`. This fixed
  `DISABLE_VERIFY_CERTIFICATE`, which never worked. The daemon reads the key
  with `seafile_session_config_get_bool`, which is
  `g_strcmp0(value, "true") == 0`, so it accepts only the exact string
  `"true"`. Python's `str(True)` stored the string `"True"`, which did not
  match and was therefore read as false, leaving verification on for anyone
  who asked to disable it. The default stored the string `"False"`, which is
  also not `"true"` and so was correctly read as false.

Acceptance criteria:

- Table-driven tests cover unset, zero, valid, negative, and malformed values.
- A default container receives exactly the defaults documented in the README.

### Make startup and shutdown deterministic

- [x] Check every important subprocess return code. A failed `seaf-cli sync` is
  reported per library and does not stop the remaining ones.
- [x] Add timeouts to daemon startup, shutdown, and readiness polling. See
  `DAEMON_START_TIMEOUT` and `DAEMON_STOP_TIMEOUT` in `dsc/const.py`; the stop
  timeout is deliberately below the 10 second `docker stop` grace period.
- [x] Handle `SIGTERM` and `SIGINT` and stop the daemon in `finally`.
- [x] Return a nonzero container exit code on configuration or daemon failure.
- [x] Produce actionable errors instead of waiting forever.

Acceptance criteria:

- A daemon that never becomes ready causes a bounded failure.
- `docker stop` performs a graceful shutdown within Docker's timeout.
- Failure-injection tests cover command errors and interrupted startup.

### Add real tests

- [ ] Add unit tests for configuration parsing, command construction, library
  resolution, path validation, retries, and status parsing. Command
  construction and path validation are covered in `tests/`; configuration
  parsing, retries, and status parsing are not.
- [ ] Add regression tests for externally reported password and deletion
  threshold issues.
- [ ] Add a container smoke test for imports, installed CLI version, startup,
  and shutdown using controlled fakes. Graceful shutdown was verified by hand
  in the built image (`docker stop` returns immediately with exit code 0
  instead of being killed after 10 seconds); it is not yet automated in CI.
- [x] Keep image construction as a separate CI job so packaging failures are
  distinguishable from application failures. The `unit-test` job does not
  depend on the image build.

Acceptance criteria:

- CI fails on a deliberate parsing, quoting, or path-safety regression.
- Application tests run without requiring a live production server.

### Repair and validate the quick start

- [x] Change the Compose example to mapping syntax so quote characters are not
  passed as part of `LIBRARY_ID`.
- [x] Pin the example to a versioned image instead of an implicit latest tag.
- [x] Add a checked-in `compose.example.yaml`.
- [x] Validate it with `docker compose config` in CI.

## P1 - Reliability and supply chain

### Networking and protocol behavior

- [ ] Add explicit connect and read timeouts to all HTTP requests.
- [ ] Define a bounded retry budget with backoff and jitter.
- [ ] Handle authentication, rate limits, malformed responses, and retryable
  server errors separately.
- [ ] Make TLS configuration consistent between Python requests and Seafile.
- [ ] Support a custom CA bundle; keep certificate disabling as a last resort.
- [x] Prefer structured JSON output from `seaf-cli` over parsing display text.
  `seaf-cli list --json` is used instead of splitting the display columns,
  which could not represent a library name or a path containing whitespace.
  `list-remote` still uses the HTTP API rather than the CLI.
- [ ] Reject ambiguous library names and an empty requested library set.

### Runtime hardening

- [ ] Run the long-lived process as the configured non-root user after setup.
- [ ] Reject UID or GID zero unless a documented use case requires it.
- [ ] Add a health check for the daemon and RPC endpoint.
- [ ] Handle temporary RPC failures and daemon restarts without corrupting
  state.
- [ ] Document supported CPU architectures instead of implying multi-platform
  support.

### CI and release pipeline

- [x] Replace `actions/checkout@v2` and `docker/build-push-action@v1`.
- [x] Set workflow permissions explicitly to `contents: read` by default.
- [x] Use a scoped Docker Hub access token. The workflow now reads
  `secrets.DOCKER_TOKEN`; the repository secret still has to be created from a
  scoped Docker Hub token before the next tag is pushed.
- [x] Build a release image once and attach all version and `latest` tags to
  the same manifest digest.
- [x] Add OCI labels via `docker/metadata-action`.
- [ ] Add an SBOM, provenance, and image signing.
- [x] Add dependency updates for Python, Docker, and GitHub Actions. A weekly
  Dependabot configuration covers `requirements.txt`, the Dockerfile base
  image, and the workflow actions. The Seafile AppImage is fetched by URL and
  checksum, so it still has to be bumped by hand.
- [ ] Run dependency and image scans on pull requests and on a schedule.

Acceptance criteria:

- Every tag for one release resolves to the same manifest digest.
- Pull requests cannot access publication credentials.
- The current dependency update pull request passes all checks.

## P2 - Maintainability and presentation

### Simplify the implementation

- [ ] Separate configuration, subprocess execution, library resolution, and
  status monitoring so each can be tested independently.
- [x] Remove unused imports and unnecessary dependencies. Both pinned
  requirements are used; `urllib3` is imported directly but only pinned
  transitively through `requests`.
- [ ] Add type annotations and static checks at external-input boundaries.
- [ ] Make logging configurable and avoid forced dependency debug logs.
- [ ] Add `.dockerignore` and reduce unnecessary image packages. `.dockerignore`
  is in place; `binutils` and `squashfs-tools` are still shipped in the final
  image because the AppImage is unpacked in the same stage.

### Establish a visible maintenance process

- [ ] Publish GitHub Releases for future tags with compatibility and rollback
  notes.
- [ ] Add `CHANGELOG.md`, `SECURITY.md`, and concise contribution guidance.
- [ ] Add issue templates that request image, client, and server versions plus
  sanitized logs.
- [ ] Triage stale issues and document the status of Docker secret support.
- [ ] Enable branch protection and require passing CI before merge.

### Improve the public project page

- [x] Link directly to the Docker Hub image near the top of `README.md`.
- [ ] Add CI, release, Docker pulls, and license badges after the checks are
  trustworthy.
- [ ] Add a short architecture and process-lifecycle section.
- [ ] Add a tested compatibility matrix.
- [ ] Explain deletion behavior, volume ownership, state loss, backup
  expectations, and recovery.
- [ ] Fix example inconsistencies and typographical errors.

## Release gate

Do not publish the next image until all of the following are true:

- [ ] A clean, reproducible build uses a supported Seafile client.
- [ ] External values cannot reach a shell or escape the data directory.
- [ ] Secret-file or token authentication is covered by tests.
- [ ] Startup, retries, and shutdown are bounded and observable.
- [ ] Unit and container smoke tests pass.
- [ ] The steady-state process is non-root and has a useful health check.
- [ ] Release tags point to one scanned and signed image digest.
- [ ] The README quick start succeeds from a clean environment.
