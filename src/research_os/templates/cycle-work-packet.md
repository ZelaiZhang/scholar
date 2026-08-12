# Supervised research cycle: {{RUN_ID}}

Project: `{{PROJECT_SLUG}}`  
Idea limit: {{MAX_IDEAS}}  
Provider-call limit: {{MAX_CALLS}}

Reserved Idea IDs: {{RESERVED_IDEA_IDS}}
Suggested first ID: {{SUGGESTED_IDEA_ID}}

This run is guidance-only. Do not execute training, evaluation, shell experiment,
or clinical actions. Do not store hidden reasoning or chain-of-thought. Record only
concise conclusions, evidence locators, uncertainties, and reproducible search terms.

## Artifact contract

1. Write candidates to `candidates.yaml`; every Idea remains `draft` and cites only
   sources linked to this project.
2. Document novelty in the same candidate records with reproducible queries, at
   least one registered nearest source, and a concrete difference.
3. Keep `reviews/novelty.json`, `reviews/methods.json`, and
   `reviews/medical-safety.json` independent. No review may select an Idea.
4. Write `meta-review.json` only after all three reviews validate. It may shortlist,
   but it may not select.
5. Stop at human approval. Only `research-os approve-idea` may create `selected`.

After writing exactly the requested artifact, run `research-os cycle --project
{{PROJECT_SLUG}}` again and follow its single reported next action.
