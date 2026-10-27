# Agent rules for chinese-ocr-qa

Read `docs/AGENT_HANDOFF.md` first, then `docs/DATA_FORMAT.md` before any training-data change. This is the standalone public `Tiachi/chinese-ocr-qa` project, not the entire private Dataset repository.

- Commit only code, tests, example configuration, small nonsensitive manifests and docs. Never commit datasets, training QA, images, LMDB, caches, weights, credentials, private keys, signed URLs or raw logs.
- Preserve all original annotations/media. Derived files use no-clobber staging and provenance receipts.
- Do not correct OCR spelling/grammar or fabricate answers to exam questions. Different handwriting with the same label is not an image duplicate.
- Keep70%OE/30%MCQ after filtering, balanced MCQ letters and nine-source coverage; report capacity shortfall explicitly.
- Model text-only checks do not prove image/text alignment; uncertain API requests cannot be silently repeated.
- No personal proxy by default. Only explicit user authorization allows its use. Read-only proxy inspection never authorizes proxy traffic.
- Do not modify system DNS or disable TLS verification to fix download failures.
- Canonical public origin: `https://github.com/Tiachi/chinese-ocr-qa.git`; main is stable. Do not change the visibility of other repositories or copy private history here.
- Stage exact files only. No add-all, automatic stash/reset/clean or force push. Use clean, fast-forward synchronization.
- Code and config are separate; preserve existing server configuration and caches when migrating. Server worktree path is proposed, not proof of deployment.
- Separate implemented, locally tested, user-reported server tested and production verified results. Read the current state in the handoff; do not declare the dataset built.
