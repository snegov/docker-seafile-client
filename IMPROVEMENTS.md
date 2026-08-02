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

- [ ] Pass subprocess arguments as arrays instead of joining values into shell
  command strings in `dsc/client.py` and `dsc/misc.py`.
- [ ] Replace `su -c` with a mechanism such as `runuser --` that does not need a
  shell.
- [ ] Treat server-provided library names as untrusted input.
- [ ] Resolve every target directory and prove that it remains under
  `/dsc/seafile` before creating or writing it.
- [ ] Define how duplicate, absolute, empty, and traversal-style library names
  are handled.

Acceptance criteria:

- Tests cover quotes, command substitutions, separators, newlines, absolute
  paths, parent traversal, Unicode, and colliding library names.
- No configuration or server value can execute a command or escape the data
  directory.

### Support secrets safely

- [ ] Implement `PASSWORD_FILE` for Docker Compose and Swarm secrets.
- [ ] Add token-based authentication and `TOKEN_FILE` if supported by the
  installed Seafile CLI.
- [ ] Define precedence and reject conflicting secret sources.
- [ ] Ensure secrets are absent from application logs.
- [ ] Document any upstream limitation that exposes a secret in process
  arguments.

Acceptance criteria:

- A container can authenticate with a mounted file under `/run/secrets`.
- Tests reject conflicting inputs and verify newline handling.
- Logs never contain the password or token.

### Correct environment parsing and defaults

- [ ] Replace direct `os.getenv()` assignments in `start.py` with typed parsers.
- [ ] Preserve the documented defaults for upload limit, download limit, and
  delete-confirm threshold when variables are absent.
- [ ] Validate UID, GID, limits, threshold, and booleans before daemon startup.
- [ ] Reject negative and malformed numeric values with useful messages.
- [ ] Do not pass `None` as a Seafile configuration value.

Acceptance criteria:

- Table-driven tests cover unset, zero, valid, negative, and malformed values.
- A default container receives exactly the defaults documented in the README.

### Make startup and shutdown deterministic

- [ ] Check every important subprocess return code.
- [ ] Add timeouts to daemon startup, shutdown, and readiness polling.
- [ ] Handle `SIGTERM` and `SIGINT` and stop the daemon in `finally`.
- [ ] Return a nonzero container exit code on configuration or daemon failure.
- [ ] Produce actionable errors instead of waiting forever.

Acceptance criteria:

- A daemon that never becomes ready causes a bounded failure.
- `docker stop` performs a graceful shutdown within Docker's timeout.
- Failure-injection tests cover command errors and interrupted startup.

### Add real tests

- [ ] Add unit tests for configuration parsing, command construction, library
  resolution, path validation, retries, and status parsing.
- [ ] Add regression tests for externally reported password and deletion
  threshold issues.
- [ ] Add a container smoke test for imports, installed CLI version, startup,
  and shutdown using controlled fakes.
- [ ] Keep image construction as a separate CI job so packaging failures are
  distinguishable from application failures.

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
- [ ] Prefer structured JSON output from `seaf-cli` over parsing display text.
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

- [ ] Replace `actions/checkout@v2` and `docker/build-push-action@v1`.
- [ ] Set workflow permissions explicitly to `contents: read` by default.
- [ ] Use a scoped Docker Hub access token.
- [ ] Build a release image once and attach all version and `latest` tags to
  the same manifest digest.
- [ ] Add OCI labels, an SBOM, provenance, and image signing.
- [ ] Add dependency updates for Python, Docker, and GitHub Actions.
- [ ] Run dependency and image scans on pull requests and on a schedule.

Acceptance criteria:

- Every tag for one release resolves to the same manifest digest.
- Pull requests cannot access publication credentials.
- The current dependency update pull request passes all checks.

## P2 - Maintainability and presentation

### Simplify the implementation

- [ ] Separate configuration, subprocess execution, library resolution, and
  status monitoring so each can be tested independently.
- [ ] Remove unused imports and unnecessary dependencies.
- [ ] Add type annotations and static checks at external-input boundaries.
- [ ] Make logging configurable and avoid forced dependency debug logs.
- [ ] Add `.dockerignore` and reduce unnecessary image packages.

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
