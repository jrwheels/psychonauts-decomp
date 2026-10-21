> Historical verification record; the complete publication candidate includes this work.
> Current coverage/results are in [native status](native-reconstruction.md) and [publication scope](publication-scope.md).

# Clean native verification and published-history review

On 2026-10-20, a detached clean checkout of published commit `8154808` was
built and tested using the existing, hash-verified Steam executable and VC++
2008 RTM toolchain. No old objects, test results or cached differential cases
were used. The optional Rust library was rebuilt from tracked source; its hash
reproduced the prior library exactly.

| Check | Fresh result |
| --- | ---: |
| Strict C/C++ build | 62 objects, all compiler exits successful |
| Tooling tests | 29 passed, none skipped |
| Original/rebuilt differential suites | 23 passed / 6,490 cases |
| Original-only CYSP header fixtures | 44 passed, counted separately |
| Full relocation-aware matches | 3,360 functions / 298,986 mapped bytes |
| Previously matching addresses lost | 0 |

The strict build took 14.67 seconds. Rebuilding the Rust library took 0.74
seconds. All tests and the comparison took 130.22 seconds, including 11.70
seconds for the full comparison. This is a single local reproduction, not an
independent third-party result or a statistically controlled benchmark.

[Verification metadata](native-clean-verification.json) binds the source commit,
reference hashes, compiler flags, counts, timings and report hashes. Detailed
reports remain under ignored `build/clean-review-20261020/`. They are deliberately
not distributed as game-dependent build artifacts. The status page contains the
commands needed to repeat the checks with an owned reference and toolchain.

The run establishes object matching and bounded original/rebuilt x86 behavior
with mocked services. It does not establish linking, a playable engine, physical
file I/O, complete resource parsing, renderer behavior or game integration. The
44 original-only cases are not verification of reconstructed parser source.

## Privacy and attribution scope

A read-only scan covered every Git object reachable from the published commit:
31 commits and 428 blobs, totaling 25,176,510 bytes. The scan inspected commit
identity metadata, home/user path patterns, common credential/private-key markers
and executable/archive signatures. It did not rewrite history.

No secret-marker matches, executable/archive signatures, personal home-directory
paths or ordinary commit author/committer emails were detected. Five historical
email findings belong to inherited Lua project contact headers. They are
upstream attribution, not an owner personal email; retain them and the original
licenses. Public GitHub noreply identities still identify their public accounts.
Original game development paths/assertion strings are distinct from private
host paths.

This is heuristic coverage, not proof of complete anonymity or absence of every
possible secret or proprietary byte sequence. Encoded secrets, unsupported file
signatures and unrecognized personal information can escape such a scan. The
scope is published `main` history, not ignored local research or private worktree
branches. Redacted detailed findings remain ignored.
