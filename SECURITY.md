# Security

## Reporting

For a GitHub-hosted copy, use **Security → Report a vulnerability** if the
maintainer has enabled private vulnerability reporting. If that option is absent,
contact the maintainer privately through a verified channel. No dedicated security
email address is published by this project. Do not open a public issue with
exploit details while arranging a private report.
Do not post credentials, subscriber reports or an exploitable payload publicly.

Include the affected version, a minimal synthetic reproduction and the impact.
If a secret was exposed, revoke it at its provider; deleting it from a file is
not enough.

## Operating safely

- Keep credentials in environment variables or your operator's secret manager.
  The CLI does not load `.env` files automatically.
- Protect configuration, reports and the SQLite database with OS permissions.
  Reports can contain subscriber addresses, query interests and source evidence.
- Use encrypted SMTP (`ssl` or `starttls`) and HTTPS model endpoints. Supply only
  credentials scoped to the sender/model account needed by this service.
- Enabling a model sends selected paper evidence to the configured model
  provider. Ensure your provider and licensing choices fit your data policy.
- Use one durable state database per profile. Do not delete state to recover an
  uncertain delivery: it removes the guard against duplicate email.
- Run as a non-root user, keep the OS and Python current, and limit outbound
  access to the retrieval, model and SMTP services your configuration uses.
- Do not treat model output or research-source content as executable commands.

The project is an operator-run CLI, not an authenticated multi-tenant web
service. Profile separation is logical isolation, not an access-control boundary.
Before offering it as a hosted service, add authentication, consent/unsubscribe,
secret management, quotas and appropriate access controls around this backend.

## Delivery recovery

If SMTP acceptance or state recording is uncertain, automatic resend stops.
Check the actual provider and recipient records before using `resolve`. SMTP
acceptance is not proof that a message arrived in the recipient's inbox.
