# Function ownership and issue workflow

Suggested labels (maintainer-created; documentation does not create them):
`area:native`, `area:tooling`, `area:docs`, `status:available`, `status:claimed`,
`status:blocked`, `status:review`, `ai-assisted`. AI use does not change acceptance.

1. Search canonical addresses in open issues, PRs, the map and evidence before
   claiming. Use the native-reconstruction issue template for one function or a
   bounded related batch. Include both reference hashes and exact base commit.
2. State subsystem value, dependencies, affected source/shared headers, current
   evidence and estimated scope. Request ownership; a maintainer assigns the issue
   and marks it claimed after checking overlap. An unassigned request is not exclusive.
3. Coordinate dependencies and shared layouts before edits. One writer per shared
   file/batch; separate worktrees do not eliminate semantic merge conflicts.
4. Post a concise progress/blocker note at least weekly. After 14 inactive days,
   maintainers ask for status and allow seven days before releasing the claim.
   Preserve partial work and evidence links; do not overwrite someone else's effort.
5. Mark blocked when evidence/toolchain/dependencies prevent progress, with the
   exact failed method and next useful observation. Unclaim promptly when stopping.
6. Link the PR and change status to review. Maintainers reproduce native evidence,
   review publication scope and close the issue only after acceptance.

Addresses plus reference hash define the claim; provisional method names do not.
Never paste proprietary binaries, raw dumps or private transcripts into an issue.
