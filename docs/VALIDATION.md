# Verification record

Prepared on 25 November 2026; network access rechecked on 26 November 2026 on Linux x86_64.

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
- Automatic address support was rebuilt and deployed: frontend listens on all IPv4 interfaces,
  and API, media, and WebSocket traffic use the frontend origin on port 5173.
- The full smoke suite passed through loopback, the host's LAN IP, and its Tailscale IP:
  frontend/gateway health, user/admin login, refresh cookies, public queries, chat and
  notification polling plus HTTP 101 WebSocket upgrades, relative profile/post upload URLs,
  and media upload/readback.
- The launcher configuration regression test and frontend TypeScript/production build passed.
- These address checks ran from the server; connectivity from another physical computer
  still depends on its network route, firewall, and VPN permissions.

## GitHub

The initial project commit was verified on the repository's main branch over SSH.
The automatic-address change follows that existing repository history. Runtime secrets
and machine-specific environment settings remain excluded from Git.

## Not verified

- macOS, Windows, and ARM64 execution.
- Live Kubernetes deployment.
- Production security, load behavior, and backup recovery.
- Full application behavior beyond the smoke checks recorded here.
