# Fixed-build Pal icon extractor

This source-only tool exports the 287 distinct Pal icon textures used by the
288 public forms in the fixed dataset. It fails closed unless all of these
inputs match the pinned build:

- client app/build `1623730` / `24181527`
- client depot/manifest `1623731` / `2714631871676494093`
- `Pal-Windows.pak` SHA-256
  `fe2d7b8548d5be0649b6bb3e49aadc79529c2e7d138baaacece3a3563a864227`
- raw icon-table evidence SHA-256
  `e23a12ceffae5792b69c8faebe8ee3fbacbc09f0bd88572410d2b3b59aca1fe0`
- parser mappings SHA-256
  `241c45de9d5b55b246cd4b39d62b9209faf7758ce0637e1f7a545aa0f75f71f0`
- Oodle decoder SHA-256
  `cba19529d0a3b5ec9c630e95652af01e123ae29a34a8a5f7507f5bcf23d9e82b`

The icon identity comes only from the fixed-build
`DT_PalCharacterIconDataTable` SoftObjectPaths already committed under
`evidence/`. The public 1.0 parser mappings are pinned at
`PalworldModding/UsefulFiles@42cf396e714c166f17950a9c964583e0cadf2a15`.
They are used only to deserialize the exact client texture packages. The
catalog extraction's separately generated `Mappings.usmap` SHA-256 remains
`561ef13c8ee3cf785e4de8aa5bc9b3ad1646e416d895f1d1166fa27ebdfd26b0`.

Run with .NET 10 from a temporary working directory that contains
`oodle-data-shared.dll`. The first argument must be an isolated, non-linked
directory whose only filesystem entry is the verified regular file
`Pal-Windows.pak`. The extractor rejects extra containers, loose Unreal assets,
project files, subdirectories, and reparse points so another source cannot
silently override the pinned texture packages:

```powershell
dotnet run --project tools/pal-icon-extractor -c Release -- `
  D:\path\to\isolated-fixed-client-pak `
  data\pals.verified.json `
  evidence\build-24181105.assets.json `
  assets\pal-icons `
  evidence\build-24181527.pal-icons.json `
  D:\path\to\Mappings.usmap `
  tools\pal-icon-extractor\Program.cs `
  tools\pal-icon-extractor\packages.lock.json `
  D:\path\to\oodle-data-shared.dll
```

The PAK, mappings file, Oodle library, .NET build output, Steam metadata, and
compiled extractor must remain outside Git. NuGet restore is locked by
`packages.lock.json`. Only this source, the derived PNGs, the lock file, and the
derived manifest are repository artifacts. The manifest records SHA-256 values
for the Pal input, extractor source, lock file, and verified Oodle binary used
by the extraction.
