# Code review plan

Source: /code-review high. Items 1-11 verified by reading; 1, 4, 5, 8 reproduced. One item at a time; mark `[x]` when done.

## Bugs
- [x] 1. `db.upsert_job` dropped the semantic bonus each sync. Fix: carry over `semantic_score` + `semantic:` tag, add to score (review rejected the first fix, reset to pending: with embed batch 100, jobs beyond top 100 would never be re-embedded).
- [x] 2. `cmd_sync` deactivates jobs but only the `db` sink re-activates. Fix: `db` sink always runs first. Open: sinks still see in-memory `job.score` without semantic bonus (see 7); upsert happens after all targets, so a crash mid-loop leaves earlier companies inactive.
- [x] 3. telegram: sort by score, send in chunks of 8, mark only delivered chunks notified, escape URL. Shortcut: chunk by count, not 4096 chars.
- [x] 4. location: `eu`/`european union` added to geo regex; bare "Fully Remote"/"100% remote" treated like "Remote" (emea_remote). Other keyword-only remotes with no region (e.g. "Remote - Peru") are still dropped.
- [x] 5. `go`/`c` tech patterns: case-sensitive, tech-context heuristic (built-in for plain `go`/`c` entries; example yaml uses them). Open: your gitignored data/tech_stack.local.yaml still has the old `\b(golang|go)\b` pattern; replace with plain `go` and `c`.
- [x] 6. obsidian: unique note names per job (plain name for first claimant, hash suffix otherwise; `job_id` in frontmatter), JSON-quoted YAML values, dossier/link names sanitised. Open: stale notes of inactive jobs are never archived (`update_frontmatter_for_archive` is unused).
- [ ] 7. rss/obsidian/desktop sinks built from per-run jobs only; desktop ignores `notified_at`. Fix: build from `get_active_jobs()`. Also: sinks use in-memory `job.score` (no semantic bonus) – read stored score instead.
- [ ] 8. Lever `createdAt` (epoch ms) unparsed; Greenhouse uses `updated_at` as posted date.
- [ ] 9. Semantic: stale pillars returned; profile change never re-queues jobs.
- [ ] 10. `config.py` swallows all exceptions → silent 0% matches on bad YAML.
- [ ] 11. Personal data in committed code (UA, Accept-Language, Amazon queries, persona regexes, systemd path).

## Refactors
- [ ] db.py: merge two `upsert_job` statements (`COALESCE(?, CURRENT_TIMESTAMP)`); deterministic `update_job_status`; hoist `struct` import.
- [ ] cli.py: `set_defaults(func=...)` dispatch; merge `cmd_apply` into `cmd_status`; hoist `get_db` import in `cmd_embed`.
- [ ] Salary extraction: module-level regexes, one currency helper, fix lowercase `eur`/unknown-currency fallback.
- [ ] `LocationStage.process`: split classifier / scorer.
- [ ] Dead/fragile: `title.py` `get_tech_stack_re`/`TECH_STACK_RE`; combined tech regex inline flags; `workday.py:job_prefix`; `profile.py` magic `/80` + unguarded regex; class-in-loop in `sources/__init__.py`.
- [ ] Fetch layer: `http_get_json` + `FetchError`; drop `[]` shortcut in `cmd_sync`; Workable per-job requests; Workday 100 cap.
- [ ] Split `--min-score` into store vs notify thresholds.
- [ ] Move `PEER_CATALOG` to data file.
