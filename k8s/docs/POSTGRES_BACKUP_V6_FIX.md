# HM_SEC Kubernetes V6 — PostgreSQL Backup Fix

This patch fixes the manual PostgreSQL backup failure where `pg_dump` received
`connection refused` from the `postgres` ClusterIP.

The backup now:
- waits for PostgreSQL with `pg_isready` for up to 120 seconds;
- connects through the stable StatefulSet Pod DNS
  `postgres-0.postgres-hs.hm-sec.svc.cluster.local`;
- verifies the dump file is non-empty;
- preserves the existing 7-day retention cleanup.

It does not recreate K3s, databases, Kafka, application Deployments, PVCs, or NetworkPolicies.
