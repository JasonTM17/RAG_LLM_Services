# Summary

What does this PR change and why? Link the phase or plan step it belongs to
(`plans/...`) if applicable.

# Scope

- Files/areas changed:
- Out of scope (explicitly not touched):

# Verification

Record each command you ran and its result. Use the narrowest truthful status
(`LOCAL_PASS`, `CI_PASS`, `HOLD`, `NOT_RUN`). Local checks do not prove CI,
deployment, or live-provider behavior.

- Phase gate: `.\scripts\verify-phase-NN.ps1` -> [result]
- Backend: `make api-lint` -> [result]
- Backend: `make api-typecheck` -> [result]
- Backend: `make api-test` -> [result]
- Frontend (if touched): `make web-verify` / `make web-build` -> [result]
- Security: `make secret-scan` -> [result]
- Security (if SQL or dependencies touched): `make sql-scan` / `make dependency-scan` -> [result]
- `git diff --check` -> [result]

# Documentation impact

- Contracts, setup, architecture, or operator behavior changed: [yes/no]
- Docs/ADRs updated: [list or "none"]

# Rollback

How to revert this change safely (single revert, migration down-step, config
flag, etc.).

# Checklist

- [ ] Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`, ...)
- [ ] Staged explicit paths only; no unrelated dirty work included
- [ ] No secrets committed; `make secret-scan` passes
- [ ] Tests added or updated for behavior changes
- [ ] `.env.example` stays placeholder-only
