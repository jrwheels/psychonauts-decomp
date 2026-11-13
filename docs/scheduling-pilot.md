# Native scheduling pilot — 7 November 2026

Canonical project: psychonauts-decomp. Native worktree:
`.local/worktrees/native-pack-strings-20261021`. Asset extraction remains the
priority: humanoids, environments, then other creatures. No permanent scheduling,
source, map, toolchain or verification changes were made.

## Protocol and target eligibility

Reviewed native-workflow.md, matching-acceleration.md, reconstruction-tools.md,
current native status and existing ranking/planning/verifier implementations.
Reused native_workflow.py rank and native_index.py target-only; no replacement queue.
Three separate copies included the same dirty sources and existing supporting
objects; workers wrote only their own private copies. One fresh agent processed
both targets sequentially; then two fresh agents processed one each. Model/effort
were inherited, without forked conversation context. Workers were told not to read
other arms. Each target had a 150-second active budget and the same tool paths.

The mesh rank produced candidate 0x00418c80 (13 bytes) and 0x00494c10 (11 bytes).
Both have no observed direct dependencies/indirect calls and heuristic distance2
from mesh seeds. Original-byte disassembly in all arms identifies empty member
bodies, with no asset reads, fields or calls. Neither establishes an extraction
blocker. They were therefore screened out before reconstruction or compilation.
This failed eligibility gate means **no comparable asset-relevant reconstruction
benchmark was completed**. The timing below is screening only.

| Measurement | One worker | Two workers |
|---|---:|---:|
| Worker span, first target start to last target end | 31.03s | 34.05s |
| Aggregate worker elapsed time | 31.03s | 59.57s |
| Dispatch to coordinator completion observation | 62.98s | 73.11s |
| Compile / target verification | Not run | Not run |
| Accepted matching bytes | 0 | 0 |
| New recovered assets | 0 | 0 |
| AI tokens | Unobservable | Unobservable |
| Source integration | None | None |

Per-target serial screening: 15.36s /15.67s. Parallel: 33.51s /26.06s.
Index times were ~0.44s each (parallel second target ~0.46s). Snapshot creation
cost 1.25s and fresh ranking 14.81s. A separate read-only full-object preservation
comparison took 11.53s across 66 objects, retaining **3,392 matches /303,542 bytes**,
zero new addresses and **zero regressions**. Those are preservation costs, not
new-function acceptance. No fresh full build or behavioral suite was needed for
screening without code changes. All 185 protected source/map/tool/test files and
66 canonical object hashes remain unchanged relative to the frozen snapshot.

## Interpretation and next experiment

One trial, fixed arm order, warm filesystem/tool caches, model variability,
different worker startup/observation delays, unequal prompt packaging (one two-task
prompt versus two single-task prompts), unobserved token usage and no accepted work
prevent a throughput-per-token conclusion. Worker elapsed time is not an AI-cost
measurement. The dispatch totals include coordinator observation latency. Concurrent
Wine/compilation safety and contention were not exercised; do not infer them from
successful concurrent read-only screening. No speedup ratio is promoted.

Reusing the *same* targets controls body difficulty, but these targets lack useful
asset relevance. The documented recursive joint reader 0x00455200 (279 bytes),
animation-stub reader 0x00495e60 (482 bytes) and CYSP parser 0x0047b980 (1,911 bytes)
are more relevant candidates for investigation, yet have different complexity,
shared layout/stream/resource dependencies and prior blockers. They are not a
reviewed independent matched-difficulty batch, and unchanged blocked probes must
not be rerun merely for timing. No complete asset benefit is established by
matching one of those bodies alone.

Further parallel reconstruction remains unproven. First connect concrete current
humanoid/scene export failures to independently bounded original functions, review
shared headers/callees and define measurable asset/byte acceptance. Only then
repeat a counterbalanced serial/two-worker experiment with token telemetry and
existing strict full verification at integration. Continue batch extraction of
already supported assets independently. No scheduler installation or permanent
coordination code is justified by this pilot.

Private raw timings, frozen copies, disassembly, protocol and preservation reports:
`.local/scheduling-experiment-20261107/`. The prior 9.49x matcher-phase result is
historical and is not counted as a new result here. No games, installations,
commits, pushes or publication. Next action: asset-blocker attribution, with native
scheduling subordinate to the extraction handoff.
