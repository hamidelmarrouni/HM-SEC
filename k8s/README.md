# Kubernetes baseline

These manifests are inputs to the optional local profile in [deploy/k3d](../deploy/k3d/README.md).
Use that guide and the root README for deployment. Files in `docs/` and the standalone
validator in `scripts/` are imported reference material from the earlier deployment.

The local launcher orders database initialization and application rollout. Do not apply
this entire directory recursively: the advanced HPA, TLS, and multi-node examples require
separate configuration and are excluded from the local one-CPU profile.
