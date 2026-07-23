# Fixed-build Palworld evidence

`build-24181105.assets.json` is a derived, read-only extraction.
`build-24181105.native-breeding.json` records reproducible byte offsets,
instruction excerpts, and hashes from the exact dedicated-server executable.
`../audit/native-runtime-comparison.json` records the exhaustive direct-call
result produced from that executable. None of these files contains a
PAK/IoStore payload, mappings file, executable, Steam credential, compiled
probe, or account data.

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
applies release selection from Paldex fields, rarity, boss flags, and exact icon
identity without classifying RowName text, calculates every unordered parent
pair, and compares every logical result row with pinned auxiliary outputs.
The byte-verified top-level control flow checks special combinations before
normal selection and has no equal-parent shortcut; this is why two self-pair
results intentionally differ from auxiliary calculators that add such a rule.

The native runtime audit injects byte-layout rows built from the fixed extracted
tables into the hash-verified server process and calls the real top-level
breeding function for all 41,616 pairs, both parent orders, and both meaningful
gender orientations. Its 166,464 calls and all 41,617 logical results have zero
differences. This proves the fixed executable's selection against the exact
extracted tables. The probe instruments five lookup/helper points (raw and
unique `FindRow`, row-key generation, manager `FindRow`, and the manager
helper); it does not claim an unmodified live-PAK DataTable read or 41,616
observed in-game hatches.

To reproduce the native byte checks without committing the executable:

```sh
python3 tools/verify_native_breeding_binary.py \
  /path/to/PalServer-Linux-Shipping
```

To reproduce the exhaustive direct-call audit from the exact server root:

```sh
sudo unshare --net -- bash -lc '
  ulimit -c 0
  ip link set lo up
  python3 tools/verify_native_breeding_runtime.py /path/to/palserver-root \
    --output audit/native-runtime-comparison.json
'
```

The workflow uploads only the derived JSON. The downloaded server files and
temporary compiled shared objects remain runner-local and are deleted with the
runner.
