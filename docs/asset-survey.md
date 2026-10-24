# Bounded archive inventory and export survey

The preceding correctness checkpoint was verified before work: 12 staged source
hashes, 344 private evidence hashes, recovery copies and all 259 accepted Boyd
files matched. Existing local history consistently uses `Codex <codex@localhost>`;
that identity was reused through command-local Git options for commit `892338d`.
No global/local Git configuration or remotes were changed. Work remains on
`asset-export-correctness`; nothing is pushed or published.

## Accounting and scope

The manifest indexes 50 PPF archives, 50 APF archives and one PKG from the owned
Steam PC installation. PPF texture scope is locale-0/shared records; other
localizations, PPF script groups, sound/video banks and unrelated installations
are not fully inventoried. All archive hashes and occurrence offsets/IDs remain
private. PKG reader paths are unverified hints, not stable identities.

Record occurrences, unique content and normalized named families are separate.
Identical model/animation payloads deduplicate by SHA-256. Texture identity uses
known format/dimensions plus complete encoded surface bytes: archive-local
headers otherwise make all 16,789 records appear different. Every original
texture record hash is retained. Different encoded variants remain distinct;
this is not perceptual image deduplication. Skeletons, collision and material
descriptors use explicitly marked canonical metadata identities, excluding
storage offsets. Embedded APF facial/event chunks add 3,609 occurrences but no
new unique payloads beyond the indexed PKG content. LODs are export variants,
not additional source assets.

Parsed means accepted by the current decoder and its checks. CYSP scene tails,
full runtime behavior and original shaders remain outside that claim. PPF
texture parsing checks complete mip/face record coverage where supported; DDS
parsing here is only Pillow base-image decoding. Exported/validated counts below
are unique source resources from **this batch**, excluding inherited exports.

| Category | Records | Unique | Parsed | Exported | Source + glTF validated |
| --- | ---: | ---: | ---: | ---: | ---: |
| Static models | 2,985 | 1,216 | 1,216 | 3 | 3 |
| Skeletal models | 2,290 | 447 | 447 | 3 | 3 |
| Skeletons, derived | 2,348 | 341 | 341 | 3 | 3 |
| Unclassified model failures | 48 | 31 | 0 | 0 | 0 |
| Skeletal animation payloads | 3,975 | 3,934 | 3,916 | 3 | 3 |
| Facial animation payloads | 10,928 | 7,767 | 1,873 | 0 | 0 |
| PPF textures | 16,789 | 6,052 | 5,784 | 272 | 272 |
| PKG DDS textures | 589 | 588 | 588 | 0 | 0 |
| Material descriptors, derived | 31,979 | 9,219 | 9,219 | 425 | 425 |
| Serialized environment scenes | 49 | 49 | 49 | 3 | 3 |
| Collision meshes, derived | 920 | 535 | 535 | 3 | 3 |
| Animation event payloads | 1,141 | 320 | 319 | 0 | 0 |
| Animation reference descriptors | 8,301 | 2,731 | 2,731 | 0 | 0 |
| Other indexed resources | 377 | 375 | Not attempted | 0 | 0 |

These rows overlap by containment: a model owns skeletons/materials, and scenes
own collision. Do not sum them into a single library-asset total. Texture exports
are selected base mip/frame PNGs embedded in GLBs, not complete animated textures.
Material validation covers source parameters and texture assignment, not shader
equivalence. Parser coverage of models is 1,663/1,694 unique payloads (98.17%);
this is **not** a whole-library export success rate. The sample is intentionally
biased toward tractable resources and includes one known unsupported control.

## Representative results

The public plan is [asset-survey-plan.json](asset-survey-plan.json). No Boyd model
was exported in this batch.

| Example | Vertices | Triangles | Result |
| --- | ---: | ---: | --- |
| Asylum heater | 597 | 610 | Textureless material; fixed schema failure, validated/imported |
| Loboto disguise trophy | 567 | 564 | Textured prop validated/imported |
| Asylum bucket | 496 | 438 | Textured prop validated/imported |
| Crow, LOD1 | 1,444 | 1,592 | 22 joints, one original skeletal clip |
| Gloria | 3,642 | 4,456 | 181 joints, 12 morph targets, one skeletal clip |
| Lungfish, LOD1 | 5,579 | 7,807 | 231 joints, one original skeletal clip |
| Bunkhouse scene | 8,312 | 6,523 | Visual snapshot plus separate collision |
| Lodge scene | 31,036 | 21,992 | Visual snapshot plus separate collision |
| Campgrounds scene | 111,514 | 98,473 | Visual snapshot plus separate collision |
| Ultracoach shield, control | — | — | Stops on unsupported affector type 50 |

There are nine successful visual exports and three separate collision exports.
All 12 GLBs plus three diagnostic fixtures pass Khronos validation with zero
errors/warnings; informational unused-resource notices are retained. The failed
heater attempt and successful replacement are separate artifacts.

## Reusable fixes and quality findings

* Textureless props exposed invalid empty `images`/`textures` arrays. The visual
  serializer now omits empty optional arrays, matching glTF minItems rules. A
  synthetic textured-independent triangle fixture guards this regression. The
  inventory identifies 37 static model candidates with no base/lightmap images;
  this is opportunity, not proof all 37 export.
* The generic inspection renderer now resets imported bone/morph state after
  muting animations. Lungfish initially rendered blank with stale imported pose
  state; an explicit bind reset produces a coherent model. This changes inspection
  state, not exported geometry. Optional source-coordinate region framing makes
  large scene views useful without changing assets; whole-scene bounds include
  sky/staging objects and can dwarf useful environment geometry.
* Source comparisons check positions, packed normals, winding, UVs, palette
  indices/weights, material flags and texture references. Embedded PNG pixels
  match the selected original base textures through a separate image read.
  This checks selection/codec consistency, not independent shader behavior.
* Blender 4.2.23 imports all nine visual exports. Six static visual GLBs pass
  coordinate-multiset and triangle-count checks. The three characters pass 27
  samples of original clips, maximum position discrepancy 0.008967 source units,
  and 324 synthetic deformation samples, maximum 0.000438. Existing model-relative
  tolerances and slerp densification remain explicit. Morph geometry is retained;
  no new facial companion animations are attached.
* Collision source arrays and glTF checks pass. Bunkhouse retains 1,102 triangles
  in Blender, Lodge 2,330. Campgrounds GLB retains all 30,827 source triangles;
  Blender imports 30,352, suppressing exactly 475 duplicates, with no new faces
  or unexplained missing triangle locations. The strict face-count verifier
  remains failed for this case; it was not weakened to hide the difference.
* Textured renders were inspected for props, characters and environment views.
  Coherent surfaces/base textures do not establish original lighting fidelity.
  Godot, Unity and Unreal imports are untested.

## Failure classes and practical limits

The 31 unparsed model payloads include 11 unsupported skin-influence layouts,
seven truncated/unknown layouts, seven old scene versions (303/304/305/315), and
six affector variants (4/30/50/91/110). The 18 rejected JAN payloads comprise
12 non-increasing-time diagnostics, one truncated/unknown layout and five
unsupported versions (1/100). These are decoder failures; do not assume every
reported key-order problem proves a malformed original asset or sort keys.

Facial parsing rejects 5,877 unique PBA version-101 payloads and 17 version-100
tail variants. PPF texture surface checks reject 258 multi-frame/volume variants
and ten unsupported/truncated surface layouts. One unique event payload fails
name/key consistency. Other indexed resources include shader, ASD, HLPS, DFS,
camera and configuration records; they are inventoried, not decoded/exported.

Environment exports preserve baked geometry and serialized metadata, not complete
levels. Bunkhouse/Lodge/Campgrounds retain respectively 2/1/7 nonidentity mesh
transforms without asserting their runtime placement rules. Script placements
are 9/16/157; only 0/3/76 have existing index/name/translation agreement. Scene
tails remain opaque (7,756/11,359/753,688 bytes). Lightmaps are retained but not
composed like the original renderer; detail/gloss/reflection and dynamic actors
remain incomplete. Collision exports do not establish physics behavior.

## Reproduction and next work

Use the existing Python environment, owned archives and private validator:

```sh
python -B tools/asset_manifest.py "$GAME" --output "$PRIVATE/inventory.json"
python -B tools/asset_survey.py --game "$GAME" --manifest "$PRIVATE/inventory.json" \
  --plan docs/asset-survey-plan.json --out "$PRIVATE/new-survey" --validator "$VALIDATOR"
blender --background --threads 2 --python-exit-code 1 \
  --python tools/blender_model_check.py -- "$PRIVATE/new-survey" rigged
python -B -m unittest discover -s tests -v
```

Inventory/survey destinations must be new and under this checkout's
`.local/assets/`. Plans are capped at 16 targets. The survey records stage-specific
failures and writes a new coverage manifest; it never overwrites an input manifest
or accepted export. Animation selection examines at most 40 same-joint-count
candidates and requires exact hierarchy compatibility; references with separate
APF root-motion channels are excluded. Selected skeletal clips do not imply
event/PBA companion recovery. Blender saves private .blend copies; never run its
writer on an accepted archive. Inspection renderer arguments may include a source
`x,y,z` center and positive radius after yaw for camera framing only.

Priorities based on measured coverage:

1. Recover PBA version 101 using independent original records and source-loader
   evidence: 5,877 unique payloads blocked by a shared version gate. Do not bypass
   the gate or assume the version-100 layout.
2. Expand shared texture/model variants with bounded fixtures: classify the 258
   multi-frame/volume textures and ten surface failures, then the 11 skin-layout
   failures. Favor common reusable cases over isolated effectors.
3. Establish environment instance/transform rules and material composition using
   independent placement/lightmap evidence. All 49 visual scenes parse, but the
   observed runtime-placement and lighting gaps limit practical level reuse.

This batch adds original tooling, metadata summaries and synthetic tests suitable
for separate review. Raw inventory, failed attempts, private exports, Blender
projects, diagnostics and original assets remain ignored. Nothing is submitted
upstream; contribution fit still requires parent-project review.
