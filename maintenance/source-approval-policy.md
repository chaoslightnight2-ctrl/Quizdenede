# Source approval and publication contract

Every factual publishing field needs a separate editorial evidence row. News
includes title, hook, description and each narration part. Fact videos include
title, description and each factual scene. Quiz includes question, answer and
explanation; the independent answer must also match the proposed answer after
normalization. Missing, duplicate, unknown, unsupported or invented evidence
cannot produce approval. Quotes must occur in the exact supplied source.

The existing editor call returns this ledger; no extra model pass is added.
After checks, SHA-256 digests bind the exact fields, source, editorial decision,
prepared speech/TTS and relevant publishing metadata. Active upload gateways
recompute the contract before OAuth or insertion. Fact videos also recheck after
rendering. Old boolean-only caches do not meet the current contract and must be
regenerated. A changed cache or script cannot retain its old approval.

These digests detect accidental changes. They are not signatures and do not
protect against an actor editing code or deliberately recreating the digests.
Per-field evidence is not proof that the publisher is correct or that the model
understood every sentence correctly. Automated semantic accuracy cannot be
guaranteed. The enforced properties are coverage, literal quotation, an explicit
editorial decision and unchanged approved publication data.

Unreviewed legacy upload entry points now reject publication. The old root
fact-video generators also stop before spending model quota or using canned
fallbacks; the scheduled protected freefaceless pipeline remains the entry point.

Text-only audits stop on saved cooldowns and allow at most two Groq HTTP attempts
for generation and review combined. Repair retries share that allowance. They
cannot render or upload and preserve raw responses and source inputs for manual
inspection. An audit failure is not a successful content validation.
