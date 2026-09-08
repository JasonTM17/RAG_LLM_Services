---
name: Bug report
description: Report broken behavior or an unexpected result
labels: ["bug"]
---

**What happened**

<!-- Actual behavior, including error output or failing test name. -->

**What you expected**

**Reproduction**

```text
# Exact commands, e.g.
make api-test
uv run pytest apps/api/tests/ -k <test_name>
# or the relevant phase gate:
.\scripts\verify-phase-NN.ps1
```

**Environment**

- OS: [Windows / Linux]
- Python: [3.13.x]
- Compose service states (`docker compose ps`): [running / exited / not used]

**Relevant phase or surface**

<!-- e.g. Phase 04 ingestion (packages/rag), Phase 05 retrieval, apps/worker -->
