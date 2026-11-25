# EC2 Security Group for the Kubernetes Baseline

After HM_SEC runs through K3s/Traefik, the intended public ports are:

| Port | Source | Purpose |
|---:|---|---|
| 22/TCP | your administration IP only | SSH |
| 80/TCP | intended client range / 0.0.0.0/0 for a public demo | HM_SEC HTTP through Traefik Ingress |
| 443/TCP | only when TLS is configured | HM_SEC HTTPS |

Do **not** expose these publicly:

- 3001–3010 microservices
- 5432 PostgreSQL
- 27017 MongoDB
- 6379 Redis
- 9092/9093 Kafka
- 6443 Kubernetes API unless you deliberately configure secure remote cluster administration

After Kubernetes acceptance succeeds, remove the old Docker demo rules for 5173 and 8080.

The Kubernetes API is administered locally over SSH using `~/.kube/config`; this avoids making 6443 public for the single-EC2 lab.
