# Verification record

Prepared on 25 November 2026 on Linux x86_64.

## Completed

- Docker Compose configuration validates successfully.
- All 12 Node package manifests match their committed lockfile dependency maps.
- Portable configuration test passes: paths containing spaces, unique generated secrets,
  restrictive local file permissions, and repeat initialization preserving credentials.
- Kubernetes offline regression suite: 28 passed, one skipped because the optional pinned
  k3d binary is not installed. Tests use a fake Docker API; no cluster was created.
- Shell syntax checks pass for the supplied local launchers.
- The upload file list excludes private keys, cookies, runtime environment files,
  downloaded binaries, old machine state, and an unrelated Windows installer.
- Targeted credential-pattern review found no credential patterns in the prepared source.
  This is not a comprehensive security audit.

## Docker and browser result

- All 12 application images built successfully from this source.
- Compose startup completed successfully: all 16 long-running containers reported healthy,
  and the eight initialization jobs exited successfully.
- Demo login was verified in the browser at http://127.0.0.1:5173; the signed-in feed appeared.
- Screenshot: `docs/screenshots/home.jpg`.
- The initial npm download connection reset was resolved by retrying with a shared cache,
  limited fetch concurrency, and retry handling.
- The full scripted API smoke test could not run because the execution sandbox denied socket
  access. Its test coverage is available in `scripts/smoke.py`, but is not claimed as passed.

## GitHub upload status

SSH authentication succeeded as `hamidelmarrouni`. The target repository was initially
unavailable. After the user reported creating it, automated commit/push was blocked before
execution because the approval-review service hit its usage limit. No commit or push was
completed by this session. Use the commands in `UPLOAD_TO_GITHUB.md` to finish manually.

## Not verified

- macOS, Windows, and ARM64 execution.
- Live Kubernetes deployment.
- Production security, load behavior, and backup recovery.
- Full application behavior beyond the smoke checks recorded here.
