# Evidence-Bound Manuscript Audit Design

## 1. Goal

Add a read-only `research-os manuscript-audit` command that checks whether a Markdown manuscript can be traced back to the current project's validated evidence, human-approved Idea, experiment design, and registered aggregate results.

The command does not judge scientific truth or semantic entailment. It verifies explicit provenance contracts and reports exactly what still requires researcher review.

## 2. Why this is the next feature

Research OS v0.7 answers which manuscript sections are ready and which evidence may be used. It does not inspect the manuscript that is eventually written. A researcher can still accidentally:

- omit a claim reference while editing;
- cite an open, conflicted, invalid, or differently typed claim as a fact;
- write Methods before Idea approval or experiment-design completion;
- write Results that are not linked to a registered aggregate result artifact;
- remove a limitation during prose polishing;
- place identifiable medical information in a draft.

The audit closes that gap without generating prose or sending the manuscript to an external API.

## 3. Approaches considered

### A. Deterministic hidden block annotations — selected

Each audited prose block has one invisible HTML comment that declares its scientific role and provenance. The command validates those declarations against Research OS state.

Advantages: deterministic, local, reviewable in Git, robust to paraphrasing, and compatible with rendered Markdown. Cost: the writer must keep paragraph-level annotations.

### B. Fuzzy sentence-to-ledger matching — rejected

Token similarity or embeddings could suggest related claims, but negation, abbreviations, and medical terminology make automatic alignment unsafe. A high similarity score is not evidence that one statement entails another.

### C. Mandatory external-model semantic audit — rejected

An LLM could identify rhetorical and semantic problems, but its output is nondeterministic and would require manuscript externalization permission. It may be added later as an optional second opinion, never as the provenance gate.

## 4. Command contract

```powershell
research-os manuscript-audit `
  --project medical-reasoning `
  --draft .\projects\medical-reasoning\writing\draft.md `
  --as-of 2026-08-13 `
  --format markdown
```

Arguments:

- `--project`: required validated project slug;
- `--draft`: required Markdown file that is a direct regular file below the project's `writing/` directory;
- `--as-of`: optional ISO date, defaulting to the local current date;
- `--format`: `markdown` or `json`, default `markdown`;
- `--workspace`: workspace root, default current directory.

Exit codes:

- `0`: no manuscript issues;
- `1`: audit completed and found one or more manuscript issues;
- `2`: unsafe input, identifiable-health-data suspicion, malformed project state, invalid date, path escape, link/reparse point, unstable snapshot, or unreadable draft.

The command never writes files, calls a provider, or accesses the network.

## 5. Annotation grammar

An annotation is an exact single-line HTML comment immediately before one Markdown content block:

```markdown
<!-- research-os:kind=fact; claims=C001,C002 -->
The public benchmark reported improved calibration under the stated setting.
```

Supported forms:

```text
<!-- research-os:kind=fact; claims=<claim-id>[,<claim-id>...] -->
<!-- research-os:kind=inference; claims=<claim-id>[,<claim-id>...] -->
<!-- research-os:kind=hypothesis; claims=<claim-id>[,<claim-id>...] -->
<!-- research-os:kind=limitation; claims=<claim-id>[,<claim-id>...] -->
<!-- research-os:kind=method; idea=<idea-id> -->
<!-- research-os:kind=result; artifacts=<filename>[,<filename>...] -->
```

IDs and filenames use only ASCII letters, digits, dot, underscore, colon, and hyphen; they are never inserted into shell commands. Duplicate keys, unknown keys, empty lists, duplicate values, extra text inside the comment, or more than one annotation for a block are invalid.

The annotation applies only to the next non-empty content block and never crosses a heading. Headings, blank lines, horizontal rules, fenced code, and the annotation comments themselves are not prose blocks. A paragraph, list, block quote, or table is one block until the next blank line or heading.

Only the eight H2 sections below are audited:

1. Abstract
2. Introduction
3. Related Work
4. Methods
5. Experiments
6. Results
7. Limitations and Ethics
8. Conclusion

Front matter and sections outside this fixed set are ignored in v0.8. Missing or duplicate audited sections are reported.

## 6. Provenance rules

### 6.1 Fact blocks

Every referenced claim must:

- exist in the current project ledger;
- have `type: fact` and `status: verified`;
- pass the existing claim-level ledger validation against this project's linked and verified source IDs;
- retain at least one support `source_id + locator` pair and a non-empty limitation.

Open, conflicted, invalid, excluded, inference, or hypothesis claims cannot support a fact block.

### 6.2 Inference and hypothesis blocks

Every referenced claim must exist, pass ledger structure validation, and have the exact declared type. Its original status, support, opposition, confidence, and limitation remain visible in JSON/Markdown output. These blocks never become citation candidates.

### 6.3 Limitation blocks

Every referenced claim must be valid and have a non-empty `limitations` field. The audit reports the claim IDs and their recorded limitations so a researcher can compare the draft wording manually.

### 6.4 Method blocks

The annotation must name one Idea that is selected in the active completed research cycle. The Methods section must be `ready` in the v0.7 manuscript plan, which requires the human Idea gate and experiment-design completion.

### 6.5 Result blocks

Every named artifact must be a direct file registered by `artifacts/results-manifest.yaml`. Its hash, source repository, generation time, file identity, and manifest identity must pass the existing stable result-input validation. The Results section must be `ready`, which requires aggregate result input and completed conservative interpretation.

An annotation proves provenance, not statistical correctness or clinical utility.

## 7. Section and block rules

- Every prose block inside an audited section requires exactly one annotation.
- `kind=method` is allowed only in Methods or Experiments.
- `kind=result` is allowed only in Abstract, Experiments, Results, or Conclusion.
- `kind=limitation` is allowed in Abstract, Introduction, Results, Limitations and Ethics, or Conclusion.
- `kind=fact`, `inference`, and `hypothesis` may appear in any audited section when their provenance rules pass.
- Any annotated block in a `blocked` section receives `SECTION_BLOCKED`; a block in a `partial` section receives `SECTION_PARTIAL`.
- The audit does not compare prose meaning with the cited claim. It emits the boundary `ANNOTATION_NOT_ENTAILMENT` in every report.

## 8. Medical privacy boundary

Before parsing or reporting manuscript content, scan the draft for the existing identifiable-medical markers:

- `姓名`
- `住院号`
- `身份证`
- `联系电话`
- `patient_id`
- `medical_record_number`

If any marker occurs, stop with exit code 2 and a generic `PHI_SUSPECTED` error. Do not echo the matching line, nearby text, or extracted value. This is a conservative safety tripwire, not a complete de-identification system.

## 9. Stable issue model

Each issue contains:

- `code`;
- `severity`: `error` or `warning`;
- `section`;
- `block_index`;
- `line`;
- `claim_ids`;
- `artifact_names`;
- `message` generated only from trusted templates and validated IDs.

Stable issue codes:

- `MISSING_SECTION`
- `DUPLICATE_SECTION`
- `UNANNOTATED_BLOCK`
- `ORPHAN_ANNOTATION`
- `INVALID_ANNOTATION`
- `KIND_NOT_ALLOWED_IN_SECTION`
- `UNKNOWN_CLAIM`
- `CLAIM_KIND_MISMATCH`
- `CLAIM_NOT_CITABLE`
- `CLAIM_INVALID`
- `LIMITATION_MISSING`
- `IDEA_NOT_SELECTED`
- `UNKNOWN_RESULT_ARTIFACT`
- `SECTION_BLOCKED`
- `SECTION_PARTIAL`

All are errors in v0.8. The report is sorted by document line, then issue code. No automatic fixes are applied.

## 10. Data model and public schema

`ManuscriptAudit` contains:

- `schema_version=1`;
- `as_of`;
- public project status;
- draft path relative to the project;
- draft SHA256;
- `status`: `pass` or `issues`;
- block counts by kind;
- section summaries;
- ordered issues;
- used claim IDs;
- used result artifact names;
- boundaries.

The JSON serializer is explicit. It must not expose direct file identities, directory identities, snapshot tokens, absolute paths, provider configuration, or source notes.

## 11. Snapshot and file safety

1. Resolve the project through the existing containment and reparse checks.
2. Require `writing/` to be a real project directory and the draft to be a direct regular `.md` file within it.
3. Capture draft and writing-directory identities, read at most 4 MiB as stable UTF-8, then recheck both identities.
4. Build the v0.7 manuscript plan before and after draft parsing.
5. Compare the two explicit public plan payloads byte-for-byte. If research state changes, fail with exit code 2 instead of combining time points.
6. Recheck the draft identity and SHA before returning.

The draft may contain untrusted text. It is displayed as neither a shell command nor an error message. Report commands, if any are added later, may use only validated slug and fixed templates.

## 12. Markdown output

Order is fixed:

1. project, draft, date, and overall status;
2. section coverage table;
3. block-kind counts;
4. ordered issues with line and trusted identifiers;
5. used evidence and result provenance summary;
6. hard boundaries.

The report does not reproduce draft paragraphs.

## 13. Integration changes

- Create `src/research_os/manuscript_audit.py` for parsing, validation, payload, and Markdown rendering.
- Add the CLI adapter in `src/research_os/cli.py`.
- Extend `manuscript_plan.py` with a read-only public result-artifact projection only if the audit cannot reuse an existing validated internal representation.
- Update `src/research_os/templates/manuscript-outline.md` with annotated examples.
- Update `.agents/skills/manuscript-assistant/SKILL.md` so generated blocks carry the annotation contract.
- Add unit, CLI, workspace, doctor, and installed-wheel tests.
- Bump package version to `0.8.0` only after the installed-wheel journey passes.

## 14. Testing strategy

All behavior is developed test-first. Required cases include:

- every supported annotation kind;
- verified fact acceptance and open/conflicted/invalid/type-mismatch rejection;
- selected Idea and design gate enforcement;
- registered result artifact and result-readiness enforcement;
- missing, duplicate, malformed, orphan, and cross-heading annotations;
- unannotated paragraph, list, quote, and table blocks;
- exact H2 section handling, fenced-code exclusion, and deterministic ordering;
- PHI tripwire without sensitive-text echo;
- path escape, symlink, junction/reparse, same-content replacement, mid-read replacement, and oversize draft rejection;
- public JSON internal-field leakage attempts;
- read-only workspace byte comparison and fixed-date determinism;
- full source tests, warnings-as-errors, compileall, pip check, both doctors, diff check, independent adversarial review, and installed-wheel smoke.

## 15. Non-goals

- semantic entailment or plagiarism detection;
- automatic citation metadata, BibTeX, DOI, author, venue, or year generation;
- automatic rewriting or fixing of manuscript prose;
- clinical advice or clinical-utility certification;
- venue-specific reporting-checklist completion;
- external API calls;
- experiment, training, fine-tuning, quantization, or RL execution;
- auditing Word, LaTeX, or PDF in v0.8.

## 16. Acceptance criteria

Given a Markdown draft containing annotated fact, inference, hypothesis, method, result, and limitation blocks, the command must:

- accept only provenance that is valid for the current project and declared kind;
- report all unannotated or unsafe blocks without reproducing their prose;
- stop without content disclosure when identifiable-medical markers are found;
- fail closed on file or research-state drift;
- emit deterministic Markdown and explicit schema-versioned JSON;
- make no writes and no network/provider calls;
- pass an installed-wheel end-to-end journey;
- receive an independent review verdict with no unresolved Critical or Important findings.
