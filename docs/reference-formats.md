# Original-format reference research

These source tools are preserved from the original Psychonauts asset investigation
because they help inspect resource, mesh, hierarchy, animation and collision evidence.
They are separate from matching native C++ and are not a replacement engine. No
original models, textures, archives, animations or generated exports are distributed.
The included tests construct synthetic bytes/numbers; they never open installed games.

## Included utilities

| Utility | Use and boundary |
| --- | --- |
| psyassets.py | Steam PPAK/CYSP metadata, scene/mesh records and bounded primitives; adapted MIT noclip decoder |
| psyinventory.py | Read-only owned-archive inventory; names reported by PKG reader remain unverified |
| psyexport.py | Experimental geometry/texture/collision glTF inspection exports; not faithful complete levels |
| psyrig.py / psyanim.py | Rig math, palettes and bounded JAN variants; unsupported/malformed variants fail |
| psymorph.py | Reference blend/texture record helpers; not verified native runtime morph semantics |
| psynav.py | Collision-linked navigation evidence; visibility/scene tails remain incomplete |
| glb_skin.py / glb_preview.py | CPU skin inspection and simple textured preview; not the game's renderer |
| third_party/psypkg.py | Attributed index reader; supported integration uses read_index only, not mount/unpack |

Install `requirements-reference.txt` for these tools. `contribute/requirements-dev.txt` includes
it so public synthetic tests cannot silently skip this coverage. NumPy 2.2.6 is pinned
for Python 3.10/3.11; 2.5.4 for Python 3.12+, with Pillow 12.3.0. Both matrix Python
versions must be tested after changing numerical dependencies.

```sh
python -m pip install -r requirements-reference.txt
python -B tools/psyinventory.py "$OWNED_GAME" --output .local/assets/inventory.json
python -B tools/psyexport.py "$OWNED_PACK" --common "$OWNED_COMMON_PACK" \
  --model "$MODEL_NAME" --output .local/assets/inspection.glb
python -B tools/glb_preview.py .local/assets/inspection.glb --output .local/assets/preview.png
```

Set variables locally to your own inputs; do not publish them or outputs. Entry
points constrain generated exports to ignored `.local/assets/`. Library APIs are
intended for trusted owned data, not a hardened untrusted-file service. Do not run
third-party extraction/mount commands or modify an installation for native matching.

Preserve original identifiers, raw metadata and hierarchy in private analysis.
Scene export currently bakes positions and uses identity transforms; serialized TRS
are metadata. Collision remains separate. Raw quaternion interpolation, unknown
animation tails, descending-time keys, shader/lightmap behavior and dynamic transform
rules have known gaps. A structurally valid glTF or parsed record is not faithful
runtime behavior. Consult [model findings](model-format-findings.md) for where native
CYSP/version/dependency evidence is stronger than permissive file-format guesses.
[Attribution](../third_party/README.md) records the included licenses. Destination
costume fitting, Blender packaging, Studio automation and mod installation are excluded.
