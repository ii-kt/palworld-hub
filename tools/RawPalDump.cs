// Fixed-build evidence extractor extension used with Awy64/palworld-atlas-data
// commit 0385b3fd8bd757240d4a2c79615145122669abd5. This emits derived JSON only;
// the PAK, mappings, Steam credentials, and executables must never be committed.
using System.Security.Cryptography;
using System.Reflection;
using System.Text.Json;
using CUE4Parse.FileProvider;
using CUE4Parse.UE4.Assets.Exports;
using CUE4Parse.UE4.Assets.Objects;
using CUE4Parse.UE4.Objects.UObject;

namespace PalworldAtlas.Extractor;

internal static class RawPalDump
{
    public static int Write(string pakDirectory, string? mappings, string buildId, string output)
    {
        using var workspace = new PakWorkspace(pakDirectory, mappings);
        var palTable = workspace.LoadFirst(AssetCatalog.Pals)
            ?? throw new InvalidDataException("DT_PalMonsterParameter was not parsed");
        var breedingTable = workspace.LoadFirst(AssetCatalog.Breeding)
            ?? throw new InvalidDataException("DT_PalCombiUnique was not parsed");
        var iconTable = workspace.Load("Pal/Content/Pal/DataTable/Character/DT_PalCharacterIconDataTable")
            ?? throw new InvalidDataException("DT_PalCharacterIconDataTable was not parsed");
        var japaneseNames = workspace.Load("Pal/Content/Pal/DataTable/Text/DT_PalNameText_Common")
            ?? throw new InvalidDataException("Japanese DT_PalNameText_Common was not parsed");
        var englishNames = workspace.Load("Pal/Content/L10N/en/Pal/DataTable/Text/DT_PalNameText_Common")
            ?? throw new InvalidDataException("English DT_PalNameText_Common was not parsed");
        const string breedingItemEffectPath =
            "Pal/Content/Pal/DataAsset/MapObject/Breeding/DA_BreedingItemEffectData";
        var providerField = typeof(PakWorkspace).GetField("_provider", BindingFlags.Instance | BindingFlags.NonPublic)
            ?? throw new MissingFieldException("Pinned PakWorkspace._provider was not found");
        var provider = providerField.GetValue(workspace) as DefaultFileProvider
            ?? throw new InvalidDataException("Pinned PakWorkspace provider type changed");
        var breedingItemEffectAsset = provider.LoadPackageObject<UObject>(breedingItemEffectPath);
        var itemEffectProperty = breedingItemEffectAsset.Properties.Single(property =>
            property.Name.Text.Equals("ItemEffectMap", StringComparison.OrdinalIgnoreCase));
        var itemEffectMap = itemEffectProperty.Tag.GetValue<UScriptMap>();

        static FStructFallback StructValue(CUE4Parse.UE4.Assets.Objects.Properties.FPropertyTagType value)
        {
            var wrapper = value.GetValue<FScriptStruct>();
            return wrapper.StructType as FStructFallback
                ?? throw new InvalidDataException("Breeding item map entry is not a fallback struct");
        }

        var breedingItemEffects = itemEffectMap.Properties.Select(entry =>
        {
            var key = new RowReader(StructValue(entry.Key));
            var valueStruct = StructValue(entry.Value);
            var value = new RowReader(valueStruct);
            var mutationRate = valueStruct.Properties.Single(property =>
                property.Name.Text.Equals("MutationRateBonusPercent", StringComparison.OrdinalIgnoreCase));
            return new
            {
                itemId = key.String("", "Key"),
                talentBonusMin = value.Int(0, "TalentBonusMin"),
                talentBonusMax = value.Int(0, "TalentBonusMax"),
                mutationRateBonusPercent = mutationRate.Tag.GetValue<float>(),
                combiRankBonus = value.Int(0, "CombiRankBonus"),
                breedCount = value.Int(0, "BreedCount"),
                inheritAllActiveSkills = value.Bool(false, "bInheritAllActiveSkills"),
                passiveInheritCountOverride = value.Int(0, "PassiveInheritCountOverride")
            };
        }).OrderBy(value => value.itemId, StringComparer.Ordinal).ToArray();

        var pals = palTable.RowMap.Select((row, index) =>
        {
            var reader = new RowReader(row.Value);
            return new
            {
                sourceOrder = index,
                rowName = row.Key.Text,
                isPal = reader.Bool(false, "IsPal"),
                isBoss = reader.Bool(false, "IsBoss"),
                isRaidBoss = reader.Bool(false, "IsRaidBoss"),
                isTowerBoss = reader.Bool(false, "IsTowerBoss"),
                predator = reader.Bool(false, "Predator"),
                zukanIndex = reader.Int(-1, "ZukanIndex"),
                zukanIndexSuffix = reader.String("", "ZukanIndexSuffix"),
                combiRank = reader.Int(0, "CombiRank"),
                combiDuplicatePriority = reader.Int(0, "CombiDuplicatePriority"),
                rarity = reader.Int(0, "Rarity"),
                ignoreCombi = reader.Bool(false, "IgnoreCombi"),
                tribe = reader.String(row.Key.Text, "Tribe"),
                overrideNameTextId = reader.String("", "OverrideNameTextId", "OverrideNameTextID"),
                elementType1 = reader.String("None", "ElementType1"),
                elementType2 = reader.String("None", "ElementType2"),
                walkSpeed = reader.Int(0, "WalkSpeed"),
                runSpeed = reader.Int(0, "RunSpeed"),
                workSuitability = new Dictionary<string, int>
                {
                    ["EmitFlame"] = reader.Int(0, "WorkSuitability_EmitFlame"),
                    ["Watering"] = reader.Int(0, "WorkSuitability_Watering"),
                    ["Seeding"] = reader.Int(0, "WorkSuitability_Seeding"),
                    ["GenerateElectricity"] = reader.Int(0, "WorkSuitability_GenerateElectricity"),
                    ["Handcraft"] = reader.Int(0, "WorkSuitability_Handcraft"),
                    ["Collection"] = reader.Int(0, "WorkSuitability_Collection"),
                    ["Deforest"] = reader.Int(0, "WorkSuitability_Deforest"),
                    ["Mining"] = reader.Int(0, "WorkSuitability_Mining"),
                    ["OilExtraction"] = reader.Int(0, "WorkSuitability_OilExtraction"),
                    ["ProductMedicine"] = reader.Int(0, "WorkSuitability_ProductMedicine"),
                    ["Cool"] = reader.Int(0, "WorkSuitability_Cool"),
                    ["Transport"] = reader.Int(0, "WorkSuitability_Transport"),
                    ["MonsterFarm"] = reader.Int(0, "WorkSuitability_MonsterFarm")
                }
            };
        }).ToArray();

        var combinations = breedingTable.RowMap.Select((row, index) =>
        {
            var reader = new RowReader(row.Value);
            return new
            {
                sourceOrder = index,
                rowName = row.Key.Text,
                parentTribeA = reader.String("", "ParentTribeA"),
                parentTribeB = reader.String("", "ParentTribeB"),
                parentGenderA = reader.String("", "ParentGenderA"),
                parentGenderB = reader.String("", "ParentGenderB"),
                childCharacterId = reader.String("", "ChildCharacterID")
            };
        }).ToArray();

        static Dictionary<string, string> Names(CUE4Parse.UE4.Assets.Exports.Engine.UDataTable table) =>
            table.RowMap.ToDictionary(
                row => row.Key.Text,
                row => new RowReader(row.Value).String("", "TextData", "Text", "Value"),
                StringComparer.OrdinalIgnoreCase);

        var icons = iconTable.RowMap.Select(row => new
        {
            id = row.Key.Text,
            path = row.Value.Get<FSoftObjectPath>("Icon").AssetPathName.Text
        }).ToArray();
        var pakFiles = Directory.EnumerateFiles(pakDirectory, "*.pak", SearchOption.AllDirectories)
            .Order(StringComparer.Ordinal)
            .Select(path => new
            {
                file = Path.GetFileName(path),
                bytes = new FileInfo(path).Length,
                sha256 = Convert.ToHexString(SHA256.HashData(File.OpenRead(path))).ToLowerInvariant()
            }).ToArray();
        var payload = new
        {
            schemaVersion = 1,
            buildId,
            pakFiles,
            japaneseNames = Names(japaneseNames),
            englishNames = Names(englishNames),
            icons,
            pals,
            combinations,
            breedingItemEffectPath,
            breedingItemEffects
        };
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        File.WriteAllText(output, JsonSerializer.Serialize(payload, new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            WriteIndented = false
        }));
        return 0;
    }
}
