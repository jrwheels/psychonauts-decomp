# Fork development checkpoint

The lean upstream contribution and this fork have separate scopes.

- Upstream source-only branch: reviewed 3,375 engine functions /300,735 bytes,
  based on upstream `6959341`; only src/game and the two engine progress files.
- This fork: 3,389 functions /303,359 bytes, preserving every published match.
  The 14 additional unique canonical matches add 2,624 bytes; this includes the
  previously local cache lookup and the later dependency campaign. Compiler-
  generated support matches are distinguished in the campaign report.
- Fresh full native verification: 66 compiling sources, zero regressions,
  12,124 differential cases and 44 separate original-only cases. Required native
  tooling passed; optional Rust tests were not requested in this reproduction.
- After integrating asset tooling and near-match diagnostics, 105 required
  synthetic tooling tests pass without skips. The compiler, native source/map
  inputs and differential suites remain identical to the fresh native run.

The fork retains the contributor infrastructure, tests, diagnostic classifier,
source-format tools, export correctness fixes, bounded survey and documentation.
The published contributor-directory layout is retained. Asset tooling is backed
by the earlier documented original-data and Blender checks; no new asset exports
or gameplay tests were performed merely for publication.

Incomplete recursive-joint compiler experiments, private diagnostic inputs,
original executables/assets, compiler files, detailed reports and the paused
untested resumable export runner remain preserved locally. They are not promoted
as verified engine reconstructions or public-ready tools. An unmatched but
behavior-tested helper remains unmatched in the canonical map.

Future priority remains practical, reusable extraction: independent format
validation, GLB geometry/rigs/material relationships, bounded multi-asset surveys
and clearly documented environment/animation limits. No linked/playable engine
or Godot/Unity/Unreal runtime compatibility is claimed.
