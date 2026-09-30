# Criterion-Preserving Context Management for Budgeted Psychiatric Interviews

<!-- research-os:generated:start -->
> **Prospective manuscript v0.1, 2026-09-30.** No method implementation or research experiment has been completed. The topic and protocol await researcher selection. `fact` sentences cite verified ledger claims; `inference` and `hypothesis` passages are interpretations and proposed work. These labels must remain until scientific review. Results, approval statements, and final contribution claims are intentionally pending.

## Abstract — hypothesis / proposed study

We propose to study whether a bounded working context can preserve the evidence needed for diagnostic reasoning in simulated psychiatric interviews. The target is a revisable criterion-level memory that retains supporting and refuting observations, temporal scope, unresolved conflicts, and links to the original dialogue. Rather than treating a completed tree branch as an irreversible decision, the proposed controller would invalidate dependent states when earlier evidence is explicitly corrected. We plan a two-stage evaluation: fixed dialogue replay to isolate memory effects, followed by controlled interactive interviews. Comparisons would match the diagnostic backbone, knowledge, input budget, and access to historical records, while accounting for all memory-management calls. The primary analysis would measure diagnostic macro-F1 at a preregistered budget; evidence loss, unsupported updates, revision recovery, and cumulative cost would provide mechanism and efficiency analyses. A deterministic controller would be tested before an optional learned policy. Whether either policy improves the quality-cost tradeoff remains an open empirical question. This work is intended for offline research and would not establish clinical utility.

**Results sentence:** [To be written only after externally executed, audited experiments.]

## 1. Introduction

`fact F01` The SCID-5 is described by Columbia University as a semi-structured DSM-5 interview administered by a clinician or trained mental health professional. [SCID-5 FAQ](https://www.columbiapsychiatry.org/research/research-labs/diagnostic-and-assessment-lab/structured-clinical-interview-dsm-disorders-12)

`fact F02/F04` Structured psychiatric dialogue already has close precedents: PsyCoTalk describes a SCID-5-RV state machine and context tree, while ProAI includes a diagnostic knowledge tree with a back transition. [PsyCoTalk §4.1](https://arxiv.org/html/2510.25232v2), [ProAI §3.2.2](https://arxiv.org/html/2502.20689v1)

`inference I01` These precedents make a tree-guided interview or a backtracking action alone an insufficient novelty argument for the proposed study. We instead ask what information must survive a memory update when a diagnostic reasoner has a fixed context budget. This formulation separates the procedural order of an interview from the evidence supporting its current decisions.

`hypothesis H01` A useful working memory may need to retain more than positive symptom summaries. We propose to preserve condition identity, evidence direction, temporal scope, unresolved conflict, and valid revisions as explicit fields. The empirical question is whether this representation improves diagnosis quality and evidence retention relative to strong general-memory methods under comparable resource constraints. We do not assume that a structured record is correct merely because it is parseable.

`hypothesis RQ2` A second question concerns evidence revision. If an earlier statement is explicitly corrected, retaining its downstream conclusion may create a mismatch between current evidence and the active interview branch. We propose to invalidate dependent decisions and measure both successful recovery and inappropriate reversal. Ordinary additions referring to a different time period would not automatically invalidate prior observations.

`hypothesis / planned contributions` The proposed study would aim to contribute: (i) a criterion-preservation contract for bounded diagnostic memory; (ii) a controlled replay and revision evaluation that separates memory from question-selection effects; and (iii) an empirically assessed deterministic controller, with a learned extension only if its extra cost is justified. These are research objectives, not completed contributions or claims of priority.

## 2. Related Work

`fact F03` PsyCoTalk uses binary threshold states and describes a simulator that returns negative answers for symptoms missing from its record or incompatible with its provisional diagnosis. [PsyCoTalk §4.1–4.2](https://arxiv.org/html/2510.25232v2)
`inference` That simulator rule should be distinguished from the proposed task's explicit unknown evidence state; the task definitions require reconciliation before a fair comparison.

`fact F05/F06` Context-Folding introduces learned branch-and-fold context operations, and Memory-R1 describes an RL manager for structured memory operations. [Context-Folding abstract](https://arxiv.org/abs/2510.11967v1), [Memory-R1 abstract](https://arxiv.org/abs/2508.19828v5)
`inference` Their existence motivates a comparison against learned general-memory policies; adding RL to a medical tree does not by itself establish a new research contribution. Full algorithm and reproduction requirements still need review.

`fact F08/F10` Training-free multi-head recurrent memory and contextual-intent retrieval offer further memory designs. [MHM abstract](https://arxiv.org/abs/2607.01523v1), [STITCH abstract](https://aclanthology.org/2026.findings-acl.584/)
`hypothesis` The proposed controller should be evaluated against these stronger alternatives, rather than only against truncation.

`fact F07/F09` MentalBench describes DSM-grounded synthetic cases with varied completeness and complexity; a human-centered depression annotation framework describes criterion-level evidence, expert revision, and dual memories. [MentalBench abstract](https://arxiv.org/abs/2602.12871v2), [Annotation framework §III](https://arxiv.org/html/2607.15202v1)
`inference` These works limit claims that diagnostic criteria, evidence slots, or expert feedback are new. The remaining candidate question is their behavior under matched budgets and controlled multi-turn revisions; the present search does not establish an unoccupied research gap.

## 3. Problem Formulation — proposed design

Let \(H_t=(u_1,\ldots,u_t)\) denote the observed dialogue prefix and \(K\) a fixed, versioned set of diagnostic conditions and dependencies. A memory controller constructs a visible representation \(M_t\). A frozen reasoner returns a label set \(\hat Y_t\), or an explicit abstention, from the current input, knowledge, and memory.

We propose to constrain the total reasoner input:

\[
\operatorname{tokens}(I,K_t,u_t,M_t)\le B,
\]

where \(I\) is the fixed instruction and \(K_t\) the knowledge supplied at that step. Retrieval results are part of \(M_t\), not an uncounted channel. Total system cost additionally includes extraction, management, retrieval, and generation calls. A larger-budget full-history condition would be reported separately as a reference.

The target hypotheses concern diagnostic quality, critical evidence retention, and revision behavior at matched budgets. No future turn, hidden case label, or evaluation annotation would be accessible to the controller. Prefix judgments would be evaluated against what the prefix permits, rather than against information revealed later.

## 4. Criterion-Preserving Memory — proposed design

### 4.1 Assertions and condition states

An assertion would include a condition identifier, its supporting or refuting direction, the observed turn, event-time scope, an exact source span, and an optional explicit revision link. Valid assertions would be appended to an audit store \(A_t\). The bounded working memory would be a selected representation of active assertions and unresolved questions.

For each condition, we propose the evidence states supported, refuted, unknown, and conflicted. These describe available evidence, not disease confirmation. Contradiction requires compatible condition and time scopes. Explicit corrections would supersede earlier assertions while preserving their audit history; a different episode would remain a separate observation.

### 4.2 Budgeted construction

The initial controller would be deterministic. It would prioritize unresolved critical conflicts and revisions, decision-relevant exclusions and negative evidence, temporal requirements, and other observed conditions before general narrative. Tie-breaking and serialization would be fixed before testing. When essential information cannot fit, the controller would record insufficient context and defer or abstain rather than silently discard a condition.

Compression would be evaluated for semantic preservation and recoverable provenance. A stable identifier would not substitute for the actual evidence needed by the reasoner. Where stored evidence is retrieved, both access and token cost would be shared with comparison methods.

### 4.3 Revision and dependency invalidation

When an active assertion changes, the controller would recompute affected condition states and invalidate decisions that depend on them. Revisiting a branch would follow this dependency update. We plan to test recovery after genuine corrections alongside negative controls in which a later statement should leave the prior interpretation unchanged.

### 4.4 Optional learned controller

H02 would evaluate a learned policy over feasible memory actions using the same frozen extractor, reasoner, historical access, and budget enforcement. A proposed constrained objective is:

\[
\max_\pi \mathbb{E}[Q],\qquad
\mathbb{E}[C]\le C_{\max},\qquad
\mathbb{E}[L_{\mathrm{critical}}]\le\delta.
\]

Here \(Q\) is case-level task quality, \(C\) cumulative system cost, and \(L_{\mathrm{critical}}\) loss of observed critical evidence. Constraints and reward weights would be selected using training/development data and frozen before test evaluation. Such constraints would not guarantee individual correctness or clinical safety. If the learned policy fails to improve on the deterministic controller, we would not claim an RL contribution.

## 5. Experimental Protocol — prospective

The full protocol is recorded in `05-experiment-design.md`. Candidate data sources require license and grouping checks before use. Source cases would be split before generating any variants, and related dialogues, rewrites, and perturbations would remain in the same split.

The primary experiment would replay identical dialogue inputs under a fixed backbone and budget. An interactive extension would then examine question-selection effects using a controlled case world and audited responses. Strong comparisons would include tuned summaries, retrieval, structured-tree controls, multi-head and intent-based memory, and faithful learned-memory implementations where feasible. Adaptations would be labeled as such.

The planned primary endpoint is diagnostic macro-F1 on complete replay at one preregistered budget against a development-selected strong baseline. Secondary analyses would measure critical evidence loss, four-state condition quality, unsupported updates, valid revision recovery, erroneous reversals, risk-coverage tradeoffs, and total cost. Paired source-case bootstrap intervals would preserve within-case correlations. The study would report infeasible budgets, errors, and failed runs.

Ablations would remove temporal scope, distinguishability of unknown and negative evidence, revision history, dependency invalidation, or condition alignment. Comparisons sharing the extractor would help isolate memory-management effects. Generalization checks would use a second model or source where permissions and resources allow.

## 6. Results — pending

No research results are available. The following is a reporting template, not an experimental table.

| Method | Budget | Diagnostic macro-F1, 95% CI | Critical evidence loss | Revision recovery | Total tokens/calls |
|---|---|---|---|---|---|
| Frozen strong baseline | To freeze | Not run | Not run | Not run | Not run |
| CPM-rule | Same budget | Not run | Not run | Not run | Not run |
| CPM-learned, optional | Same budget | Not run | Not run | Not run | Not run |

Planned figures: quality versus total cost; evidence loss versus dialogue length; recovery after valid revisions; negative-control reversal rate. Actual plots require real external result artifacts.

## 7. Limitations and Ethics — proposed scope

This protocol does not establish data access, ethics approval, diagnostic efficacy, or clinical usefulness. Synthetic case distributions, uncertain pretrained-data overlap, limited annotator agreement, extraction errors, and knowledge-tree transcription errors would constrain interpretation. Offline label agreement would not support claims about patient outcomes.

The workspace contains public references and researcher design notes, with no identifiable records or scanned book contents. Any subsequent sensitive-data processing must occur in an approved separate environment. Knowledge and dataset usage, derived artifacts, and redistribution require permission review. Generated labels and case variations must not be treated as independently validated clinical ground truth.

## 8. Conclusion — pending evidence

The proposed study asks whether diagnostic conditions can serve as an information-preservation contract for bounded, revisable memory. Its conclusions will depend on matched-cost comparisons and explicit failure criteria. Empirical conclusions and submission-ready wording remain pending.
<!-- research-os:generated:end -->
