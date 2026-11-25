# Local demo security

HM-SEC is a local development lab, not a hardened production deployment.

- Runtime secrets are randomly generated into `runtime/.env.docker`, excluded from Git.
- Only the frontend and gateway publish ports, bound to loopback by default.
- Databases have no published host ports. The Compose data network is internal.
- Demo accounts share the locally generated seed password; the main demo account is also an administrator.
- Development OTP is fixed; email uses console mode; OAuth is disabled; moderation auto-approves.
- The local media endpoint allows unauthenticated uploads. Do not expose this configuration to an untrusted network.
- Logs can contain application data and development verification messages. Review before sharing.

Never commit private keys, certificates, kubeconfigs, cookies, real `.env` files, database exports, or user uploads. The supplied archives remain separate from this repository. If credentials from an earlier copy were published, rotate them in the service that issued them.

Before an internet deployment, replace development authentication shortcuts, protect uploads, configure TLS and managed secrets, review dependencies and permissions, and verify backups and recovery. The included manifests alone do not establish production readiness.
