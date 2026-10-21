# Publication safety

Review an explicit file list before staging; review the index before commit and
the outgoing history before push. `.gitignore` is convenience, not an enforcement
boundary: tracked or force-added private files can still be published. Keep game
references, original archives/assets, compiler components, Wine prefixes, analysis
DBs, object files, local reports, credentials and transcripts outside public Git.
Original reconstruction source and synthetic tests still require attribution review.

```sh
python -B contribute/tools/publication_check.py --worktree
python -B contribute/tools/publication_check.py --paths-from build/public-files.txt
python -B contribute/tools/publication_check.py --staged
python -B contribute/tools/publication_check.py --tree HEAD
python -B contribute/tools/publication_check.py --history BASE..HEAD
```

No mode changes Git/files. `--staged` (default) scans the entire index blobs, not
working copies; it catches force-added ignored files. `--worktree` scans tracked
and nonignored new files. `--paths-from` reviews an explicit newline-separated
candidate list; deleted paths should not appear. Tree mode inspects the full
snapshot. History mode inspects every commit snapshot and commit record in the
range, catching files removed or renamed later. Use `--history HEAD` for all
reachable history. This can be slower than a current-tree check.

Rules detect common credential/key markers, personal absolute host paths, transcript
records, private/generated directories, compiler/game/archive extensions, excluded destination-modding/session-tool paths, executable
or archive signatures/NUL bytes, symlinks/submodules and artifacts over 1 MiB.
Findings include paths, rule IDs and Git object IDs, not matching contents. Treat
path names themselves as potentially private; do not upload detailed findings.
No suppressions are provided: resolve findings or obtain an explicit reviewed policy
change. Avoid putting real-looking secrets in test source; construct synthetic markers.

This is a conservative heuristic, not a secret manager, malware scanner, license
review or proof of no proprietary content. Encoded secrets, unrecognized personal
paths and renamed textual compiler headers can escape detection. Inspect every
proposed public diff and ownership/attribution manually. A clean tree cannot clear
an unsafe history. Do not rewrite existing history without separate authorization.
Publish only the reviewed branch/range; never push all refs or mirror a research
checkout. If an actual credential is exposed, stop publication and notify its owner privately.

Public CI scans its tree/history and runs synthetic fixtures on GitHub-hosted
runners with read-only repository permission, no proprietary inputs/secrets and no
artifact uploads. It never uses a privileged pull_request_target job or a private
self-hosted runner for untrusted contributions. Native matching still needs private
maintainer reproduction. A proposed workflow is not tested on hosted GitHub until
explicitly approved publication; local equivalent commands are the current evidence.
