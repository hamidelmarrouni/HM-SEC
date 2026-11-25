# HM_SEC — Docker Compose to Kubernetes Mapping

This document maps the verified Docker Compose baseline to the Kubernetes implementation in this repository.

| Docker Compose baseline | Kubernetes implementation | Why |
|---|---|---|
| `frontend` container | `Deployment/frontend` + `Service/frontend` | Stateless edge workload; rolling updates and HPA-safe. |
| `nginx-gateway` | `Deployment/nginx-gateway` + `Service/nginx-gateway` | Keeps the existing API/WebSocket gateway contract. |
| `user-service` | Deployment + ClusterIP Service | Stateless application workload; PostgreSQL state is external. |
| `writer-service` | Deployment + ClusterIP Service | Stateless process; MongoDB owns persistent content state. |
| `feed-service` | Deployment + ClusterIP Service | Stateless process; MongoDB/Redis are dependencies. |
| `chat-service` | Deployment + ClusterIP Service, 1 replica | Socket.IO currently has no cross-replica adapter; do not HPA it yet. |
| `notification-service` | Deployment + ClusterIP Service, 1 replica | Socket.IO currently has no cross-replica adapter; keep one replica. |
| `email-service` | Deployment + ClusterIP Service | Kafka consumer in console-email mode. |
| `moderation-service` | Deployment + ClusterIP Service | Kafka consumer/producer in deterministic dev auto-approval mode. |
| `reward-service` | Deployment + ClusterIP Service | Stateless process; PostgreSQL owns reward state. |
| `query-service` | Deployment + ClusterIP Service | Stateless query/hydration layer; HPA-safe. |
| `media-service` | Deployment + ClusterIP Service + PVC | Local media compatibility layer needs persistent storage. |
| Docker published ports 5173/8080 | Traefik Ingress on 80 | One public Kubernetes edge; all HM_SEC Services remain ClusterIP. |
| Docker DNS names | Kubernetes Service DNS | Existing names such as `kafka:9092` remain valid. |
| Docker `edge/app/data` networks | Labels + NetworkPolicies | Reproduces segmentation using Kubernetes-native controls. |
| PostgreSQL container + named volume | StatefulSet + headless/ClusterIP Services + PVC | Stable state and storage. |
| MongoDB `rs0` + named volume | StatefulSet + headless Service + PVC + init Job | Preserves transaction-compatible replica-set semantics. |
| Redis + AOF volume | StatefulSet + PVC | Preserves cache/state durability behavior. |
| Kafka KRaft + named volume | StatefulSet + PVC | Preserves single-broker development event bus. |
| `postgres-init` | Job | Creates `user_service` and `reward_service` schemas once. |
| `mongodb-init` | Job | Idempotently initiates/reconfigures `rs0` and waits for PRIMARY. |
| `kafka-init` | Job | Creates the exact inherited topic set once. |
| `user-db-init` | Job | Runs Prisma DB push once, never per replica. |
| `reward-db-init` | Job | Runs Prisma DB push once, never per replica. |
| `user-seed` | Job | Idempotent development seed. |
| `reward-score-init` | Job | Initializes reward score rows. |
| `media-init` | Job | Creates/prepares the media PVC. |
| Docker health checks | startup/readiness/liveness probes | Kubernetes only routes to Ready Pods and restarts unhealthy containers. |
| `.env.docker` | runtime ConfigMap + three Secrets | Non-secret config and secret material are separated. |
| Docker restart policy | Deployment/StatefulSet controllers | Kubernetes reconciles desired state continuously. |
| Docker Compose scaling | replicas + HPA | Applied only to workloads proven safe to scale horizontally. |
| manual backup | CronJobs + backup PVC | Daily PostgreSQL/MongoDB backup jobs with retention. |

## Critical invariants preserved

1. Browser traffic enters through the frontend/API edge, not private services.
2. `user-service` still owns PostgreSQL schema `user_service`.
3. `reward-service` still owns PostgreSQL schema `reward_service`.
4. MongoDB stays `rs0`.
5. Kafka topic names are unchanged, including inherited `comment.delted.events`.
6. Chat and notification Socket.IO paths remain `/api/v1/chat/socket.io` and `/api/v1/notification/socket.io`.
7. `query-service` remains the search/hydration compatibility layer; Elasticsearch is not introduced.
8. `media-service` remains local/PVC-backed; S3 is not required.
9. Email remains console/development mode.
10. Moderation remains deterministic auto-approval for this baseline.
11. Databases, Redis, Kafka and ports 3001–3010 are never exposed as public Services.
12. Prisma and Kafka bootstrap stay controlled one-shot Jobs.
