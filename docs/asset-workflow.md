# Original asset research workflow

Use personally supplied original archives and the hash-gated supported Steam
Windows executable. Do not distribute game assets, extracted outputs, binaries,
or private reports. Keep outputs under ignored `.local/assets/` or `build/`.
Install the dependencies in `requirements-reference.txt`; original-code controls
also require the development dependencies in `contribute/requirements-dev.txt`.

## Coverage and validation

`tools/asset_manifest.py` inventories source resources. `tools/export_coverage.py`
accepts a bounded JSON plan and maintains separate parsing, export, source,
texture, animation, glTF and Blender results. Use `--help` for explicit input
paths. Completed attempts are hash-checked before reuse; retries preserve earlier
attempts. Prioritize character models, rigs, textures and variants before broader
animation coverage. LOD selection does not multiply unique source coverage.

`tools/check_bind_pose.py` independently checks serialized bind transforms and
inverse bind matrices. `tools/asset_survey.py` can resolve exact named APF/JAN
references; compatible skeletons alone do not establish character ownership.
`tools/blender_boyd_check.py` checks imported bind poses and sampled animation;
run it with Blender's Python. `tools/check_model_export.py --collision` compares
raw collision positions and indices, without claiming physics equivalence.
`tools/scene_relationships.py` retains placement/material evidence without
inventing runtime transformations.

## Bounded facial-animation research

`tools/pba101_research.py` and `tools/original_reader_pba.py` compare isolated
channel decoding, mapping and timing. `tools/original_dialogue_pba.py` exercises
bounded original dialogue/fade/stop paths with explicit adapters for Lua access,
ready resources, allocation and sound services. `tools/probe_dialogue_face.py`
exports one Milla dialogue case; `tools/blender_dialogue_check.py` independently
checks that export. These are research tools, not complete engine reconstruction.
The production facial-animation version gate remains unchanged. General mixed
layers, asynchronous loading, actual audio timing, root motion, event playback,
and original renderer fidelity remain unverified.

Run synthetic checks with:

```sh
python -B contribute/tools/run_tooling_tests.py
```

The separate original-only controls need a privately supplied reference:

```sh
PSYCHONAUTS_REFERENCE="$REFERENCE" PYTHONPATH=tools:tests \
  python -B -m unittest discover -s reference_tests -v
```

No game launch is needed. Original-only checks are not part of public CI and
must not be reported as synthetic coverage. Output/report paths can contain
private information and must stay out of Git.
