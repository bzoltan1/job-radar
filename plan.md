# Code review plan

Source: /code-review high. Items 1-11 verified by reading; 1, 4, 5, 8 reproduced. One item at a time; mark `[x]` when done.

## Bugs
- [x] 1. `db.upsert_job` dropped the semantic bonus each sync. Fix: carry over `semantic_score` + `semantic:` tag, add to score (review rejected the first fix, reset to pending: with embed batch 100, jobs beyond top 100 would never be re-embedded).
- [x] 2. `cmd_sync` deactivates jobs but only the `db` sink re-activates. Fix: `db` sink always runs first. Open: sinks still see in-memory `job.score` without semantic bonus (see 7); upsert happens after all targets, so a crash mid-loop leaves earlier companies inactive.
- [x] 3. telegram: sort by score, send in chunks of 8, mark only delivered chunks notified, escape URL. Shortcut: chunk by count, not 4096 chars.
- [x] 4. location: `eu`/`european union` added to geo regex; bare "Fully Remote"/"100% remote" treated like "Remote" (emea_remote). Other keyword-only remotes with no region (e.g. "Remote - Peru") are still dropped.
- [x] 5. `go`/`c` tech patterns: case-sensitive, tech-context heuristic (built-in for plain `go`/`c` entries; example yaml uses them). Open: your gitignored data/tech_stack.local.yaml still has the old `\b(golang|go)\b` pattern; replace with plain `go` and `c`.
- [x] 6. obsidian: unique note names per job (plain name for first claimant, hash suffix otherwise; `job_id` in frontmatter), JSON-quoted YAML values, dossier/link names sanitised. Open: stale notes of inactive jobs are never archived (`update_frontmatter_for_archive` is unused).
- [x] 7. `snapshot` sinks (rss, obsidian) get all stored active jobs (`job_from_row`); other sinks get stored scores (`apply_stored_scores`); desktop announces only jobs first seen this sync (`new_job_ids`) unless `--force-notify`. Open: desktop dedupe is per-run, not persisted; `radar.py top` still reads DB (unchanged).
- [x] 8. `parse_job_date`: epoch s/ms, tz-aware -> UTC; Greenhouse uses `first_published` (verified on live cloudflare board) with `updated_at` fallback. Open: other sources (Workable, Recruitee, Deel, SmartRecruiters) not audited for date semantics.
- [x] 9. semantic pillars: cache keyed by text hash, removed pillars deleted, any change re-queues jobs (re-embedded 100 per `embed` run). First run after upgrade re-embeds once (new `text_hash` column is empty).
- [x] 10. config: broken/missing settings, profile, tech-stack files raise `ConfigError` naming the file; bad intel dossiers warn on stderr. Open: `load_dotenv_if_present` and Telegram legacy-json still swallow errors; `load_targets`/`load_countries` raise raw yaml errors.
- [x] 11. Accept-Language neutral; Amazon search terms from target `queries`/`country_queries` (your targets.local.yaml updated to keep current behaviour); personal systemd unit untracked + gitignored (example path generic). Decided NOT to externalise title/role persona regexes (systems/SRE defaults are generic role vocabulary, not personal data; needs a design call if you want per-profile role patterns). Project UA URL kept (public repo URL).

## Refactors
- [x] db.py: single `upsert_job` statement; `update_job_status` = exact id first, then active+best-score title match, `%`/`_` escaped; `struct` import hoisted.
- [x] cli.py: `set_defaults(func=...)` dispatch; `apply` is an alias of `status <job> applied` (`cmd_apply` removed); `status` choices from `VALID_STATUSES`; `cmd_embed` imports hoisted. NOTE: your data/intel.local/dynatrace.yaml has a YAML error (line 32) that was silently skipped before.
- [ ] Salary extraction: module-level regexes, one currency helper, fix lowercase `eur`/unknown-currency fallback.
- [ ] `LocationStage.process`: split classifier / scorer.
- [ ] Dead/fragile: `title.py` `get_tech_stack_re`/`TECH_STACK_RE`; combined tech regex inline flags; `workday.py:job_prefix`; `profile.py` magic `/80` + unguarded regex; class-in-loop in `sources/__init__.py`.
- [ ] Fetch layer: `http_get_json` + `FetchError`; drop `[]` shortcut in `cmd_sync`; Workable per-job requests; Workday 100 cap.
- [ ] Split `--min-score` into store vs notify thresholds.
- [ ] Move `PEER_CATALOG` to data file.
