> Historical technical evidence, not the current setup/checkpoint. Use
> [CONTRIBUTING](../contribute/README.md) and [current native status](native-reconstruction.md).
> Original local report references identify private evidence, not required downloads.

# Native geometry research — inconclusive, preserved separately

Reference: Windows SHA-1 21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07. Original vector arithmetic examined through TriggerOBB_GetExtent_impl:

| Address | Observed operation | Mapped bytes |
| --- | --- | ---: |
| 0x00401dc0 | three-component addition | 87 |
| 0x00401e20 | three-component subtraction | 87 |
| 0x00401e80 | vector/scalar multiplication | 79 |

Assembly uses thiscall with a hidden return destination and ret 8; the result copy includes x87 float loads/stores. The current Vector3 declaration is a simple layout used by existing matched bindings. Plausible operator bodies with implicit copying generated integer copies and mismatched stack/code lengths. Temporarily adding an explicit copy constructor yielded byte-search candidates for addition/multiplication but did not establish full matching or regression safety. No full regression was run with that constructor and no observed regression is claimed.

The constructor was removed. Explicit component returns without changing Vector3 still differed (112/97 object bytes versus original padded 96/79 for the examined candidates). Missing original copy/return/type semantics remain unresolved. Experimental source is retained privately in .local/geometry-arithmetic-candidate.cpp. Neither engine.h nor luafunc.cpp changed in the validated final tree.

A restored strict build compiled all 53 sources. Final read-only report build/asset-phase-native-regression.json confirms 2,890 exact matches, 232,611 mapped bytes, zero new addresses and zero regressions. Prior exact matching implementations and canonical function metadata remain unchanged. Asset parsing/export work can proceed without guessing the original Vector3 special members.
