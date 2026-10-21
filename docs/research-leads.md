# Prioritized external research leads

These are research leads supplied during publication review, not new verified native
findings. Availability, current contents, addresses, licenses and compatibility must
be checked against a pinned revision before use. Descriptions from other reviews are
not proof of matching C++ or of the absence of more advanced projects elsewhere.
No external implementations, prototypes, scripts, dumps or assets were acquired for
this list. Keep original binaries and private analysis outside the public repository.

## First compatibility audit

| Priority/source | Question to investigate | Acceptance boundary |
| --- | --- | --- |
| [noclip Psychonauts](https://github.com/magcius/noclip.website/tree/main/src/psychonauts) | Compare ppf.ts/plb.ts/render.ts field/version/material interpretations with native CYSP/resource evidence | Existing attributed decoder reuse is recorded in third_party; a parser/rendering assumption is not original runtime behavior |
| [Astralathe](https://gitlab.com/scrunguscrungus/astralathe) | Identify documented hooks, ABI and class-field observations useful for resource/model/object lifetimes | Verify executable fingerprint and each address/signature independently; keep incompatible or unclear-license implementations separate |
| [Lua API documentation](https://psycholuaapi.readthedocs.io/en/latest/index.html) | Check argument/LSO/entity semantics against the recovered registrations and binding assembly | Treat names/descriptions as hypotheses until actual calls/returns/dataflow agree |
| [Psychonauts Studio](https://github.com/RayCarrot/PsychonautsStudio) | Compare structured serialization records and version handling | Distinguish PC/PS2/Xbox/prototype layouts; inspect actual supported code, not planned editor/export features |
| [DoubleFine Explorer](https://github.com/bgbennyboy/DoubleFine-Explorer) | Compare newer archive indexing with the supported Steam resource path | Independent extractor behavior does not establish loader ownership or C++ declarations |

Use one bounded audit: select a concrete resource/mesh field or unresolved call,
record source commit, reuse permission, claimed platform/build, observed declaration,
and the exact original-reference evidence that confirms or contradicts it. Publish
only safe semantic findings and attribution, not proprietary byte dumps. No automatic
source merge or compiler/matcher change follows from finding a plausible declaration.

## Architectural and historical comparison

- [Open-Li-Po (Fancy2209)](https://github.com/Fancy2209/Open-Li-Po) and
  [Open-Li-Po (JillCrungus)](https://github.com/JillCrungus/Open-Li-Po): inspect actual
  method bodies and build evidence before treating module/declaration counts as
  implementation progress. Class names/ownership remain hypotheses until verified.
- [Psychonauts Explorer](https://github.com/bgbennyboy/Psychonauts-Explorer): compare
  older archive/platform variants with newer-release implementations.
- [2005 PKG/PPF research](https://lucasforumsarchive.com/thread/148943-psychonauts-pkg-file-format-specs)
  and [PsychoMunger discussion](https://www.lucasforumsarchive.com/thread/152305-more-psychonauts-stuff):
  distinguish provisional historical interpretations and inaccessible file links
  from evidence actually available and independently tested.
- Historical [December 2004 Xbox record](https://hiddenpalace.org/Psychonauts_(Dec_17,_2004_prototype))
  and [February 2005 Xbox record](https://hiddenpalace.org/Psychonauts_(Feb_14,_2005_prototype)):
  metadata/debug/version-transition leads only. This is not a download/acquisition
  instruction or permission to publish assets. Their addresses/compiler conclusions
  cannot be transferred to the supported Steam Windows PE32 reference.

## Later AI workflow experiment

[decomp.wtf](https://github.com/i12bp8/decomp.wtf) and
[decomp-skills](https://github.com/Ketbome/decomp-skills) are unvalidated coordination/
workflow leads. Check their pinned source, license and assumptions before adapting
ideas about claims, notes, recovery or agents. They are not installed dependencies.
After publication approval, a separately scoped independent reconstruction exercise
can test one unmatched function using the existing RTM compiler, exact reference,
full regression matcher and differential acceptance criteria. Keep the canonical
verification pipeline authoritative and preserve recoverable local work.
