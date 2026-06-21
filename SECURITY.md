# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability in CiteVyn, **please do
not open a public GitHub issue.** Instead, report it privately via
GitHub's "Report a vulnerability" feature on the
[Security tab](https://github.com/imrohitagrawal/CiteVyn-AI/security/advisories/new) of this repository.

Please include:

1. A clear description of the vulnerability and the impact.
2. A reproducer (curl, request payload, or test script).
3. The affected version (commit SHA or release tag).
4. Whether you intend to disclose publicly, and on what timeline.

We commit to:

- **Acknowledge** within **3 business days** of the report.
- **Triage** within **7 days**; assign a CVSS estimate and a
  target fix release.
- **Coordinate** a fix + advisory publication. We follow
  [coordinated disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure)
  and prefer a 90-day window before public disclosure.
- **Credit** reporters in the fix release notes unless anonymity
  is requested.

## Supported versions

| Version     | Supported           |
|-------------|---------------------|
| `main`      | yes — latest dev    |
| Tagged release (e.g. `v0.2.0`) | yes — until the next minor is cut + 30 days |
| Older       | best-effort         |

## Out-of-scope

- Denial-of-service attacks against demo deployments.
- Self-XSS via paste of malicious content into the `/v1/ask`
  prompt (this is a normal user-controlled input).
- Rate-limit bypasses that don't also bypass authentication.

## Security features of the production stack

For operators and reviewers, the production deployment enforces:

- **TLS** via Caddy's automatic Let's Encrypt issuance (ACME HTTP-01
  on port 80). The API only listens on the docker network.
- **Security headers** (HSTS, X-Frame-Options, X-Content-Type-Options,
  Referrer-Policy, Permissions-Policy, restrictive CSP). See
  [`infra/docker/Caddyfile`](infra/docker/Caddyfile).
- **Non-root containers** (uid 1001) — no shell, no package manager
  in the runtime image.
- **Bearer-token auth** — two scopes (`demo`, `admin`); admin
  routes return 404 (not 403) to unauthenticated callers so the
  attack surface is not enumerated.
- **Rate limiting** — sliding-window per-user, per-route, backed by
  Redis. 429 responses include `Retry-After`.
- **Refusal envelope** — out-of-domain or low-confidence questions
  return a refusal marker; the API never returns a guessed answer.
- **No cookies, no sessions, no client-side state** — the API is
  purely stateless over Bearer auth.

For the full threat model, see
[`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md).