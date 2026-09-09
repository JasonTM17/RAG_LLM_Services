# Security Policy

## Reporting a vulnerability

Do not open a public issue for security problems. Report vulnerabilities
privately through GitHub security advisories:

https://github.com/JasonTM17/RAG_LLM_Services/security/advisories/new

Include what you observed, the affected component or endpoint, and the steps
or inputs needed to reproduce it.

## Scope

- In scope: source code in this repository (API, worker, web app, packages,
  compose configuration, workflow exports, and verification scripts).
- Out of scope: hosted services. No hosted deployment exists yet; there is
  nothing to attack there. Do not test third-party services such as DeepSeek,
  GitHub, or any external provider.

## Project status

This is an early development preview (v0.x). It is not production-ready and
carries no support or fix SLA. The production release remains on `HOLD` until
the release gates in the
[threat model](docs/security/threat-model.md) are separately proven.

## Not considered vulnerabilities

The following are known, documented design boundaries. Reports of them will
not be treated as novel vulnerabilities:

- Prompt injection through user-provided documents. The system ingests
  untrusted documents and treats retrieved text as untrusted context; this is
  a documented design boundary covered by prompt-injection tests. See
  [Threat model](docs/security/threat-model.md).
- Owner scoping via the `X-User-Id` header. Development auth resolves the
  owner from this header in non-production environments only; it fails closed
  in production mode. Production authentication uses stateless JWT Bearer tokens
  issued via `/api/v1/auth/register` and `/api/v1/auth/login`. See the
  Authentication Readiness section of the
  [threat model](docs/security/threat-model.md).
- Any weakness whose remediation is already tracked as pending release work
  in the [threat model](docs/security/threat-model.md) rather than a defect in
  the implemented controls.
