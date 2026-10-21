# Reference-format attribution

`tools/psyassets.py` adapts the original Psychonauts PLB/PPF numerical-layout
research from noclip.website. Preserve `noclip-LICENSE.txt` (MIT) and
`noclip-sources.json` (source URLs and retained source hashes). This directory
contains no game assets or external renderer implementation.

`psypkg.py` is Mathias Panzenböck's original permissively licensed reader from
panzi/psypkg commit `59c97f1f84621d53654980828f4b1af8c63cd135`. Its complete
notice is retained in the file, which is byte-identical to the reviewed local
copy. `psyinventory.py` uses only `read_index`; package names are unverified.
The third-party unpack/mount CLI is outside the supported workflow and must
not be used on untrusted paths. llfuse is optional and unnecessary for indexing.

No read-only research clones or GPL SDK helpers are vendored here. Source and
license review do not establish fidelity of exported geometry or runtime loaders.
Python dependencies are installed from pinned manifests, not redistributed as
binaries. Existing root MIT and Lua COPYRIGHT notices remain intact; they do
not grant redistribution permission for game/compiler inputs or outputs.

The scoped .gitattributes whitespace setting preserves upstream blank-line tabs
in psypkg.py without rewriting its reviewed bytes; it does not relax checks for
project-authored files or normalize engine source.
