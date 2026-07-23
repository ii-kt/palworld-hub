# Fixed-build Palworld evidence

`build-24181105.assets.json` is a derived, read-only extraction.
`build-24181105.native-breeding.json` records reproducible byte offsets,
instruction excerpts, and hashes from the exact dedicated-server executable.
Neither file contains a PAK/IoStore payload, mappings file, executable, Steam
credential, or account data.

- Game: `v1.0.1.100619`
- Dedicated server app/build: `2394010` / `24181105`
- Linux depot/manifest: `2394012` / `2167164727892555341`
- Input `Pal-LinuxServer.pak`: 4,797,040,962 bytes, SHA-256
  `cad80fe15c38d74a795779fbab31f04bc2c15c37fb8a2188e4d89f3800fb0e68`
- Derived JSON SHA-256:
  `e23a12ceffae5792b69c8faebe8ee3fbacbc09f0bd88572410d2b3b59aca1fe0`
- Depot manifest SHA-256:
  `3bab93b8c70d612ca5bd1a827be3d7f2d1bf92a2c1829507eca60c81a8f605ca`
- `PalServer-Linux-Shipping`: 196,285,592 bytes, SHA-256
  `788649fa1592160faa7bcf07ccd16d474ebeaae954717bc32284b5a43028d8e7`
- ELF build ID: `7f7e167407984ec3`
- Base extractor: `Awy64/palworld-atlas-data` commit
  `0385b3fd8bd757240d4a2c79615145122669abd5`
- Extraction extension: `tools/RawPalDump.cs`

The extraction reads `DT_PalMonsterParameter`, `DT_PalCombiUnique`,
`DT_PalCharacterIconDataTable`, and the Japanese/English Pal-name tables.
It also reads `DA_BreedingItemEffectData`; all four fixed-build entries have
`CombiRankBonus = 0`, so the native optional rank adjustment leaves the base
ceiling-average formula unchanged for every available breeding item.
`build_verified_dataset.py` independently validates the exact input hashes,
applies the pinned release-selection rules, calculates every unordered parent
pair, and compares every logical result row with pinned auxiliary outputs.
The byte-verified top-level control flow checks special combinations before
normal selection and has no equal-parent shortcut; this is why two self-pair
results intentionally differ from auxiliary calculators that add such a rule.

To reproduce the native byte checks without committing the executable:

```sh
python3 tools/verify_native_breeding_binary.py \
  /path/to/PalServer-Linux-Shipping
```
