/*
 * Fixed-build Palworld native breeding runtime probe.
 *
 * This shared object is loaded only into the hash-verified Build 24181105
 * Linux dedicated server. It invokes the real breeding-result function at
 * 0x71168c0 while narrowly replacing its data-table accessors with rows built
 * byte-for-byte at the reflected offsets from the hash-verified fixed-build
 * asset extraction. The helper at 0x76459e0 is instruction-equivalent for
 * ordinary server objects and returns the audit manager only for two synthetic
 * parents. No selection, special-recipe, gender, or tie-break code is stubbed.
 */
#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#define ADDRESS_MANAGER_HELPER ((uintptr_t)0x76459e0)
#define ADDRESS_GET_OWNER ((uintptr_t)0x71ed360)
#define ADDRESS_GENERATE_KEYS ((uintptr_t)0xa2f9f40)
#define ADDRESS_FIND_ROW ((uintptr_t)0x713d270)
#define ADDRESS_UNIQUE_FIND_ROW ((uintptr_t)0x7118880)
#define ADDRESS_MANAGER_FIND_ROW ((uintptr_t)0x713a280)
#define ADDRESS_ALLOC ((uintptr_t)0x77dc850)
#define ADDRESS_GET_TRIBE ((uintptr_t)0x71389d0)
#define ADDRESS_FREE ((uintptr_t)0x77dd4e0)
#define ADDRESS_BREED ((uintptr_t)0x71168c0)
#define ADDRESS_BOSS_VARIANT ((uintptr_t)0x7118c40)

#define RAW_RECORD_SIZE 20u
#define RELEASED_RECORD_SIZE 8u
#define UNIQUE_RECORD_SIZE 8u
#define PAIR_RECORD_SIZE 12u
#define RAW_ROW_SIZE 0x10cu
#define UNIQUE_ROW_SIZE 0x18u

#pragma pack(push, 1)
struct input_header {
    char magic[8];
    uint32_t schema_version;
    uint32_t raw_count;
    uint32_t released_count;
    uint32_t unique_count;
    uint32_t pair_count;
    uint32_t logical_count;
    uint32_t raw_record_size;
    uint32_t released_record_size;
    uint32_t unique_record_size;
    uint32_t pair_record_size;
};

struct raw_expected {
    int32_t source_order;
    int32_t combi_rank;
    int32_t duplicate_priority;
    int32_t zukan_index;
    uint8_t is_boss;
    uint8_t ignore_combi;
    uint16_t tribe_id;
};

struct released_expected {
    uint16_t source_order;
    uint16_t reserved;
    int32_t combi_rank;
};

struct unique_expected {
    uint16_t parent_a_source;
    uint16_t parent_b_source;
    uint16_t child_source;
    uint8_t gender_a;
    uint8_t gender_b;
};

struct pair_expected {
    uint16_t parent_a;
    uint16_t parent_b;
    uint16_t female_male_child;
    uint16_t male_female_child;
    uint8_t gender_dependent;
    uint8_t recipe_type;
    uint8_t reserved[2];
};
#pragma pack(pop)

struct runtime_array {
    uint64_t *data;
    int32_t count;
    int32_t capacity;
};

struct runtime_raw_row {
    uint64_t name;
    void *row;
    uint16_t tribe;
    int32_t rank;
    int32_t priority;
    uint8_t boss;
    uint8_t ignore;
};

struct row_mismatch {
    uint32_t source_order;
    int32_t expected_rank;
    int32_t actual_rank;
    int32_t expected_priority;
    int32_t actual_priority;
    uint8_t expected_boss;
    uint8_t actual_boss;
    uint8_t expected_ignore;
    uint8_t actual_ignore;
};

struct unique_mismatch {
    uint32_t source_order;
    int32_t expected_parent_a;
    int32_t actual_parent_a;
    int32_t expected_parent_b;
    int32_t actual_parent_b;
    int32_t expected_child;
    int32_t actual_child;
    int32_t expected_gender_a;
    int32_t actual_gender_a;
    int32_t expected_gender_b;
    int32_t actual_gender_b;
};

struct pair_mismatch {
    uint32_t pair_index;
    uint16_t parent_a;
    uint16_t parent_b;
    int16_t expected_female_male_source;
    int16_t actual_female_male_forward;
    int16_t actual_female_male_reverse;
    int16_t expected_male_female_source;
    int16_t actual_male_female_forward;
    int16_t actual_male_female_reverse;
    uint8_t gender_dependent;
    uint8_t recipe_type;
};

struct boss_mapping {
    uint16_t released_index;
    int16_t boss_source;
    uint16_t source_tribe;
    uint16_t boss_tribe;
    uint8_t valid;
};

typedef void *(*get_owner_fn)(void *);
typedef struct runtime_array *(*generate_keys_fn)(struct runtime_array *, void *);
typedef void *(*find_row_fn)(void *, uint64_t, const void *, int);
typedef void *(*manager_find_row_fn)(void *, uint64_t);
typedef void *(*alloc_fn)(size_t, uint32_t);
typedef uint16_t (*get_tribe_fn)(void *, uint64_t);
typedef void (*free_fn)(void *);
typedef uint64_t (*breed_fn)(void *, void *, void *, void *);
typedef uint64_t (*boss_variant_fn)(void *, uint64_t);

static _Atomic(void *) g_manager = NULL;
static _Alignas(16) uint8_t g_parent_a[0x400];
static _Alignas(16) uint8_t g_parent_b[0x400];
static _Alignas(16) uint8_t g_breeding_context[0x10];
static _Alignas(16) uint8_t g_fake_manager[0x200];
static uint8_t g_raw_table_token;
static uint8_t g_unique_table_token;
static uint64_t *g_raw_names = NULL;
static uint64_t *g_unique_names = NULL;
static uint8_t *g_raw_row_storage = NULL;
static uint8_t *g_unique_row_storage = NULL;
static uint32_t g_raw_count = 0u;
static uint32_t g_unique_count = 0u;
static find_row_fn g_find_row_trampoline = NULL;
static find_row_fn g_unique_find_row_trampoline = NULL;
static generate_keys_fn g_generate_keys_trampoline = NULL;
static manager_find_row_fn g_manager_find_row_trampoline = NULL;

static void sleep_seconds(unsigned seconds) {
    struct timespec request = {.tv_sec = (time_t)seconds, .tv_nsec = 0};
    while (nanosleep(&request, &request) != 0 && errno == EINTR) {
    }
}

static void *manager_helper_hook(void *object) {
    void *captured = atomic_load_explicit(&g_manager, memory_order_acquire);
    if (object == g_parent_a || object == g_parent_b) {
        return captured;
    }
    if (object == NULL || ((((uint8_t *)object)[0x0b] & 0x60u) != 0u)) {
        return NULL;
    }
    get_owner_fn get_owner = (get_owner_fn)ADDRESS_GET_OWNER;
    void *first_owner = get_owner(object);
    if (first_owner == NULL || ((((uint8_t *)first_owner)[0x0b] & 0x60u) != 0u)) {
        return NULL;
    }
    void *second_owner = get_owner(object);
    if (second_owner == NULL) {
        return NULL;
    }
    return *(void **)((uint8_t *)second_owner + 0x5a0);
}

static int name_index(const uint64_t *names, uint32_t count, uint64_t name) {
    for (uint32_t index = 0; index < count; ++index) {
        if (names[index] == name) {
            return (int)index;
        }
    }
    return -1;
}

static void *find_row_hook(void *table, uint64_t name, const void *context, int warn) {
    if (table == &g_raw_table_token) {
        int index = name_index(g_raw_names, g_raw_count, name);
        return index < 0 ? NULL : g_raw_row_storage + (size_t)index * RAW_ROW_SIZE;
    }
    if (table == &g_unique_table_token) {
        int index = name_index(g_unique_names, g_unique_count, name);
        return index < 0 ? NULL : g_unique_row_storage + (size_t)index * UNIQUE_ROW_SIZE;
    }
    return g_find_row_trampoline(table, name, context, warn);
}

static void *unique_find_row_hook(void *table, uint64_t name, const void *context, int warn) {
    if (table == &g_unique_table_token) {
        int index = name_index(g_unique_names, g_unique_count, name);
        return index < 0 ? NULL : g_unique_row_storage + (size_t)index * UNIQUE_ROW_SIZE;
    }
    return g_unique_find_row_trampoline(table, name, context, warn);
}

static struct runtime_array *generate_keys_hook(struct runtime_array *result, void *table) {
    const uint64_t *names = NULL;
    uint32_t count = 0u;
    if (table == &g_raw_table_token) {
        names = g_raw_names;
        count = g_raw_count;
    } else if (table == &g_unique_table_token) {
        names = g_unique_names;
        count = g_unique_count;
    } else {
        return g_generate_keys_trampoline(result, table);
    }
    result->data = NULL;
    result->count = 0;
    result->capacity = 0;
    if (count == 0u) {
        return result;
    }
    alloc_fn runtime_alloc = (alloc_fn)ADDRESS_ALLOC;
    result->data = runtime_alloc((size_t)count * sizeof(*result->data), 0u);
    if (result->data == NULL) {
        return result;
    }
    memcpy(result->data, names, (size_t)count * sizeof(*result->data));
    result->count = (int32_t)count;
    result->capacity = (int32_t)count;
    return result;
}

static void *manager_find_row_hook(void *manager, uint64_t name) {
    if (manager == g_fake_manager) {
        int index = name_index(g_raw_names, g_raw_count, name);
        return index < 0 ? NULL : g_raw_row_storage + (size_t)index * RAW_ROW_SIZE;
    }
    return g_manager_find_row_trampoline(manager, name);
}

static int install_absolute_hook(uintptr_t address, const uint8_t *expected_prefix,
                                 size_t prefix_size, uintptr_t hook,
                                 uintptr_t *trampoline_out) {
    if (prefix_size < 12u) {
        return -1;
    }
    uint8_t *target = (uint8_t *)address;
    if (memcmp(target, expected_prefix, prefix_size) != 0) {
        return -1;
    }
    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size <= 0) {
        return -1;
    }
    if (trampoline_out != NULL) {
        uint8_t *trampoline = mmap(NULL, (size_t)page_size, PROT_READ | PROT_WRITE,
                                   MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (trampoline == MAP_FAILED) {
            return -1;
        }
        memcpy(trampoline, expected_prefix, prefix_size);
        trampoline[prefix_size] = 0x48;
        trampoline[prefix_size + 1u] = 0xb8;
        uintptr_t continuation = address + prefix_size;
        memcpy(trampoline + prefix_size + 2u, &continuation, sizeof(continuation));
        trampoline[prefix_size + 10u] = 0xff;
        trampoline[prefix_size + 11u] = 0xe0;
        if (mprotect(trampoline, (size_t)page_size, PROT_READ | PROT_EXEC) != 0) {
            munmap(trampoline, (size_t)page_size);
            return -1;
        }
        *trampoline_out = (uintptr_t)trampoline;
    }
    uintptr_t page = address & ~((uintptr_t)page_size - 1u);
    if (mprotect((void *)page, (size_t)page_size, PROT_READ | PROT_WRITE | PROT_EXEC) != 0) {
        return -1;
    }
    uint8_t patch[12] = {0x48, 0xb8};
    memcpy(patch + 2, &hook, sizeof(hook));
    patch[10] = 0xff;
    patch[11] = 0xe0;
    memcpy(target, patch, sizeof(patch));
    if (prefix_size > sizeof(patch)) {
        memset(target + sizeof(patch), 0x90, prefix_size - sizeof(patch));
    }
    __builtin___clear_cache((char *)target, (char *)target + prefix_size);
    if (mprotect((void *)page, (size_t)page_size, PROT_READ | PROT_EXEC) != 0) {
        return -1;
    }
    return 0;
}

static int install_runtime_hooks(void) {
    static const uint8_t manager_prefix[12] = {
        0x53, 0x48, 0x85, 0xff, 0x74, 0x09, 0x48, 0x89, 0xfb, 0xf6, 0x47, 0x0b,
    };
    static const uint8_t find_row_prefix[12] = {
        0x41, 0x57, 0x41, 0x56, 0x53, 0x48, 0x8b, 0x5f, 0x28, 0x48, 0x85, 0xdb,
    };
    static const uint8_t generate_keys_prefix[14] = {
        0x53, 0x48, 0x89, 0xfb, 0x0f, 0x57, 0xc0,
        0x0f, 0x11, 0x07, 0x48, 0x8d, 0x7e, 0x30,
    };
    static const uint8_t manager_find_row_prefix[14] = {
        0x41, 0x57, 0x41, 0x56, 0x41, 0x54, 0x53,
        0x48, 0x81, 0xec, 0x18, 0x01, 0x00, 0x00,
    };
    uintptr_t trampoline = 0u;
    if (install_absolute_hook(ADDRESS_FIND_ROW, find_row_prefix, sizeof(find_row_prefix),
                              (uintptr_t)&find_row_hook, &trampoline) != 0) {
        return -1;
    }
    g_find_row_trampoline = (find_row_fn)trampoline;
    if (install_absolute_hook(ADDRESS_UNIQUE_FIND_ROW, find_row_prefix, sizeof(find_row_prefix),
                              (uintptr_t)&unique_find_row_hook, &trampoline) != 0) {
        return -1;
    }
    g_unique_find_row_trampoline = (find_row_fn)trampoline;
    if (install_absolute_hook(ADDRESS_GENERATE_KEYS, generate_keys_prefix,
                              sizeof(generate_keys_prefix), (uintptr_t)&generate_keys_hook,
                              &trampoline) != 0) {
        return -1;
    }
    g_generate_keys_trampoline = (generate_keys_fn)trampoline;
    if (install_absolute_hook(ADDRESS_MANAGER_FIND_ROW, manager_find_row_prefix,
                              sizeof(manager_find_row_prefix),
                              (uintptr_t)&manager_find_row_hook, &trampoline) != 0) {
        return -1;
    }
    g_manager_find_row_trampoline = (manager_find_row_fn)trampoline;
    return install_absolute_hook(ADDRESS_MANAGER_HELPER, manager_prefix, sizeof(manager_prefix),
                                 (uintptr_t)&manager_helper_hook, NULL);
}

static int read_full(int fd, void *buffer, size_t size) {
    uint8_t *cursor = buffer;
    while (size > 0u) {
        ssize_t result = read(fd, cursor, size);
        if (result == 0) {
            return -1;
        }
        if (result < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        cursor += (size_t)result;
        size -= (size_t)result;
    }
    return 0;
}

static int source_for_name(const struct runtime_raw_row *rows, uint32_t count, uint64_t name) {
    for (uint32_t index = 0; index < count; ++index) {
        if (rows[index].name == name) {
            return (int)index;
        }
    }
    return -1;
}

static void set_parent(uint8_t *parent, uint64_t name, uint8_t gender) {
    memset(parent, 0, 0x400);
    memcpy(parent + 0x3d0, &name, sizeof(name));
    parent[0x3e0] = gender;
}

static int write_failure(const char *output_path, const char *reason) {
    FILE *output = fopen(output_path, "w");
    if (output == NULL) {
        return -1;
    }
    fprintf(output, "{\n  \"schemaVersion\": 1,\n  \"status\": \"failed\",\n"
                    "  \"reason\": \"%s\"\n}\n", reason);
    int result = fclose(output);
    return result == 0 ? 0 : -1;
}

static int write_result(
    const char *output_path,
    const struct input_header *header,
    const struct runtime_raw_row *runtime_rows,
    const struct row_mismatch *row_mismatches,
    uint32_t row_mismatch_count,
    const struct unique_mismatch *unique_mismatches,
    uint32_t unique_mismatch_count,
    const struct pair_mismatch *pair_mismatches,
    uint32_t pair_mismatch_count,
    uint32_t logical_mismatch_count,
    const struct boss_mapping *boss_mappings,
    uint32_t boss_mapping_count,
    uint32_t boss_mapping_mismatch_count,
    uint32_t parent_order_mismatch_count,
    uint32_t hidden_gender_mismatch_count,
    uint32_t call_mismatch_count,
    uint32_t same_species_mismatch_count,
    uint32_t special_mismatch_count,
    uint32_t normal_mismatch_count,
    uint8_t male_code,
    uint8_t female_code,
    uint64_t invocation_count) {
    size_t temporary_size = strlen(output_path) + 5u;
    char *temporary_path = malloc(temporary_size);
    if (temporary_path == NULL) {
        return -1;
    }
    snprintf(temporary_path, temporary_size, "%s.tmp", output_path);
    FILE *output = fopen(temporary_path, "w");
    if (output == NULL) {
        free(temporary_path);
        return -1;
    }
    bool matched = row_mismatch_count == 0u && unique_mismatch_count == 0u &&
                   logical_mismatch_count == 0u && boss_mapping_mismatch_count == 0u &&
                   parent_order_mismatch_count == 0u && hidden_gender_mismatch_count == 0u;
    fprintf(output,
            "{\n"
            "  \"schemaVersion\": 1,\n"
            "  \"status\": \"%s\",\n"
            "  \"serverBuildId\": \"24181105\",\n"
            "  \"nativeFunctionAddress\": \"0x71168c0\",\n"
            "  \"managerHelperAddress\": \"0x76459e0\",\n"
            "  \"rawPalRowCount\": %u,\n"
            "  \"releasedPalCount\": %u,\n"
            "  \"uniqueCombinationRowCount\": %u,\n"
            "  \"unorderedPairCount\": %u,\n"
            "  \"logicalResultRowCount\": %u,\n"
            "  \"nativeInvocationCount\": %" PRIu64 ",\n"
            "  \"maleRuntimeCode\": %u,\n"
            "  \"femaleRuntimeCode\": %u,\n"
            "  \"runtimeRowMetadataMismatchCount\": %u,\n"
            "  \"runtimeUniqueRowMismatchCount\": %u,\n"
            "  \"runtimeLogicalResultMismatchCount\": %u,\n"
            "  \"mismatchingParentPairCount\": %u,\n"
            "  \"runtimeCallMismatchCount\": %u,\n"
            "  \"parentOrderMismatchCount\": %u,\n"
            "  \"hiddenGenderMismatchCount\": %u,\n"
            "  \"sameSpeciesMismatchCount\": %u,\n"
            "  \"specialCombinationMismatchCount\": %u,\n"
            "  \"normalSelectionMismatchCount\": %u,\n"
            "  \"bossVariantMappingCount\": %u,\n"
            "  \"bossVariantMappingMismatchCount\": %u,\n",
            matched ? "fixed-build-native-runtime-matched" : "mismatch",
            header->raw_count, header->released_count, header->unique_count,
            header->pair_count, header->logical_count, invocation_count,
            male_code, female_code, row_mismatch_count, unique_mismatch_count,
            logical_mismatch_count, pair_mismatch_count, call_mismatch_count,
            parent_order_mismatch_count, hidden_gender_mismatch_count,
            same_species_mismatch_count,
            special_mismatch_count, normal_mismatch_count, boss_mapping_count,
            boss_mapping_mismatch_count);

    fputs("  \"runtimeRows\": [", output);
    for (uint32_t index = 0; index < header->raw_count; ++index) {
        const struct runtime_raw_row *row = &runtime_rows[index];
        fprintf(output,
                "%s\n    {\"sourceOrder\": %u, \"runtimeName\": \"%016" PRIx64
                "\", \"tribeId\": %u, \"combiRank\": %d, "
                "\"combiDuplicatePriority\": %d, \"isBoss\": %s, \"ignoreCombi\": %s}",
                index == 0u ? "" : ",", index, row->name, row->tribe,
                row->rank, row->priority, row->boss ? "true" : "false",
                row->ignore ? "true" : "false");
    }
    fputs("\n  ],\n", output);

    fputs("  \"rowMetadataMismatches\": [", output);
    for (uint32_t index = 0; index < row_mismatch_count; ++index) {
        const struct row_mismatch *item = &row_mismatches[index];
        fprintf(output,
                "%s\n    {\"sourceOrder\": %u, \"expectedRank\": %d, \"actualRank\": %d, "
                "\"expectedPriority\": %d, \"actualPriority\": %d, "
                "\"expectedBoss\": %u, \"actualBoss\": %u, "
                "\"expectedIgnore\": %u, \"actualIgnore\": %u}",
                index == 0u ? "" : ",", item->source_order,
                item->expected_rank, item->actual_rank,
                item->expected_priority, item->actual_priority,
                item->expected_boss, item->actual_boss,
                item->expected_ignore, item->actual_ignore);
    }
    fputs("\n  ],\n", output);

    fputs("  \"uniqueRowMismatches\": [", output);
    for (uint32_t index = 0; index < unique_mismatch_count; ++index) {
        const struct unique_mismatch *item = &unique_mismatches[index];
        fprintf(output,
                "%s\n    {\"sourceOrder\": %u, \"expectedParentA\": %d, \"actualParentA\": %d, "
                "\"expectedParentB\": %d, \"actualParentB\": %d, "
                "\"expectedChildSource\": %d, \"actualChildSource\": %d, "
                "\"expectedGenderA\": %d, \"actualGenderA\": %d, "
                "\"expectedGenderB\": %d, \"actualGenderB\": %d}",
                index == 0u ? "" : ",", item->source_order,
                item->expected_parent_a, item->actual_parent_a,
                item->expected_parent_b, item->actual_parent_b,
                item->expected_child, item->actual_child,
                item->expected_gender_a, item->actual_gender_a,
                item->expected_gender_b, item->actual_gender_b);
    }
    fputs("\n  ],\n", output);

    fputs("  \"logicalResultMismatches\": [", output);
    for (uint32_t index = 0; index < pair_mismatch_count; ++index) {
        const struct pair_mismatch *item = &pair_mismatches[index];
        fprintf(output,
                "%s\n    {\"pairIndex\": %u, \"parentA\": %u, \"parentB\": %u, "
                "\"expectedFemaleMaleSource\": %d, \"actualFemaleMaleForward\": %d, "
                "\"actualFemaleMaleReverse\": %d, \"expectedMaleFemaleSource\": %d, "
                "\"actualMaleFemaleForward\": %d, \"actualMaleFemaleReverse\": %d, "
                "\"genderDependent\": %s, \"recipeType\": %u}",
                index == 0u ? "" : ",", item->pair_index,
                item->parent_a, item->parent_b,
                item->expected_female_male_source,
                item->actual_female_male_forward,
                item->actual_female_male_reverse,
                item->expected_male_female_source,
                item->actual_male_female_forward,
                item->actual_male_female_reverse,
                item->gender_dependent ? "true" : "false", item->recipe_type);
    }
    fputs("\n  ],\n", output);

    fputs("  \"bossVariantMappings\": [", output);
    for (uint32_t index = 0; index < header->released_count; ++index) {
        const struct boss_mapping *item = &boss_mappings[index];
        fprintf(output,
                "%s\n    {\"releasedIndex\": %u, \"bossSourceOrder\": %d, "
                "\"sourceTribeId\": %u, \"bossTribeId\": %u, \"valid\": %s}",
                index == 0u ? "" : ",", item->released_index,
                item->boss_source, item->source_tribe, item->boss_tribe,
                item->valid ? "true" : "false");
    }
    fputs("\n  ]\n}\n", output);

    if (fflush(output) != 0 || fsync(fileno(output)) != 0 || fclose(output) != 0) {
        unlink(temporary_path);
        free(temporary_path);
        return -1;
    }
    int result = rename(temporary_path, output_path);
    free(temporary_path);
    return result;
}

static void *audit_thread(void *unused) {
    (void)unused;
    const char *input_path = getenv("PAL_NATIVE_AUDIT_INPUT");
    const char *output_path = getenv("PAL_NATIVE_AUDIT_OUTPUT");
    if (input_path == NULL || output_path == NULL) {
        return NULL;
    }
    write_failure(output_path, "audit-thread-started");
    int input_fd = open(input_path, O_RDONLY | O_CLOEXEC);
    if (input_fd < 0) {
        write_failure(output_path, "input-open-failed");
        kill(getpid(), SIGTERM);
        return NULL;
    }
    struct stat input_stat;
    if (fstat(input_fd, &input_stat) != 0 || input_stat.st_size < (off_t)sizeof(struct input_header)) {
        close(input_fd);
        write_failure(output_path, "input-stat-failed");
        kill(getpid(), SIGTERM);
        return NULL;
    }
    uint8_t *input = malloc((size_t)input_stat.st_size);
    if (input == NULL || read_full(input_fd, input, (size_t)input_stat.st_size) != 0) {
        close(input_fd);
        free(input);
        write_failure(output_path, "input-read-failed");
        kill(getpid(), SIGTERM);
        return NULL;
    }
    close(input_fd);
    const struct input_header *header = (const struct input_header *)input;
    size_t expected_size = sizeof(*header) +
        (size_t)header->raw_count * sizeof(struct raw_expected) +
        (size_t)header->released_count * sizeof(struct released_expected) +
        (size_t)header->unique_count * sizeof(struct unique_expected) +
        (size_t)header->pair_count * sizeof(struct pair_expected);
    if (memcmp(header->magic, "PWNRT01", 8u) != 0 || header->schema_version != 1u ||
        header->raw_record_size != RAW_RECORD_SIZE ||
        header->released_record_size != RELEASED_RECORD_SIZE ||
        header->unique_record_size != UNIQUE_RECORD_SIZE ||
        header->pair_record_size != PAIR_RECORD_SIZE ||
        expected_size != (size_t)input_stat.st_size) {
        free(input);
        write_failure(output_path, "input-schema-mismatch");
        kill(getpid(), SIGTERM);
        return NULL;
    }
    const uint8_t *cursor = input + sizeof(*header);
    const struct raw_expected *raw = (const struct raw_expected *)cursor;
    cursor += (size_t)header->raw_count * sizeof(*raw);
    const struct released_expected *released = (const struct released_expected *)cursor;
    cursor += (size_t)header->released_count * sizeof(*released);
    const struct unique_expected *unique = (const struct unique_expected *)cursor;
    cursor += (size_t)header->unique_count * sizeof(*unique);
    const struct pair_expected *pairs = (const struct pair_expected *)cursor;

    generate_keys_fn generate_keys = (generate_keys_fn)ADDRESS_GENERATE_KEYS;
    find_row_fn find_row = (find_row_fn)ADDRESS_FIND_ROW;
    get_tribe_fn get_tribe = (get_tribe_fn)ADDRESS_GET_TRIBE;
    free_fn runtime_free = (free_fn)ADDRESS_FREE;
    breed_fn breed = (breed_fn)ADDRESS_BREED;
    boss_variant_fn boss_variant = (boss_variant_fn)ADDRESS_BOSS_VARIANT;
    struct runtime_array raw_keys = {0};
    struct runtime_array unique_keys = {0};
    void *raw_table = &g_raw_table_token;
    void *unique_table = &g_unique_table_token;
    sleep_seconds(10u);
    g_raw_names = calloc(header->raw_count, sizeof(*g_raw_names));
    g_unique_names = calloc(header->unique_count, sizeof(*g_unique_names));
    g_raw_row_storage = calloc(header->raw_count, RAW_ROW_SIZE);
    g_unique_row_storage = calloc(header->unique_count, UNIQUE_ROW_SIZE);
    if (g_raw_names == NULL || g_unique_names == NULL ||
        g_raw_row_storage == NULL || g_unique_row_storage == NULL) {
        free(input);
        write_failure(output_path, "fixed-build-row-materialization-failed");
        kill(getpid(), SIGTERM);
        return NULL;
    }
    for (uint32_t index = 0; index < header->raw_count; ++index) {
        uint8_t *row = g_raw_row_storage + (size_t)index * RAW_ROW_SIZE;
        g_raw_names[index] = (uint64_t)(0x60000000u + index);
        memcpy(row + 0x2a, &raw[index].tribe_id, sizeof(raw[index].tribe_id));
        row[0xcc] = raw[index].is_boss;
        memcpy(row + 0x100, &raw[index].combi_rank, sizeof(raw[index].combi_rank));
        memcpy(row + 0x104, &raw[index].duplicate_priority,
               sizeof(raw[index].duplicate_priority));
        row[0x108] = raw[index].ignore_combi;
    }
    for (uint32_t index = 0; index < header->unique_count; ++index) {
        const struct unique_expected *expected = &unique[index];
        if (expected->parent_a_source >= header->raw_count ||
            expected->parent_b_source >= header->raw_count ||
            expected->child_source >= header->raw_count) {
            free(input);
            write_failure(output_path, "fixed-build-unique-source-out-of-range");
            kill(getpid(), SIGTERM);
            return NULL;
        }
        uint8_t *row = g_unique_row_storage + (size_t)index * UNIQUE_ROW_SIZE;
        g_unique_names[index] = (uint64_t)(0x61000000u + index);
        memcpy(row + 0x08, &raw[expected->parent_a_source].tribe_id,
               sizeof(raw[expected->parent_a_source].tribe_id));
        row[0x0a] = expected->gender_a;
        memcpy(row + 0x0c, &raw[expected->parent_b_source].tribe_id,
               sizeof(raw[expected->parent_b_source].tribe_id));
        row[0x0e] = expected->gender_b;
        memcpy(row + 0x10, &g_raw_names[expected->child_source],
               sizeof(g_raw_names[expected->child_source]));
    }
    g_raw_count = header->raw_count;
    g_unique_count = header->unique_count;
    write_failure(output_path, "fixed-build-rows-materialized");
    memset(g_fake_manager, 0, sizeof(g_fake_manager));
    memcpy(g_fake_manager + 0xd8, &raw_table, sizeof(raw_table));
    memcpy(g_fake_manager + 0xe0, &raw_table, sizeof(raw_table));
    memcpy(g_fake_manager + 0x140, &unique_table, sizeof(unique_table));
    void *manager = g_fake_manager;
    atomic_store_explicit(&g_manager, manager, memory_order_release);
    write_failure(output_path, "audit-manager-ready");
    generate_keys(&raw_keys, raw_table);
    generate_keys(&unique_keys, unique_table);
    write_failure(output_path, "audit-keys-generated");
    if (raw_keys.count != (int32_t)header->raw_count ||
        unique_keys.count != (int32_t)header->unique_count) {
        if (raw_keys.data != NULL) runtime_free(raw_keys.data);
        if (unique_keys.data != NULL) runtime_free(unique_keys.data);
        free(input);
        write_failure(output_path, "runtime-table-count-mismatch");
        kill(getpid(), SIGTERM);
        return NULL;
    }

    struct runtime_raw_row *runtime_rows = calloc(header->raw_count, sizeof(*runtime_rows));
    struct row_mismatch *row_mismatches = calloc(header->raw_count, sizeof(*row_mismatches));
    struct unique_mismatch *unique_mismatches = calloc(header->unique_count, sizeof(*unique_mismatches));
    struct pair_mismatch *pair_mismatches = calloc(header->logical_count, sizeof(*pair_mismatches));
    struct boss_mapping *boss_mappings = calloc(header->released_count, sizeof(*boss_mappings));
    bool *released_sources = calloc(header->raw_count, sizeof(*released_sources));
    if (runtime_rows == NULL || row_mismatches == NULL || unique_mismatches == NULL ||
        pair_mismatches == NULL || boss_mappings == NULL || released_sources == NULL) {
        write_failure(output_path, "allocation-failed");
        kill(getpid(), SIGTERM);
        return NULL;
    }

    uint32_t row_mismatch_count = 0u;
    struct { void *data; int32_t count; int32_t capacity; } empty_context = {0};
    for (uint32_t index = 0; index < header->raw_count; ++index) {
        uint64_t name = raw_keys.data[index];
        void *row = find_row(raw_table, name, &empty_context, 0);
        if (row == NULL) {
            write_failure(output_path, "runtime-row-lookup-failed");
            kill(getpid(), SIGTERM);
            return NULL;
        }
        struct runtime_raw_row *actual = &runtime_rows[index];
        actual->name = name;
        actual->row = row;
        actual->tribe = get_tribe(manager, name);
        actual->rank = *(int32_t *)((uint8_t *)row + 0x100);
        actual->priority = *(int32_t *)((uint8_t *)row + 0x104);
        actual->boss = *((uint8_t *)row + 0xcc) != 0u;
        actual->ignore = *((uint8_t *)row + 0x108) != 0u;
        const struct raw_expected *expected = &raw[index];
        bool mismatch = expected->source_order != (int32_t)index ||
                        expected->combi_rank != actual->rank ||
                        expected->duplicate_priority != actual->priority ||
                        expected->is_boss != actual->boss ||
                        expected->ignore_combi != actual->ignore;
        if (mismatch) {
            struct row_mismatch *item = &row_mismatches[row_mismatch_count++];
            item->source_order = index;
            item->expected_rank = expected->combi_rank;
            item->actual_rank = actual->rank;
            item->expected_priority = expected->duplicate_priority;
            item->actual_priority = actual->priority;
            item->expected_boss = expected->is_boss;
            item->actual_boss = actual->boss;
            item->expected_ignore = expected->ignore_combi;
            item->actual_ignore = actual->ignore;
        }
    }
    write_failure(output_path, "audit-raw-rows-validated");
    for (uint32_t index = 0; index < header->released_count; ++index) {
        if (released[index].source_order >= header->raw_count) {
            write_failure(output_path, "released-source-out-of-range");
            kill(getpid(), SIGTERM);
            return NULL;
        }
        released_sources[released[index].source_order] = true;
    }

    if (header->unique_count <= 79u) {
        write_failure(output_path, "gender-evidence-rows-missing");
        kill(getpid(), SIGTERM);
        return NULL;
    }
    void *gender_row_78 = find_row(unique_table, unique_keys.data[78], &empty_context, 0);
    void *gender_row_79 = find_row(unique_table, unique_keys.data[79], &empty_context, 0);
    if (gender_row_78 == NULL || gender_row_79 == NULL) {
        write_failure(output_path, "runtime-gender-code-evidence-missing");
        kill(getpid(), SIGTERM);
        return NULL;
    }
    uint8_t male_code = *((uint8_t *)gender_row_78 + 0x0a);
    uint8_t female_code = *((uint8_t *)gender_row_78 + 0x0e);
    if (male_code == 0u || female_code == 0u || male_code == female_code ||
        *((uint8_t *)gender_row_79 + 0x0a) != female_code ||
        *((uint8_t *)gender_row_79 + 0x0e) != male_code) {
        write_failure(output_path, "runtime-gender-code-evidence-mismatch");
        kill(getpid(), SIGTERM);
        return NULL;
    }

    uint32_t unique_mismatch_count = 0u;
    for (uint32_t index = 0; index < header->unique_count; ++index) {
        void *row = find_row(unique_table, unique_keys.data[index], &empty_context, 0);
        const struct unique_expected *expected = &unique[index];
        int actual_parent_a = *(uint16_t *)((uint8_t *)row + 0x08);
        int actual_parent_b = *(uint16_t *)((uint8_t *)row + 0x0c);
        int actual_child = source_for_name(runtime_rows, header->raw_count,
                                           *(uint64_t *)((uint8_t *)row + 0x10));
        int actual_gender_a = *((uint8_t *)row + 0x0a);
        int actual_gender_b = *((uint8_t *)row + 0x0e);
        int expected_parent_a = runtime_rows[expected->parent_a_source].tribe;
        int expected_parent_b = runtime_rows[expected->parent_b_source].tribe;
        int expected_gender_a = expected->gender_a == 0u ? 0 :
                                (expected->gender_a == 1u ? male_code : female_code);
        int expected_gender_b = expected->gender_b == 0u ? 0 :
                                (expected->gender_b == 1u ? male_code : female_code);
        bool mismatch = actual_parent_a != expected_parent_a ||
                        actual_parent_b != expected_parent_b ||
                        actual_child != expected->child_source ||
                        actual_gender_a != expected_gender_a ||
                        actual_gender_b != expected_gender_b;
        if (mismatch) {
            struct unique_mismatch *item = &unique_mismatches[unique_mismatch_count++];
            item->source_order = index;
            item->expected_parent_a = expected_parent_a;
            item->actual_parent_a = actual_parent_a;
            item->expected_parent_b = expected_parent_b;
            item->actual_parent_b = actual_parent_b;
            item->expected_child = expected->child_source;
            item->actual_child = actual_child;
            item->expected_gender_a = expected_gender_a;
            item->actual_gender_a = actual_gender_a;
            item->expected_gender_b = expected_gender_b;
            item->actual_gender_b = actual_gender_b;
        }
    }
    write_failure(output_path, "audit-unique-rows-validated");

    uint32_t pair_mismatch_count = 0u;
    uint32_t logical_mismatch_count = 0u;
    uint32_t parent_order_mismatch_count = 0u;
    uint32_t hidden_gender_mismatch_count = 0u;
    uint32_t call_mismatch_count = 0u;
    uint32_t same_species_mismatch_count = 0u;
    uint32_t special_mismatch_count = 0u;
    uint32_t normal_mismatch_count = 0u;
    uint64_t invocation_count = 0u;
    for (uint32_t index = 0; index < header->pair_count; ++index) {
        if (index != 0u && index % 10000u == 0u) {
            write_failure(output_path, "audit-native-pair-loop-in-progress");
        }
        const struct pair_expected *expected = &pairs[index];
        const struct released_expected *parent_a = &released[expected->parent_a];
        const struct released_expected *parent_b = &released[expected->parent_b];
        uint64_t name_a = runtime_rows[parent_a->source_order].name;
        uint64_t name_b = runtime_rows[parent_b->source_order].name;

        set_parent(g_parent_a, name_a, female_code);
        set_parent(g_parent_b, name_b, male_code);
        uint64_t female_male_forward_name = breed(
            NULL, g_parent_a, g_parent_b, g_breeding_context);
        uint64_t female_male_reverse_name = breed(
            NULL, g_parent_b, g_parent_a, g_breeding_context);
        set_parent(g_parent_a, name_a, male_code);
        set_parent(g_parent_b, name_b, female_code);
        uint64_t male_female_forward_name = breed(
            NULL, g_parent_a, g_parent_b, g_breeding_context);
        uint64_t male_female_reverse_name = breed(
            NULL, g_parent_b, g_parent_a, g_breeding_context);
        invocation_count += 4u;

        int female_male_forward = source_for_name(runtime_rows, header->raw_count,
                                                  female_male_forward_name);
        int female_male_reverse = source_for_name(runtime_rows, header->raw_count,
                                                  female_male_reverse_name);
        int male_female_forward = source_for_name(runtime_rows, header->raw_count,
                                                  male_female_forward_name);
        int male_female_reverse = source_for_name(runtime_rows, header->raw_count,
                                                  male_female_reverse_name);
        int expected_female_male = released[expected->female_male_child].source_order;
        int expected_male_female = released[expected->male_female_child].source_order;
        bool female_male_mismatch = female_male_forward != expected_female_male ||
                                    female_male_reverse != expected_female_male;
        bool male_female_mismatch = male_female_forward != expected_male_female ||
                                    male_female_reverse != expected_male_female;
        if (female_male_forward != expected_female_male) ++call_mismatch_count;
        if (female_male_reverse != expected_female_male) ++call_mismatch_count;
        if (male_female_forward != expected_male_female) ++call_mismatch_count;
        if (male_female_reverse != expected_male_female) ++call_mismatch_count;
        if (female_male_forward != female_male_reverse) ++parent_order_mismatch_count;
        if (male_female_forward != male_female_reverse) ++parent_order_mismatch_count;
        if (!expected->gender_dependent &&
            (female_male_forward != male_female_forward ||
             female_male_reverse != male_female_reverse)) {
            ++hidden_gender_mismatch_count;
        }
        bool logical_mismatch = female_male_mismatch || male_female_mismatch;
        uint32_t logical_rows_mismatched = expected->gender_dependent
            ? (uint32_t)female_male_mismatch + (uint32_t)male_female_mismatch
            : (uint32_t)logical_mismatch;
        logical_mismatch_count += logical_rows_mismatched;
        if (logical_mismatch) {
            struct pair_mismatch *item = &pair_mismatches[pair_mismatch_count++];
            item->pair_index = index;
            item->parent_a = expected->parent_a;
            item->parent_b = expected->parent_b;
            item->expected_female_male_source = (int16_t)expected_female_male;
            item->actual_female_male_forward = (int16_t)female_male_forward;
            item->actual_female_male_reverse = (int16_t)female_male_reverse;
            item->expected_male_female_source = (int16_t)expected_male_female;
            item->actual_male_female_forward = (int16_t)male_female_forward;
            item->actual_male_female_reverse = (int16_t)male_female_reverse;
            item->gender_dependent = expected->gender_dependent;
            item->recipe_type = expected->recipe_type;
            if (expected->parent_a == expected->parent_b) {
                same_species_mismatch_count += logical_rows_mismatched;
            }
            if (expected->recipe_type == 2u) {
                special_mismatch_count += logical_rows_mismatched;
            } else {
                normal_mismatch_count += logical_rows_mismatched;
            }
        }
    }
    write_failure(output_path, "audit-native-pairs-validated");

    uint32_t boss_mapping_count = 0u;
    uint32_t boss_mapping_mismatch_count = 0u;
    for (uint32_t index = 0; index < header->released_count; ++index) {
        uint16_t source = released[index].source_order;
        uint64_t result = boss_variant(manager, runtime_rows[source].name);
        int boss_source = result == 0u ? -1 : source_for_name(runtime_rows, header->raw_count, result);
        struct boss_mapping *mapping = &boss_mappings[index];
        mapping->released_index = (uint16_t)index;
        mapping->boss_source = (int16_t)boss_source;
        mapping->source_tribe = runtime_rows[source].tribe;
        mapping->boss_tribe = boss_source < 0 ? 0u : runtime_rows[boss_source].tribe;
        mapping->valid = boss_source < 0 ||
                         (runtime_rows[boss_source].boss &&
                          !released_sources[boss_source] &&
                          runtime_rows[boss_source].tribe == runtime_rows[source].tribe);
        if (boss_source >= 0) ++boss_mapping_count;
        if (!mapping->valid) ++boss_mapping_mismatch_count;
    }
    write_failure(output_path, "audit-boss-mappings-validated");

    int write_status = write_result(
        output_path, header, runtime_rows, row_mismatches, row_mismatch_count,
        unique_mismatches, unique_mismatch_count, pair_mismatches,
        pair_mismatch_count, logical_mismatch_count, boss_mappings, boss_mapping_count,
        boss_mapping_mismatch_count, parent_order_mismatch_count,
        hidden_gender_mismatch_count, call_mismatch_count,
        same_species_mismatch_count, special_mismatch_count,
        normal_mismatch_count, male_code, female_code, invocation_count);
    if (raw_keys.data != NULL) runtime_free(raw_keys.data);
    if (unique_keys.data != NULL) runtime_free(unique_keys.data);
    free(released_sources);
    free(boss_mappings);
    free(pair_mismatches);
    free(unique_mismatches);
    free(row_mismatches);
    free(runtime_rows);
    free(input);
    if (write_status != 0) {
        write_failure(output_path, "result-write-failed");
    }
    sleep_seconds(1u);
    kill(getpid(), SIGTERM);
    return NULL;
}

__attribute__((constructor)) static void initialize_probe(void) {
    if (getenv("PAL_NATIVE_AUDIT_INPUT") == NULL || getenv("PAL_NATIVE_AUDIT_OUTPUT") == NULL) {
        return;
    }
    if (install_runtime_hooks() != 0) {
        const char *output_path = getenv("PAL_NATIVE_AUDIT_OUTPUT");
        if (output_path != NULL) {
            write_failure(output_path, "runtime-hook-prefix-mismatch");
        }
        return;
    }
    pthread_t thread;
    if (pthread_create(&thread, NULL, audit_thread, NULL) == 0) {
        pthread_detach(thread);
    }
}
