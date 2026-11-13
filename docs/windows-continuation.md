# Continue native decomp on Windows

The fork contains the latest native source checkpoint: **3,396 matches /304,109
mapped bytes**. Read [fork status](fork-development.md), `AGENTS.md`,
[contributor setup](../contribute/README.md), [native status](native-reconstruction.md)
and the relevant subsystem evidence before editing.

## Get the checkpoint

In PowerShell, with Git and Python 3.13 installed, use a path without spaces:

```powershell
git clone https://github.com/jrwheels/psychonauts-decomp.git C:\dev\psychonauts-decomp
Set-Location C:\dev\psychonauts-decomp
git switch main
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r contribute/requirements-dev.txt
.\.venv\Scripts\python.exe -B contribute/tools/run_tooling_tests.py --report build/windows-tooling-001.json
```

For an existing checkout, preserve local edits first, then `git fetch origin` and
`git merge --ff-only origin/main` on your local main. A divergent branch needs
review; do not reset or overwrite it. Record `git rev-parse HEAD` for the handoff.
These Windows setup commands are provided for continuation; they have not been
executed on a Windows machine during this handoff.

## Private inputs and the build boundary

Supply your own supported Steam Windows PE32 executable privately. Verify:

```powershell
$env:REFERENCE = 'C:\private\Psychonauts.exe'
Get-FileHash $env:REFERENCE -Algorithm SHA1
Get-FileHash $env:REFERENCE -Algorithm SHA256
```

Expected SHA-1: `21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`.
Expected SHA-256: `cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.

Matching requires privately supplied VC++ 2008 RTM x86 **15.00.21022.08** and
unchanged `/Od /Oy /Ob1 /Oi /MD /GS-`. Keep the reference, compiler, original
assets and detailed reports outside public Git or under ignored `.local/`.
Git transfers the source and sanitized evidence; private machine inputs remain
on the Deck and must be supplied separately if needed on Windows.

The current strict build wrapper uses Linux/Wine and explicitly rejects WSL;
the full verification driver also assumes that build path. Native Windows full
verification is not yet implemented/validated. Source inspection and Python
analysis can continue on Windows; before accepting new matches, adapt and verify
the compiler invocation on Windows or reproduce with the established Linux/Wine
workflow. Do not replace the compiler with a modern MSVC version or bypass checks.

## Resume prompt

```text
Continue pure Psychonauts native decomp in this checkout. Read AGENTS.md,
contribute/README.md, docs/fork-development.md, docs/native-reconstruction.md,
docs/native-boyd-actions.md and docs/native-script-state.md.
Baseline: 3,396 functions /304,109 mapped bytes; all old matches must survive.
Inspect Git status and preserve existing work. First validate the Windows Python
checks and identify the native compiler/verifier portability work. Do not claim
a Windows native full build until it actually passes.
Next bounded research target: instruction dispatcher 0x00441240 (animation
opcode 1 and Lua opcode 3), then direct LoadAnim_impl 0x005c3520.
Keep CurrentState context switching, audio sync and gameplay gaps explicit.
Use only privately supplied hash-gated reference and pinned RTM compiler.
No exporter/costume/ReSkate work, game launches, installation/save changes,
commits or pushes unless separately requested.
```
