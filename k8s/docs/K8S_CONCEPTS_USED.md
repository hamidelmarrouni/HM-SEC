# Kubernetes Concepts Used in HM_SEC

HM_SEC deliberately uses Kubernetes objects where they solve a real project problem rather than creating fake examples.

## Core object model

- **Namespace**: `hm-sec` isolates the application resources and gives NetworkPolicy/RBAC a clean boundary.
- **Pod**: the runtime unit created by Deployments, StatefulSets, Jobs and CronJobs.
- **ReplicaSet**: created automatically by each Deployment; you normally do not manage it directly.
- **Deployment**: manages the stateless frontend, gateway and microservices, rolling updates, restarts and replica counts.
- **StatefulSet**: manages PostgreSQL, MongoDB, Redis and Kafka because they need persistent identity/storage semantics.
- **Service (ClusterIP)**: stable internal DNS and virtual IP for every HM_SEC component.
- **Headless Service**: stable DNS identity for StatefulSet members such as `mongodb-0.mongodb-hs...`.
- **Ingress**: public HTTP entry; Traefik sends `/api` and `/media` to the existing Nginx gateway and `/` to the frontend.
- **IngressClass**: K3s provides the `traefik` class used by HM_SEC.

## Configuration and security

- **ConfigMap**: non-secret runtime values such as public URL, Kafka DNS, local media URL and development feature flags.
- **Secret**: JWT/OTP secrets, PostgreSQL credentials, seed credentials and compatibility credentials. The start script creates them from the existing private Docker env; no secret manifest is committed.
- **Secret encryption at rest**: a new K3s install is created with `--secrets-encryption`.
- **ServiceAccount**: application Pods use `hm-sec-app` with API-token automount disabled.
- **RBAC Role/RoleBinding**: `hm-sec-ops-reader` has namespace-scoped read-only operational visibility.
- **Pod Security Admission labels**: namespace enforces baseline and warns/audits against restricted policy.
- **NetworkPolicy**: default deny + explicit edge/app/data flows reproduce Docker network segmentation.

## Reliability and lifecycle

- **initContainer**: microservices wait for required service sockets before the main container starts.
- **startupProbe**: allows slow startup without premature liveness restarts.
- **readinessProbe**: only Ready Pods receive Service traffic.
- **livenessProbe**: restarts a container when its application health fails persistently.
- **RollingUpdate**: stateless Deployments use `maxUnavailable: 0` and `maxSurge: 1`.
- **terminationGracePeriodSeconds**: allows Node services time to shut down cleanly.
- **resources.requests/limits**: every long-running workload declares CPU/memory budgets so scheduling and HPA have real inputs.

## State and storage

- **StorageClass**: K3s `local-path` dynamically provisions development PVs on the EC2 node.
- **PersistentVolumeClaim**: stateful components and media request persistent storage.
- **PersistentVolume**: created dynamically by the local-path provisioner; inspect with `kubectl get pv`.
- **volumeClaimTemplates**: each StatefulSet gets its own persistent data claim.

## Batch and automation

- **Job**: eight controlled bootstrap tasks map directly from Docker one-shot services.
- **CronJob**: daily PostgreSQL and MongoDB backups demonstrate scheduled Kubernetes workloads and produce operational recovery artifacts.

## Scaling and availability

- **HorizontalPodAutoscaler (`autoscaling/v2`)**: enabled only for frontend, gateway, user-service and query-service because those are safe to multiply in the current architecture.
- **PodDisruptionBudget**: a multi-node manifest is included but intentionally not enabled on the single-node EC2 cluster; on one node it can block maintenance without providing availability.
- **Topology spread / anti-affinity**: also belongs to the later multi-node/EKS step. A single-node cluster has no failure domain to spread across.

## Concepts intentionally not faked

- **DaemonSet** is not used just to say “we used DaemonSet.” It becomes appropriate later for per-node runtime/observability agents such as Falco or node exporters.
- **multi-replica chat/notification** is not enabled because the current Socket.IO services do not contain a shared cross-replica Socket.IO adapter. Scaling them blindly would make real-time delivery inconsistent.
- **multi-replica Mongo/Kafka/Postgres** is not pretended to be HA on one EC2 host. The present StatefulSets are the Kubernetes functional baseline; HA needs multiple nodes and a deliberate stateful architecture.
