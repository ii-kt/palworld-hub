using System.Security.Cryptography;
using System.Text.Json;
using CUE4Parse.Compression;
using CUE4Parse.FileProvider;
using CUE4Parse.MappingsProvider.Usmap;
using CUE4Parse.UE4.Assets.Exports.Texture;
using CUE4Parse.UE4.Versions;
using CUE4Parse_Conversion;
using CUE4Parse_Conversion.Textures;
using Serilog;

const string GameVersion = "v1.0.1.100619";
const string ClientAppId = "1623730";
const string ClientBuildId = "24181527";
const string ClientDepotId = "1623731";
const string ClientDepotManifestId = "2714631871676494093";
const long ExpectedClientPakBytes = 40_526_106_335;
const string ExpectedClientPakSha256 = "fe2d7b8548d5be0649b6bb3e49aadc79529c2e7d138baaacece3a3563a864227";
const string ExpectedAssetsSha256 = "e23a12ceffae5792b69c8faebe8ee3fbacbc09f0bd88572410d2b3b59aca1fe0";
const string CatalogMappingsSha256 = "561ef13c8ee3cf785e4de8aa5bc9b3ad1646e416d895f1d1166fa27ebdfd26b0";
const string ExpectedParserMappingsSha256 = "241c45de9d5b55b246cd4b39d62b9209faf7758ce0637e1f7a545aa0f75f71f0";
const long ExpectedOodleBytes = 998_400;
const string ExpectedOodleSha256 = "cba19529d0a3b5ec9c630e95652af01e123ae29a34a8a5f7507f5bcf23d9e82b";
const string ParserMappingsCommit = "42cf396e714c166f17950a9c964583e0cadf2a15";
const string IconTablePath = "Pal/Content/Pal/DataTable/Character/DT_PalCharacterIconDataTable";
const string AtlasExtractorCommit = "0385b3fd8bd757240d4a2c79615145122669abd5";
const string Cue4ParseCommit = "ecad882a3049df6f27e0c5c3a3531346305c010b";
const string Cue4ParseVersion = "1.2.2.202607";

if (args.Length != 9)
{
    Console.Error.WriteLine(
        "Usage: PalIconExtractor <pak-dir> <pals.verified.json> <build-assets.json> " +
        "<output-dir> <manifest.json> <parser-Mappings.usmap> <Program.cs> " +
        "<packages.lock.json> <oodle-data-shared.dll>");
    return 2;
}

var pakDirectory = Path.GetFullPath(args[0]);
var palsPath = Path.GetFullPath(args[1]);
var assetsPath = Path.GetFullPath(args[2]);
var outputDirectory = Path.GetFullPath(args[3]);
var manifestPath = Path.GetFullPath(args[4]);
var mappingsPath = Path.GetFullPath(args[5]);
var extractorSourcePath = Path.GetFullPath(args[6]);
var packagesLockPath = Path.GetFullPath(args[7]);
var oodlePath = Path.GetFullPath(args[8]);
var readOptions = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
var writeOptions = new JsonSerializerOptions
{
    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    WriteIndented = true
};

if (!Directory.Exists(pakDirectory))
    throw new DirectoryNotFoundException(pakDirectory);
if (!File.Exists(palsPath))
    throw new FileNotFoundException("Pal dataset is missing", palsPath);
if (!File.Exists(assetsPath))
    throw new FileNotFoundException("Build assets evidence is missing", assetsPath);
if (!File.Exists(mappingsPath))
    throw new FileNotFoundException("Mappings.usmap is missing", mappingsPath);
if (!File.Exists(extractorSourcePath)
    || !Path.GetFileName(extractorSourcePath).Equals("Program.cs", StringComparison.Ordinal))
    throw new FileNotFoundException("Extractor Program.cs is missing", extractorSourcePath);
if (!File.Exists(packagesLockPath)
    || !Path.GetFileName(packagesLockPath).Equals("packages.lock.json", StringComparison.Ordinal))
    throw new FileNotFoundException("Extractor packages.lock.json is missing", packagesLockPath);
if (!File.Exists(oodlePath)
    || !Path.GetFileName(oodlePath).Equals("oodle-data-shared.dll", StringComparison.OrdinalIgnoreCase))
    throw new FileNotFoundException("oodle-data-shared.dll is missing", oodlePath);

var pakDirectoryInfo = new DirectoryInfo(pakDirectory);
if (pakDirectoryInfo.Attributes.HasFlag(FileAttributes.ReparsePoint))
    throw new InvalidDataException("The isolated PAK directory cannot be a reparse point");
var pakEntries = Directory.EnumerateFileSystemEntries(
        pakDirectory,
        "*",
        SearchOption.AllDirectories)
    .Select(Path.GetFullPath)
    .Order(StringComparer.OrdinalIgnoreCase)
    .ToArray();
if (pakEntries.Length != 1 || !File.Exists(pakEntries[0]))
    throw new InvalidDataException(
        "The supplied PAK directory must be isolated and contain exactly one regular file, " +
        $"Pal-Windows.pak; found {pakEntries.Length} filesystem entries");
var pakPath = pakEntries[0];
if (File.GetAttributes(pakPath).HasFlag(FileAttributes.ReparsePoint))
    throw new InvalidDataException("The fixed Pal-Windows.pak cannot be a reparse point");
if (!Path.GetFileName(pakPath).Equals("Pal-Windows.pak", StringComparison.OrdinalIgnoreCase)
    || !Path.GetExtension(pakPath).Equals(".pak", StringComparison.OrdinalIgnoreCase))
    throw new InvalidDataException(
        $"The only allowed container is the fixed Pal-Windows.pak; found {Path.GetFileName(pakPath)}");
var pakInfo = new FileInfo(pakPath);
if (pakInfo.Length != ExpectedClientPakBytes)
    throw new InvalidDataException($"Fixed client PAK size mismatch: {pakInfo.Length}");
var pakSha256 = Sha256File(pakPath);
if (!pakSha256.Equals(ExpectedClientPakSha256, StringComparison.Ordinal))
    throw new InvalidDataException($"Fixed client PAK SHA-256 mismatch: {pakSha256}");
var assetsSha256 = Sha256File(assetsPath);
if (!assetsSha256.Equals(ExpectedAssetsSha256, StringComparison.Ordinal))
    throw new InvalidDataException($"Build assets evidence SHA-256 mismatch: {assetsSha256}");
var mappingsSha256 = Sha256File(mappingsPath);
if (!mappingsSha256.Equals(ExpectedParserMappingsSha256, StringComparison.Ordinal))
    throw new InvalidDataException($"Mappings.usmap SHA-256 mismatch: {mappingsSha256}");
var extractorSourceSha256 = Sha256File(extractorSourcePath);
var packagesLockSha256 = Sha256File(packagesLockPath);
var palsSha256 = Sha256File(palsPath);
var oodleInfo = new FileInfo(oodlePath);
if (oodleInfo.Length != ExpectedOodleBytes)
    throw new InvalidDataException($"Oodle library size mismatch: {oodleInfo.Length}");
var oodleSha256 = Sha256File(oodlePath);
if (!oodleSha256.Equals(ExpectedOodleSha256, StringComparison.Ordinal))
    throw new InvalidDataException($"Oodle library SHA-256 mismatch: {oodleSha256}");

var pals = JsonSerializer.Deserialize<PalDataset>(File.ReadAllText(palsPath), readOptions)
           ?? throw new InvalidDataException("Invalid Pal dataset");
var assets = JsonSerializer.Deserialize<BuildAssets>(File.ReadAllText(assetsPath), readOptions)
             ?? throw new InvalidDataException("Invalid build assets evidence");

var iconById = assets.Icons
    .Where(icon => !icon.Path.Contains("T_dummy_icon", StringComparison.OrdinalIgnoreCase))
    .GroupBy(icon => icon.Id, StringComparer.OrdinalIgnoreCase)
    .ToDictionary(
        group => group.Key,
        group => group.Single(),
        StringComparer.OrdinalIgnoreCase);

var requested = new SortedDictionary<string, IconRequest>(StringComparer.Ordinal);
foreach (var pal in pals.Pals)
{
    var usedTribeFallback = false;
    if (!iconById.TryGetValue(pal.SourceId, out var iconRow))
    {
        if (!iconById.TryGetValue(pal.Tribe, out iconRow))
            throw new InvalidDataException(
                $"No fixed-build icon mapping for {pal.Id} ({pal.SourceId}/{pal.Tribe})");
        usedTribeFallback = true;
    }

    var iconId = iconRow.Id.Trim().ToLowerInvariant();
    if (!iconRow.Path.StartsWith("/Game/Pal/Texture/PalIcon/Normal/", StringComparison.Ordinal)
        || iconRow.Path.Contains("T_dummy_icon", StringComparison.OrdinalIgnoreCase))
        throw new InvalidDataException($"Invalid fixed-build icon path for {pal.Id}: {iconRow.Path}");
    if (requested.TryGetValue(iconId, out var existing))
    {
        if (!existing.ObjectPath.Equals(iconRow.Path, StringComparison.Ordinal))
            throw new InvalidDataException($"One icon ID maps to multiple texture paths: {iconId}");
        existing.PalIds.Add(pal.Id);
        if (usedTribeFallback)
            existing.TribeFallbackPalIds.Add(pal.Id);
    }
    else
    {
        requested.Add(iconId, new IconRequest(
            iconId,
            iconRow.Id,
            iconRow.Path,
            $"{iconId}.png",
            [pal.Id],
            usedTribeFallback ? [pal.Id] : []));
    }
}

if (pals.Pals.Count != 288)
    throw new InvalidDataException($"Expected 288 public forms, got {pals.Pals.Count}");
if (requested.Count != 287)
    throw new InvalidDataException($"Expected 287 unique icon textures, got {requested.Count}");
var shared = requested.Values.Where(request => request.PalIds.Count > 1).ToArray();
if (shared.Length != 1
    || shared[0].IconId != "plantslime"
    || !shared[0].PalIds.ToHashSet(StringComparer.Ordinal).SetEquals(
        ["plantslime", "plantslime_flower"]))
    throw new InvalidDataException("Unexpected public-form icon sharing");

Directory.CreateDirectory(outputDirectory);
Directory.CreateDirectory(Path.GetDirectoryName(manifestPath)!);
Log.Logger = new LoggerConfiguration().MinimumLevel.Warning().WriteTo.Console().CreateLogger();
OodleHelper.Initialize(oodlePath);

using var provider = new DefaultFileProvider(
    pakDirectory,
    SearchOption.AllDirectories,
    new VersionContainer(EGame.GAME_UE5_1),
    StringComparer.OrdinalIgnoreCase);
provider.MappingsContainer = new FileUsmapTypeMappingsProvider(mappingsPath);
provider.Initialize();
provider.Mount();
provider.LoadVirtualPaths();

var records = new List<OutputRecord>(requested.Count);
foreach (var request in requested.Values)
{
    var texture = provider.LoadPackageObject<UTexture2D>(request.ObjectPath)
                  ?? throw new InvalidDataException($"UTexture2D not found: {request.ObjectPath}");
    var decoded = texture.Decode()
                  ?? throw new InvalidDataException(
                      $"Texture decode returned null: {request.ObjectPath}; " +
                      $"format={texture.Format}; imported={texture.ImportedSize.X}x{texture.ImportedSize.Y}; " +
                      $"platform={texture.PlatformData.SizeX}x{texture.PlatformData.SizeY}; " +
                      $"mips={texture.PlatformData.Mips.Length}; firstMip={texture.PlatformData.FirstMipToSerialize}");
    var pngBytes = decoded.Encode(ETextureFormat.Png, saveHdrAsHdr: false, out var extension);
    if (!extension.Equals("png", StringComparison.Ordinal))
        throw new InvalidDataException($"Unexpected output extension {extension}: {request.ObjectPath}");

    var outputPath = Path.Combine(outputDirectory, request.FileName);
    File.WriteAllBytes(outputPath, pngBytes);
    records.Add(new OutputRecord(
        request.IconId,
        request.SourceTableId,
        request.ObjectPath,
        $"assets/pal-icons/{request.FileName}",
        request.PalIds.Order(StringComparer.Ordinal).ToArray(),
        request.PalIds.Count > 1,
        request.TribeFallbackPalIds.Order(StringComparer.Ordinal).ToArray(),
        decoded.Width,
        decoded.Height,
        decoded.PixelFormat.ToString(),
        decoded.Data.LongLength,
        Sha256(decoded.Data),
        pngBytes.LongLength,
        Sha256(pngBytes)));
}

var manifest = new OutputManifest(
    SchemaVersion: 1,
    GameVersion: GameVersion,
    SourceClient: new SourceClient(
        ClientAppId,
        ClientBuildId,
        ClientDepotId,
        ClientDepotManifestId,
        Path.GetFileName(pakPath),
        pakInfo.Length,
        pakSha256),
    SourceMapping: new SourceMapping(
        IconTablePath,
        "evidence/build-24181105.assets.json",
        assetsSha256,
        CatalogMappingsSha256,
        $"PalworldModding/UsefulFiles@{ParserMappingsCommit}",
        mappingsSha256),
    SourceInputs: new SourceInputs(
        "data/pals.verified.json",
        palsSha256,
        "tools/pal-icon-extractor/Program.cs",
        extractorSourceSha256,
        "tools/pal-icon-extractor/packages.lock.json",
        packagesLockSha256,
        Path.GetFileName(oodlePath),
        oodleInfo.Length,
        oodleSha256),
    Extractor: new ExtractorIdentity(
        $"Awy64/palworld-atlas-data@{AtlasExtractorCommit}",
        $"FabianFG/CUE4Parse@{Cue4ParseCommit}",
        Cue4ParseVersion),
    Counts: new OutputCounts(pals.Pals.Count, records.Count, records.Count(record => record.Shared)),
    Icons: records.OrderBy(record => record.IconId, StringComparer.Ordinal).ToArray());
File.WriteAllText(manifestPath, JsonSerializer.Serialize(manifest, writeOptions) + Environment.NewLine);
Console.WriteLine($"Extracted {records.Count} fixed-client PNGs for {pals.Pals.Count} public forms.");
return 0;

static string Sha256File(string path)
{
    using var stream = File.OpenRead(path);
    return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
}

static string Sha256(byte[] bytes) =>
    Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

sealed record PalDataset(List<Pal> Pals);
sealed record Pal(string Id, string SourceId, string Tribe);
sealed record BuildAssets(List<IconRow> Icons);
sealed record IconRow(string Id, string Path);
sealed record IconRequest(
    string IconId,
    string SourceTableId,
    string ObjectPath,
    string FileName,
    List<string> PalIds,
    List<string> TribeFallbackPalIds);
sealed record SourceClient(
    string AppId,
    string BuildId,
    string DepotId,
    string DepotManifestId,
    string PakFile,
    long PakBytes,
    string PakSha256);
sealed record SourceMapping(
    string IconTable,
    string EvidencePath,
    string EvidenceSha256,
    string CatalogMappingsSha256,
    string ParserMappings,
    string ParserMappingsSha256);
sealed record SourceInputs(
    string PalsPath,
    string PalsSha256,
    string ExtractorSourcePath,
    string ExtractorSourceSha256,
    string PackagesLockPath,
    string PackagesLockSha256,
    string OodleFile,
    long OodleBytes,
    string OodleSha256);
sealed record ExtractorIdentity(
    string TableExtractor,
    string TextureDecoder,
    string Cue4ParseVersion);
sealed record OutputCounts(int PalForms, int UniqueIcons, int SharedIcons);
sealed record OutputRecord(
    string IconId,
    string SourceTableId,
    string ObjectPath,
    string OutputPath,
    string[] PalIds,
    bool Shared,
    string[] TribeFallbackPalIds,
    int Width,
    int Height,
    string PixelFormat,
    long DecodedPixelBytes,
    string DecodedPixelSha256,
    long PngBytes,
    string PngSha256);
sealed record OutputManifest(
    int SchemaVersion,
    string GameVersion,
    SourceClient SourceClient,
    SourceMapping SourceMapping,
    SourceInputs SourceInputs,
    ExtractorIdentity Extractor,
    OutputCounts Counts,
    OutputRecord[] Icons);
