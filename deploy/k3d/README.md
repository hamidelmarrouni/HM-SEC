# Optional local Kubernetes lab

This folder combines the supplied one-CPU k3d tooling with the application in the repository root.
Source paths are resolved relative to this folder. No pre-existing application checkout is needed.

## Requirements

This optional mode targets Debian/Ubuntu/Kali Linux with rootful Docker, cgroup v2,
CPU quota/cpuset support, Python and PyYAML. It is not the cross-platform entry point;
use the root Compose launcher on macOS or Windows. ARM64 requires matching application images.

The lab keeps all cluster containers on one logical CPU (default CPU 0), with a 6 GB
node memory limit. This is a constrained learning configuration; slow startup or timeouts
are possible. It does not limit the whole host or Docker's image-unpacking work.

## Build and start

From the repository root:

```sh
python3 scripts/hmsec.py build
cd deploy/k3d
./INSTALL.sh
./UP.sh
```

`INSTALL.sh` can install distribution packages and downloads checksum-verified k3d/kubectl
into this folder's ignored `bin/`. Review the script before executing it.
`UP.sh` stops the `hm-sec` Compose project, creates/starts a local cluster, imports the
application images you built, deploys the stack in order, and runs acceptance checks.
The default application URL is http://127.0.0.1:8088.

Configuration comes from the root `runtime/.env.docker`. Copy `local.env.example` to
`local.env` only if overrides are needed. `local.env` is trusted shell configuration;
the Docker environment file is parsed as data. Runtime kubeconfigs and rendered secrets
remain in ignored local directories. The default user kubeconfig is not modified.

## Commands

| Script | Purpose |
| --- | --- |
| `UP.sh` | Setup, import, deploy, validate |
| `SETUP.sh` | Create/start the capped cluster |
| `START.sh` / `STOP.sh` | Resume/stop the cluster, retaining its data |
| `STATUS.sh` | Inspect cluster and application state |
| `IMPORT_IMAGES.sh` | Import locally built images |
| `DEPLOY.sh` | Deploy the rendered profile |
| `VALIDATE.sh` | Check topology, workloads, storage, and application |
| `VALIDATE.sh --media` | Also check uploaded media survives pod recreation |
| `KUBECTL.sh -n hm-sec get pods` | Use the isolated cluster configuration |
| `COMPOSE_START.sh` / `COMPOSE_STOP.sh` | Switch to/stop Compose using the lab's mode guard |

Use these mode-switch scripts when switching between runtimes. Calling the root Compose
launcher directly bypasses this lab's mutual-exclusion guard.

Kubernetes PVCs are a separate data set from Compose volumes. Starting this lab does not
migrate existing Compose data. Successful initialization jobs are retained on redeployment.
Stopping retains the cluster and volumes; do not delete them merely to stop the app.

## Manifests

`k8s/` in the repository root is the preferred baseline; `manifests/upstream/` is its
bundled fallback. `lib/render.py` generates the local profile with one replica, long
startup allowances, persistent Kafka logs, suspended backups, and local image tags.
HPA, multi-node PDB, and TLS examples are not deployed by this local profile.
The app's local-demo limitations described in the root SECURITY.md also apply here.

## Verification

```sh
python3 -m unittest discover -s tests -v
```

These regression tests use a fake Docker API and do not run a cluster. One optional test
requires the pinned k3d binary. The current repository verification record is
[docs/VALIDATION.md](../../docs/VALIDATION.md). A passing offline suite does not establish
that Kubernetes has been deployed or verified on the current host.
