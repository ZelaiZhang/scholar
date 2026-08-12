# Project Research Dashboard Design

**Version:** Research OS v0.5 target  
**Date:** 2026-08-12  
**Status:** Approved for planning

## 1. Purpose

Research OS already provides project guidance, evidence validation, research cycles,
knowledge search, knowledge recommendations, and knowledge-maintenance gaps. Those
capabilities are individually useful, but a researcher still has to run several
commands and mentally combine their outputs before deciding what to do next.

The project research dashboard will provide one deterministic, read-only view of an
active project's current state. Its purpose is to reduce daily coordination work,
surface evidence and methodological risks early, and return no more than three
concrete next actions without pretending to replace scientific judgment.

## 2. User Interface

The feature adds one top-level command:

```powershell
research-os dashboard --project medical-reasoning
research-os dashboard --project medical-reasoning --as-of 2026-08-12
research-os dashboard --project medical-reasoning --as-of 2026-08-12 --format json
```

Arguments:

- `--project SLUG` is required. The dashboard never guesses between projects.
- `--workspace PATH` follows the existing CLI convention and defaults to the current
  workspace.
- `--as-of YYYY-MM-DD` fixes all freshness calculations. It defaults to the local
  calendar date and is always included in structured output.
- `--format text|json` defaults to `text`.

Successful execution returns exit code 0. Invalid arguments, malformed project data,
unsafe paths, or unreadable required state return exit code 2 through the existing
CLI error boundary.

## 3. Output Contract

The dashboard returns a single immutable snapshot with these sections.

### 3.1 Project status

- project slug and title;
- current Research OS stage;
- current stage state: `ready`, `in_progress`, `blocked`, or `awaiting_human`;
- the most recent trustworthy artifact or state transition when available;
- explicit blockers reported by existing validators and guidance logic.

The dashboard must reuse the same stage and next-step interpretation as `guide`. It
must not introduce a second, conflicting workflow state machine.

### 3.2 Evidence health

- number of source IDs linked to the project;
- number currently verified and number unknown or stale;
- counts of valid ledger entries by evidence role: support, opposition/conflict, and
  limitation/uncertainty, using the ledger's existing schema rather than keyword
  guessing;
- validation issues such as an unlinked source reference or missing locator.

Only sources linked by the selected project's `project.yaml` and accepted by the
existing source and ledger validators may contribute to healthy evidence counts.
Evidence from another project must never appear in the snapshot.

### 3.3 Idea and decision state

- active cycle run, if any;
- candidate count and candidate-review progress;
- novelty check, independent review, and meta-review readiness;
- whether a human Idea decision is required;
- whether an Idea has already been selected.

The section describes state only. It cannot approve an Idea, alter a cycle, or infer
that a partially edited template has passed a gate.

### 3.4 Methodological knowledge

The dashboard reuses project-stage knowledge recommendations and returns at most
three items. Recommendations may include knowledge cards, playbooks, checklists, or
reporting guidelines. Each item retains its source/status/verification metadata and
a concise reason for its relevance.

Global knowledge items are methodological guidance, not project evidence. The
dashboard must label this boundary in text and JSON output and must not link a
knowledge source into the project automatically.

### 3.5 Risk radar

Risks are deterministic rules triggered only by validated project facts. Initial
categories are:

- evidence integrity: unknown, stale, unlinked, or locator-deficient evidence;
- medical evaluation: absent external validation, unsuitable diagnostic metrics,
  leakage risk, or unclear reference standard when the project profile makes the
  corresponding requirement applicable;
- experimental rigor: missing baseline, ablation, statistical analysis, or
  reproducibility plan when the current stage requires it;
- model adaptation: unfair fine-tuning/quantization/RL comparison or missing
  compute/configuration disclosure when declared by the project profile or design
  artifact;
- workflow integrity: damaged cycle state, pending human approval, or inconsistent
  required artifacts.

Every risk contains a stable code, severity, short explanation, and the specific
trigger that was observed. The first version does not use an LLM to invent or score
risks. When a condition cannot be established from structured state, it is reported
as unknown or omitted rather than guessed.

### 3.6 Today's actions

The snapshot returns at most three actions in this fixed priority order:

1. repair a safety, schema, path, or evidence blocker;
2. complete the active workflow gate;
3. fill a critical evidence gap;
4. strengthen methodology or knowledge coverage.

Each action contains a stable code, priority, rationale, expected artifact, and an
exact command when Research OS has a safe applicable command. Commands must come
from existing CLI contracts; the dashboard must not output invented commands or
shell fragments assembled from untrusted document contents.

## 4. Architecture

### 4.1 Pure snapshot builder

A new focused module, `research_os.dashboard`, owns immutable dashboard models and a
`build_project_dashboard(workspace, project, as_of)` function. It orchestrates
existing loaders and validators but performs no file writes and no provider calls.

The builder may depend on:

- `project` for safe project resolution and manifest loading;
- `guidance` for the canonical workflow stage and blocking state;
- `sources` and `evidence` for project-scoped source and ledger health;
- `cycle`, `review`, and journal readers for cycle state already accepted by those
  modules;
- `knowledge_recommend` and `knowledge_gaps` for stage-aware methods support.

The existing modules must not depend on `dashboard`. This keeps the dashboard an
aggregation boundary and avoids import cycles.

### 4.2 Risk rules

Risk rules live in a separate focused module or a clearly isolated section of the
dashboard module. Each rule accepts only structured, already-loaded facts and returns
zero or more immutable risk records. Rule ordering is explicit and stable.

Rules must distinguish:

- `observed`: directly established from valid structured data;
- `missing_required`: a requirement applies but its structured evidence is absent;
- `unknown`: the current schema cannot establish the condition.

Only `observed` and `missing_required` conditions can become blocking or warning
risks. Unknown conditions cannot be rendered as confirmed defects.

### 4.3 Renderers and CLI

Text and JSON rendering are presentation-only functions. JSON uses explicit schema
version `1`, stable field names, and stable array ordering. Text rendering is concise
and Chinese-first for daily use while preserving stable risk/action codes.

CLI parsing delegates to the pure builder and renderers. It does not duplicate
business logic.

## 5. Determinism and Read-Only Boundary

Given identical workspace bytes, project slug, and `--as-of`, text and JSON output
must be byte-for-byte stable.

The command:

- performs no network or external API calls;
- creates no cache, lock, log, run, or temporary file inside the workspace;
- does not update access times intentionally;
- does not modify project manifests, evidence ledgers, cycles, knowledge profiles,
  or the global knowledge base;
- never reads or recommends evidence belonging only to another project.

An optional DeepSeek/OpenAI narrative layer is explicitly deferred. A future layer
may summarize the versioned JSON snapshot, but it cannot alter facts, risks, gates,
or actions and must require explicit external-API consent.

## 6. Error and Degraded-State Handling

Errors that make the selected project unsafe or uninterpretable fail closed with
exit code 2. Examples include a path escaping the workspace, malformed project
manifest, malformed evidence ledger, or structurally invalid cycle manifest.

Recoverable absence is represented in the snapshot rather than treated as a crash.
Examples include a new project with no linked sources, no active cycle, no knowledge
profile, or no completed experiment design. Such states produce explicit actions and
may reduce recommendation specificity.

The dashboard must not catch broad exceptions and silently emit a healthy-looking
partial report.

## 7. Testing and Acceptance Criteria

The implementation is accepted only when all of the following hold:

1. A new project, evidence-building project, awaiting-approval project, and selected-
   Idea project produce correct stage summaries and next actions.
2. Unknown or stale linked sources and invalid ledger references fail or block in
   agreement with existing validators.
3. Evidence and cycle data from another project never appear in the snapshot.
4. Recommendations are stage-aware, limited to three, and clearly labeled as
   methodological guidance rather than project evidence.
5. Risk rules expose their trigger and do not convert unknown state into an observed
   defect.
6. At most three actions are returned in the documented priority order.
7. Two executions using the same fixed `--as-of` produce identical text and JSON.
8. Invalid dates and unsupported formats return exit code 2 with actionable errors.
9. Before/after byte snapshots prove that `dashboard` makes no workspace changes.
10. The full suite passes with warnings treated as errors, packaging metadata is
    updated, and an installed wheel passes a smoke test outside the source tree.
11. README and `docs/DEVELOPER-HANDOFF.md` document the command, architecture,
    safety boundary, and extension points.

## 8. Out of Scope

The first release does not:

- execute experiments or access an experiment repository;
- automatically approve Ideas or edit research artifacts;
- write a daily Markdown report;
- call DeepSeek, OpenAI, or another external provider;
- use embeddings, online search, or a generative model to infer risks;
- replace `guide`, `doctor`, or the evidence validator.

These exclusions keep the dashboard trustworthy, inexpensive, reproducible, and
usable before the researcher configures any external API.
