# Code review plan

Source: /code-review high. Items 1-11 verified by reading; 1, 4, 5, 8 reproduced. One item at a time; mark `[x]` when done.

## Bugs
- [x] 1. `db.upsert_job` dropped the semantic bonus each sync. Fix: carry over `semantic_score` + `semantic:` tag, add to score (review rejected the first fix, reset to pending: with embed batch 100, jobs beyond top 100 would never be re-embedded).
- [ ] 2. `cli.cmd_sync` deactivates jobs, only `db` sink reactivates. `--sinks rss` wipes active set; `telegram,db` never alerts new jobs. Fix: upsert in `cmd_sync` before sinks.
- [ ] 3. `telegram_sink`: sends first 8 unsorted, marks all notified. Fix: sort by score, chunk, mark only sent; escape URL.
- [ ] 4. `pipeline/location.py`: "Remote (EU)", "Fully Remote" dropped. Fix: add `eu|european union` to geo regex; decide keyword-only remote handling.
- [ ] 5. `go` / `c` tech regexes match plain English (config.py, data/tech_stack.example.yaml). Fix: case-sensitive/context-bound.
- [ ] 6. Obsidian filename collisions + unescaped YAML frontmatter + unsanitised dossier filenames.
- [ ] 7. rss/obsidian/desktop sinks built from per-run jobs only; desktop ignores `notified_at`. Fix: build from `get_active_jobs()`.
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
