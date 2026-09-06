<!-- agentkit-managed-contract-start -->
# AgentKit project instructions

This file is the portable, runtime-neutral operating contract for projects that
install AgentKit. It applies to Codex, Claude Code, Cursor, Gemini CLI, Grok
Build, and compatible agent runtimes. AgentKit commands use the `/ak:`
namespace; do not rewrite them into another kit's command namespace.

OpenCode is supported through its project adapter, and Grok Build through the
native `.grok` project adapter described below. OMP (the Pi-based `omp` CLI) is
supported through the native `.omp` adapter described below.

## Read order

1. Read the project `README.md` and the nearest nested `AGENTS.md` before work.
2. Inspect `.agentkit/config.yaml` when present. Honor `coding_level`, `paths`,
   `workflow_artifact_gate`, and every explicit project override.
3. Inspect repository state, package/runtime metadata, and relevant tests.
4. Select the smallest AgentKit workflow that covers the request.
5. Load each selected skill's complete `SKILL.md` before following it.

Project or user instructions override this file. A nested `AGENTS.md` overrides
it only for files below that directory.

## Registry and portability rules

- Canonical kit development source: `engineer/skills/`.
- Runtime mirrors: `.codex/skills/`, `.claude/skills/`, `.cursor/skills/`, and
  `.agents/skills/`. Gemini CLI and OpenCode consume `.agents/skills/` directly
  as their supported workspace alias; do not add a duplicate `.gemini/skills/`
  mirror.
- Gemini adapter assets are `.gemini/commands/ak/`, `.gemini/agents/`,
  `.gemini/settings.json`, and root `GEMINI.md`. Keep them project-relative and
  free of provider credentials, UI overrides, and Claude-only hooks.
- OpenCode consumes `.agents/skills/` natively. Its generated
  `.opencode/opencode.json` contains thin `/ak:<name>` command templates that
  point to that shared registry, so do not add a `.opencode/skills` mirror or
  per-skill `.opencode/commands` files; either would duplicate the `/ak:`
  namespace.
- OMP/Pi consumes `.agents/skills/` through its `agents` provider. Its native
  adapter ships `.omp/agents/`, `.omp/commands/`, and `.omp/config.yml`; do not
  create `.omp/skills/` or copy `.claude`, `.codex`, or `.opencode` registries
  into an OMP-only project. OMP command filenames use `/ak-<name>` on Windows
  because `:` is not a valid filename; the canonical skill form is
  `/skill:ak:<name>` when `skills.enableSkillCommands` is enabled.
- Grok Build 1.0.13 discovers native project skills from `.grok/skills/` and
  native task agents from `.grok/agents/`. Its adapter ships those directories,
  the opt-in `.grok/workflows/agentkit-audit.rhai` workflow,
  `.grok/config.toml`, `.grok/README.md`, and the ownership manifest. Run that
  read-only workflow explicitly as `/workflow agentkit-audit {"task":"..."}`;
  it is separate from skill discovery. Claude agents/hooks/rules/settings are
  optional compatibility assets for mixed runtime projects; Grok skill
  discovery must continue to work when `.claude/` is absent. Do not rely on
  `.agents/skills/` or copy `.claude/skills/` into a Grok-only project, because
  those belong to other runtimes.
- Use only the registry selected by the current runtime. Never load two mirror
  trees for the same task; duplicate registries cause duplicate skill entries.
- In an installed project, prefer the project-local registry over a global
  fallback. A global skill must not silently shadow a reviewed project skill.
- Skill command `/ak:name` normally maps to folder `ak-name`. Office skills are
  routed by `/ak:document-skills` to nested `/ak:docx`, `/ak:pdf`, `/ak:pptx`,
  or `/ak:xlsx`.
- Resolve paths from the current project root or the selected skill directory.
  Never embed a developer-specific drive, username, download path, or home path.
- Do not copy `.venv`, caches, credentials, auth files, or generated reports to
  another machine. Recreate runtime dependencies at the destination.
- If the project-local skill cannot be found, report the exact searched paths
  and enter degraded mode; do not pretend the skill ran.

## Default AgentKit workflow

Use this sequence for material engineering work:

1. `/ak:goal-warmup` for a large or long-running objective.
2. `/ak:advise` when intent, product trade-offs, architecture, or scope is
   ambiguous. Advice is a decision artifact, not implementation.
3. `/ak:scout` to collect codebase evidence and affected boundaries.
4. `/ak:plan` or `/ak:issue-to-plan` to produce an executable plan and Outcome
   Contract. Do not implement in `issue-to-plan`.
5. `/ak:worktree`, `/ak:orchestrate`, or `/ak:team` only when ownership can be
   split into independent bounded work.
6. `/ak:cook`, `/ak:fix`, `/ak:vibe`, or the relevant domain skill to implement.
7. `/ak:test` plus domain-specific checks.
8. `/ak:code-review`; use `/ak:wukong` for a high-risk or difficult claim that
   needs adversarial falsification.
9. `/ak:ship` only after required evidence and review gates pass.
10. `/ak:journal` or `/ak:handoff` when durable continuation context is useful.

This is routing guidance, not permission to widen scope. Read-only questions do
not authorize edits, commits, pushes, deployment, or external messages.

## Plan-locked execution

Apply the additive `/ak:plan-lock` overlay alongside the selected original
implementation workflow. The overlay constrains execution cadence and does not
remove or replace any original workflow stage or required role.

For material implementation, an accepted active plan is the default execution
authority. Optimize for forward progress through that plan, not for maximum
analysis, agent utilization, or test volume.

### Execution recipe

Repeat this loop until the accepted plan reaches its terminal checkpoint:

1. Resolve the active plan and the first incomplete step.
2. Load only the Outcome Contract, global constraints, current step, and its
   exit criterion; consult older detail only when the current step depends on it.
3. Take the smallest reversible action that advances that step.
4. Record the result and evidence, then select the next incomplete step.
5. Continue without asking whether to proceed unless a user decision boundary,
   external-authority boundary, or concrete blocker has been reached.

Before the first implementation action, perform one bounded consistency sweep
over the accepted plan for contradictory paths, contracts, dependencies, or
acceptance criteria. Resolve a local wording ambiguity as an execution ruling;
do not reopen planning after implementation has started merely to seek a more
elegant option.

- Keep four items explicit while working: active plan, current phase, next
  unfinished step, and that step's exit criterion. If a small task does not
  need a durable plan, treat the user's requested outcome as the bounded plan.
- For long-running or multi-phase work, keep
  `plans/<plan-id>/reports/execution-ledger.md`. Its first non-heading line must
  name the repo-relative active plan path. Record completed steps and evidence,
  current step, authorized rulings, deferred findings, and the next resume
  point. On resume, verify that plan identity, do not repeat evidence-backed
  completed work, and start at the first incomplete step. Never reuse a ledger
  from another plan.
- Execute the next unfinished step. Do not repeatedly scout settled areas,
  reopen accepted decisions, invent alternative architectures, refactor nearby
  code, or add polish while the current step remains safely actionable.
- Stop analysis when the available evidence is sufficient to take the next
  reversible in-scope action. Uncertainty alone is not a reason to brainstorm
  every possible failure mode.
- Classify new information as `NOW`, `LATER`, or `BLOCKER`. Act immediately only
  on `NOW` work required by the current step or on a `BLOCKER`; keep `LATER`
  items out of the implementation path and report them at handoff.
- Never replan autonomously. A direct user instruction may revise the plan.
  Otherwise, route the proposed change to exactly one appropriate authority:
  Advisor for intent/scope ambiguity, Kongming for architecture or sequencing,
  Wukong for a falsifiable high-risk claim, or a specialized agent for a domain
  constraint. Replan only when that role returns an evidence-backed finding
  that invalidates a current assumption, step, or safety boundary. If the
  required role is unavailable, keep the current plan unchanged, record a
  blocker, and ask the user instead of silently choosing a new direction.
- When replanning is authorized, record the recommendation and the smallest
  plan delta, then resume from the first affected incomplete step; do not
  restart planning from zero.
- A specialist recommendation may be applied without another user round-trip
  only when it is reversible, stays inside the accepted Outcome Contract, and
  does not change public contracts, release target, risk acceptance, authority,
  or non-goals. Ask the user to decide any recommendation that crosses one of
  those boundaries. Advice is not blanket permission to redesign the project.
- Continue until every in-scope phase reaches its evidence-backed exit
  criterion or a concrete blocker requires user/external authority. An
  intermediate compile, partial implementation, or agent report is not a
  natural stopping point.

Use this drift tripwire whenever new information appears:

| Signal | Classification | Action |
| --- | --- | --- |
| Clarifies wording without changing outcome, contract, sequence, or risk | Execution ruling | Record it and continue |
| Breaks the current step but has a reversible in-scope repair | `NOW` defect | Repair narrowly, prove it, and resume |
| Suggests nicer architecture, extra hardening, polish, or unrelated cleanup | `LATER` | Defer; keep it off the critical path |
| Invalidates a plan assumption, public contract, safety boundary, or required sequence | Replan candidate | Obtain the defined Advisor/Kongming/Wukong/specialist recommendation |
| Requires changed scope, non-goal, release target, risk acceptance, authority, or irreversible action | User decision | Stop at a safe boundary and ask the user |

## Delegation gate

Keep every agent role that the selected original AgentKit workflow marks as
required. Outside those named workflow roles, single-agent execution is the
default. Additional subagents are a limited coordination tool, not a
completeness ritual and not a way to occupy available concurrency.

Spawn a subagent only when at least one of these conditions is true:

1. the selected original workflow, user, or accepted plan explicitly requires
   independent agent work;
2. Advisor, Kongming, or Wukong is required for its defined decision, strategy,
   or adversarial-evidence role;
3. a specialized agent has a capability materially needed by the current plan
   step that the controller does not have efficiently; or
4. independent, disjoint work removes a real critical-path delay and its
   integration cost is lower than doing it sequentially.

Do not add extra subagents for routine repository reading, search,
implementation, test execution, summarization, status checks, or confirmation
of the controller's own conclusion beyond roles already required by the
selected workflow. Before each additional spawn, state the condition above
that passed and provide one bounded mission with exact scope, allowed writes,
deliverable, evidence requirement, and stop condition. Reuse an existing agent
when it already owns the context. Use one delegation wave at a time by default;
do not permit nested delegation unless the user or active plan explicitly
requires it.

Every authorized delegation brief must also name the active plan, current step,
reason the controller cannot efficiently own the slice, files or domain owned,
forbidden scope, and exact return format. Worker agents may not spawn further
agents. The controller alone integrates findings, changes plan state, and
decides whether a new delegation wave is justified.

Role boundaries remain strict:

- Advisor resolves outcome, scope, or trade-off ambiguity before it changes the
  implementation path.
- Kongming reviews architecture, sequencing, and high-risk plan changes; it
  does not become an extra general-purpose coder.
- Wukong attacks one falsifiable, load-bearing claim read-only and never
  self-approves a repair.
- A specialized agent receives only the domain slice that needs its specialty.

Agent findings do not automatically expand scope. Integrate a finding now only
when it is evidence-backed and blocks the current plan, invalidates a plan
assumption, or reveals an in-scope high/critical risk. Otherwise record it for
the planned defect checkpoint or handoff.

This gate overrides skill examples or routing defaults that suggest delegation
or replanning from task size, file count, domain count, available concurrency,
or implementation completion alone. Those signals may identify a candidate;
they never authorize a spawn or plan change by themselves.

## Verification checkpoints

Implementation and verification are separate lanes connected by planned
checkpoints. Do not turn every edit into a broad test cycle.

- Put exact verification checkpoints and commands in the plan. During an
  implementation step, run only the cheapest check needed to keep the step
  safely executable, such as changed-file syntax, a focused type check, or a
  single regression that determines the next action.
- Give each checkpoint a verification budget: named commands/scope, the
  broadening trigger, and the allowed rerun condition. Do not rerun an unchanged
  passing gate, expand a focused gate because of generic doubt, or insert an
  unplanned suite onto the release critical path.
- Do not repeatedly run the full test suite, full lint/build, browser matrix,
  end-to-end suite, load test, security scan, or unrelated package checks after
  each edit. Batch those gates at the affected phase boundary or terminal
  verification stage according to risk.
- If a confirmed in-scope defect blocks the next plan step, fix it immediately,
  run the narrow regression needed to prove the repair, and resume the plan.
- If Kongming or Wukong produces an evidence-backed high/critical finding or
  invalidates the current approach, pause at the nearest safe boundary, apply
  the smallest cause-aligned fix or plan delta, run a targeted check, and then
  resume the next incomplete step.
- Batch other non-blocking in-scope defects into the plan's defect-fix
  checkpoint. Record out-of-scope defects without fixing them unless the user
  expands scope.
- At terminal verification, run the planned focused checks, fix observed
  in-scope failures, rerun affected checks, then broaden only as required by
  changed contracts and risk. Review and completion follow this converging
  loop; they do not interrupt every implementation step.

Use a bounded repair circuit at a failing checkpoint: the controller gets at
most two focused cause-aligned repair attempts. If the same gate still fails,
use exactly one appropriate specialist-guided attempt when the delegation gate
passes. If it still fails, record the evidence and ask the user or report the
external blocker; do not enter an open-ended fix/retest loop. Re-review and
rerun only the gate that covers the repair. Findings in untouched code are
deferred unless they invalidate a load-bearing assumption or make the accepted
outcome unsafe.

## Fast routing

| Intent | Preferred route |
| --- | --- |
| Explain or answer architecture | `/ak:ask`, optionally `/ak:advise` |
| Locate code quickly | `/ak:scout` |
| Semantic symbol/impact analysis | `/ak:gkg` or `/ak:graphify` |
| Reproduce and diagnose a bug | `/ak:scout` -> `/ak:debug` |
| Repair a bounded bug | `/ak:debug` -> `/ak:fix` -> `/ak:test` |
| Hard intermittent/security/concurrency claim | `/ak:debug` -> `/ak:wukong` -> fix -> independent retest |
| New feature from issue | `/ak:issue-to-plan` -> `/ak:plan` -> `/ak:cook` |
| End-to-end feature to PR-ready | `/ak:vibe` |
| Multi-agent coding | `/ak:orchestrate` or `/ak:team` |
| Parallel isolated branches | `/ak:worktree` |
| Backend/API | `/ak:backend-development` |
| Database/schema/query | `/ak:databases` |
| Auth | `/ak:better-auth` plus `/ak:security` |
| Frontend implementation | `/ak:frontend-development` |
| UI replication/design | `/ak:frontend-design`, `/ak:ui-styling`, `/ak:ui-ux-pro-max` |
| Browser test | `/ak:web-testing` or `/ak:agent-browser` |
| Logged-in Chrome state | `/ak:chrome-profile` |
| CI/deployment | `/ak:devops` or `/ak:deploy` |
| Security review | `/ak:security` and `/ak:security-scan` |
| Documentation | `/ak:docs` or `/ak:docs-seeker` |
| Office documents | `/ak:document-skills` |
| Unknown capability | `/ak:find-skills` or `/ak:agentkit` |

Do not activate every listed skill. Use the minimum set needed for the task and
state the selected workflow in progress updates.

## Specialized review agents

### Advisor

Advisor clarifies outcomes, trade-offs, constraints, non-goals, and decision
criteria. Use Advisor before building when a decision could materially change
scope. Advisor must not be treated as proof that implementation is correct.

### Kongming

Kongming reviews architecture, sequencing, capability boundaries, failure
containment, and release strategy. For high-risk work, ask Kongming to review a
frozen exact snapshot independently and read-only.

### Wukong

Wukong is an adversarial investigator, not a general implementer or release
authority. Give it a falsifiable claim, target identity, invariants, authority,
budget, and evidence boundary. It returns `FALSIFIED`, `NOT_FALSIFIED`,
`INCONCLUSIVE`, or `UNDERDEFINED` with an explicit gate and handoff.

Use Wukong especially for concurrency races, distributed state, migrations,
tenant/auth isolation, quota/accounting ledgers, recovery, portability, encoded
boundaries, and model/tool authority. High or critical findings require a fresh
independent confirmation before acceptance. Wukong never self-approves a fix.

## Planning contract

Store durable plans under `plans/` using the closest template in
`plans/templates/`. AgentKit's canonical shape is a directory
`plans/<timestamp>-<slug>/` containing `plan.md` and at least one
`phase-NN-*.md`; add more phases plus `reports/`, `research/`, and `assets/`
when the work needs them. If
`.agentkit/scripts/set-active-plan.cjs` exists, pass that plan directory (or its
`plan.md`) to select the active plan; otherwise link the active plan from the
project tracker without creating a machine-specific path.

The reviewed Codex and Claude hook packages can persist session-bound plan
state when they provide a valid runtime marker and `CK_SESSION_ID`. The current
Cursor compatibility adapter has no reviewed session-state marker, so active
plan selection there is validation-only; do not claim persistence until a
Cursor state bridge is installed and tested.

Every material plan must include:

- outcome and success signal;
- scope, non-goals, and authority;
- current evidence and assumptions;
- affected components and ownership;
- ordered implementation stages;
- bite-sized executable steps with exact inputs/outputs and an exit criterion;
- acceptance criteria and exact verification commands;
- risks, rollback, and recovery;
- documentation/release impact;
- unresolved decisions and explicit blockers.

For AgentKit `plan.md` frontmatter, use `pending`, `in-progress`, `completed`,
or `cancelled`. Live task APIs may instead require their own enum such as
`pending`, `in_progress`, `completed`; do not copy one schema into the other.
Completion means current evidence proves the acceptance criteria; intent, a
green narrow test, or a worker's report alone is insufficient. Represent a
blocked plan through `blockedBy`, its dependency graph, and an explicit blocker
section rather than inventing an unsupported plan status.

## Implementation rules

- Search before editing. Prefer existing modules, conventions, helpers, and
  generated-file workflows.
- Make the smallest coherent change that satisfies the full requested outcome.
- Preserve unrelated dirty and untracked work. Stage only explicit intended
  paths; never reset, clean, or overwrite broadly.
- Do not modify global skills or user configuration unless explicitly asked.
- Prefer portable paths and structured argv. Avoid shell string composition,
  implicit current-working-directory assumptions, and platform-only quoting.
- Treat generated manifests and mirrors as derived artifacts. Update canonical
  source first, synchronize all required mirrors, then regenerate manifests.
- Never weaken a gate or change an oracle merely to make a failing test green.
- Do not expose secrets, credentials, raw auth/provider errors, absolute home
  paths, or private oracle content in logs and committed evidence.
- If a file becomes difficult to reason about, modularize at a stable boundary;
  do not split code mechanically just to satisfy a line-count preference.

## Multi-agent ownership

- Give each writer a disjoint file set or isolated worktree and a concrete
  deliverable.
- One integration owner controls shared state, merges, manifests, and releases.
- Reviewers remain read-only and identify the exact base/HEAD/scope they saw.
- A review becomes stale when the reviewed snapshot changes. Freeze, rerun, and
  record a new identity before accepting it.
- Workers do not merge, push, or mutate another worktree unless explicitly
  authorized.
- Report `PASS`, `FAIL`, `BLOCKED_CAPABILITY`, or `NOT_RUN`; never translate an
  unobserved environment into a pass.

## Verification discipline

Verify in proportion to risk:

1. syntax/static checks for changed files;
2. focused regression tests for the changed behavior;
3. package/integration tests for affected boundaries;
4. manifest, mirror, generated-artifact, and `git diff --check` gates;
5. cross-platform/runtime matrix when portability is claimed;
6. independent Advisor/Kongming review for high-risk release claims;
7. authenticated provider or live-service evidence only when the environment
   actually supplies it.

Record the command, result, environment, and important limitation. Unit tests do
not prove live provider routing, OS isolation, deployment, Redis/Postgres, or
macOS behavior. A CI workflow definition is not evidence that CI ran.

For bug fixes, include a regression that fails on the old behavior and passes on
the new behavior. For concurrency or recovery, test a deterministic schedule or
fault point. For security boundaries, add a negative/abuse case. For portable
hooks, cover spaces, Unicode, quoting, parent traversal, symlinks, and the actual
runtime family.

## Git and release

- Inspect `git status`, branch, remotes, and relevant history first.
- New branches use concise intent-based names such as `feature/...`, `fix/...`,
  or `release/...`; never prefix them with `codex/`.
- Use Conventional Commits that describe the intent. Preserve an existing
  branch/PR name unless asked to rename it.
- Run `git diff --check`, targeted tests, manifest/parity validation, and a
  secret scan before commit.
- For Gemini adapter changes, also run
  `generate-gemini-adapter.py --check` and `validate-gemini-adapter.py`; an auth
  failure is `NOT_RUN` for live Gemini execution, not a static adapter failure.
- For Grok adapter changes, also run `validate-grok-adapter.py`; an absent Grok
  CLI is `NOT_RUN` for live discovery, while provider authentication and
  trusted hook execution remain separate evidence gates.
- A local commit is not a push, a push is not a passing CI run, and passing CI is
  not production verification. State each boundary honestly.
- Use force-with-lease only when history rewrite was explicitly authorized.

## Documentation and handoff

Update documentation when behavior, setup, architecture, commands, contracts,
or operator expectations change. Prefer links and exact paths over duplicated
large excerpts. Keep examples portable and redact host identities.

A final handoff states:

- outcome and files changed;
- tests/gates actually observed;
- commit/push/CI state;
- unresolved risk or external blocker;
- the next safe action, if any.

Do not call a kit, agent, feature, or release fully production-ready when the
required live, cross-platform, isolation, provenance, or rollback evidence has
not been observed.
## Grok compatibility hardening

Grok security hooks fail closed on empty, malformed, or incomplete payloads;
non-security hooks retain bounded timeout handling. Native Grok discovery uses
`.grok/skills/` and `.grok/agents/`; compatibility hooks are optional and are
not a prerequisite for skills.

## Antigravity adapter

Antigravity receives explicit `.agents/skills` projections and allowlisted
agents. Its default discovery and hook parity remain capability-gated until
proved by the live CLI; no credentials or host-specific paths are emitted.
<!-- agentkit-managed-contract-end -->
