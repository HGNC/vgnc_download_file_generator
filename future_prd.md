# Product Requirements: Generate All VGNC Download Files

## Overview

Add a `--generate-all` CLI option that automatically generates all possible VGNC download files for all species, chromosomes, locus types, and file types.

## Problem Statement

Currently, users must run multiple CLI commands to generate all required files:
- Separate commands for each species
- Separate commands for each chromosome
- Separate commands for each file type (vgnc_public, vgnc_ensembl, vgnc_withdrawn)
- Manual tracking of what has been generated

This is:
- **Time-consuming**: Requires many manual commands
- **Error-prone**: Easy to miss combinations or duplicate work
- **Hard to maintain**: No easy way to regenerate all files after database updates

## Goals

### Primary Goal
Provide a single command that generates all VGNC download files:
```bash
vgnc-download-file-generator --generate-all
```

### Secondary Goals
1. **Progress tracking**: Show progress across hundreds of files
2. **Resume capability**: Skip already-generated files (unless --force)
3. **Parallel execution**: Optional parallel processing for speed
4. **Selective generation**: Allow filtering what to generate

## Functional Requirements

### FR1: Generate All Command
**Priority**: P0 (Must Have)

The CLI shall accept a `--generate-all` flag that:
- Generates all file types for all species
- Includes all chromosome-specific files
- Includes all locus type files
- Includes all locus group files
- Includes "All" species files (vgnc_ensembl, vgnc_withdrawn)
- Generates both TSV and JSON formats

**Example:**
```bash
vgnc-download-file-generator --generate-all
```

### FR2: Discover Database Content
**Priority**: P0 (Must Have)

The generator shall:
- Query the `species` table to get all live species
- Query the `chromosomes` table to discover all chromosomes for each species
- Query the `locus_type` table to get all locus types
- Query the `locus_group` table to get all locus groups

### FR3: File Type Combinations
**Priority**: P0 (Must Have)

Generate files for each combination:

1. **Per Species, Per Chromosome** (vgnc_public)
   - `json/{species}/{species}_vgnc_gene_set_chr_{chromosome}.txt`
   - `json/{species}/{species}_vgnc_gene_set_chr_{chromosome}.json`

2. **Per Species, Per Locus Type** (vgnc_public)
   - `json/{species}/locus_types/{species}_{locus_type}_All.txt`
   - `json/{species}/locus_types/{species}_{locus_type}_All.json`

3. **Per Species, Per Locus Group** (vgnc_public)
   - `json/{species}/locus_groups/{species}_{locus_group}_All.txt`
   - `json/{species}/locus_groups/{species}_{locus_group}_All.json`

4. **All Species** (vgnc_ensembl)
   - `ensembl/VGNC_to_Ensembl_mapping.txt`

5. **All Species** (vgnc_withdrawn)
   - `withdrawn/{species}/{species}_withdrawn.txt`
   - For each species with withdrawn entries

### FR4: Progress Display
**Priority**: P1 (Should Have)

Show progress for all files:
```
Generating all VGNC download files...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 45/237 (19%)

Current: cow (9913) - Chromosome X
```

### FR5: Skip Existing Files
**Priority**: P1 (Should Have)

By default:
- Check GCS for existing files
- Skip generation if file exists and is recent
- Use `--force` flag to regenerate all files

### FR6: Parallel Processing
**Priority**: P2 (Nice to Have)

Optional parallel generation:
```bash
vgnc-download-file-generator --generate-all --workers 8
```

### FR7: Selective Generation
**Priority**: P2 (Nice to Have)

Allow filtering what to generate:
```bash
# Only generate TSV files
vgnc-download-file-generator --generate-all --formats tsv

# Only generate for specific species
vgnc-download-file-generator --generate-all --species 9913,9606,9598

# Only generate chromosome files
vgnc-download-file-generator --generate-all --chromosomes-only

# Only generate vgnc_public files
vgnc-download-file-generator --generate-all --file-type vgnc_public
```

## Non-Functional Requirements

### NFR1: Performance
- Should complete full generation in under 1 hour (for ~30 species)
- Memory usage should remain under 2GB
- Should handle 500+ file generations

### NFR2: Reliability
- Must handle failures gracefully
- Continue on individual file errors
- Log all errors for review
- Provide summary report at end

### NFR3: Idempotency
- Running multiple times should produce same results
- File metadata (timestamps) should be consistent

## Technical Implementation

### Database Queries

**Get all species:**
```sql
SELECT taxon_id, display_name, ensembl_species_name
FROM species
WHERE is_live IN ('Y', 'T', 'F')
  AND taxon_id != 9606
ORDER BY taxon_id;
```

**Get chromosomes for a species:**

This query discovers all chromosomes that have gene locations for a given species:

```sql
SELECT DISTINCT
    CASE
        WHEN c.display_name LIKE 'Un%' THEN 'Un'
        WHEN c.display_name LIKE 'Un_%' THEN 'Un'
        ELSE c.display_name
    END as chromosome_name
FROM chromosomes c
JOIN gene_location gl ON c.chr_id = gl.chr_id
JOIN genefam gf ON gl.gene_id = gf.genefam_id
WHERE gf.taxon_id = :taxon_id
ORDER BY chromosome_name;
```

**Important notes:**
- Different species have vastly different chromosome counts
- Unplaced scaffolds (Un0001, Un0002, etc.) are grouped together as "Un"
- Horse has ~5,354 chromosomes in database, but after grouping Un scaffolds, this is much more manageable
- Some species have scaffold naming (e.g., Cat: A1, A2, A3, B1, B2, etc.)
- Some species have haplotype chromosomes
- The query uses JOINs to ensure only chromosomes with actual gene data are returned

**Get all locus types:**
```sql
SELECT DISTINCT type
FROM locus_type
ORDER BY type;
```

**Get all locus groups:**
```sql
SELECT DISTINCT name
FROM locus_group
ORDER BY name;
```

### File Generation Strategy

1. **Discovery Phase**
   - Query all species
   - For each species, discover chromosomes
   - Build list of all file combinations
   - Estimate total file count

2. **Generation Phase**
   - Iterate through combinations
   - Skip existing files (unless --force)
   - Track progress
   - Handle errors

3. **Reporting Phase**
   - Summary statistics
   - Error report
   - GCS paths generated

### CLI Options

```bash
vgnc-download-file-generator --generate-all [OPTIONS]

Options:
  --force                    Regenerate all files, even if they exist
  --workers N                Number of parallel workers (default: 1)
  --formats FORMAT[S]        Only generate specified formats (tsv,json)
  --species IDS              Only generate for specified species
  --file-type TYPE           Only generate specified file type
  --chromosomes-only         Only generate chromosome-specific files
  --locus-only               Only generate locus type/group files
  --dry-run                  Show what would be generated
  --check-only               Only check what's missing, don't generate
```

## Success Metrics

- **Usability**: Single command generates all files
- **Time**: Full generation completes in <1 hour
- **Reliability**: <1% failure rate
- **Completeness**: All expected files are generated

## Future Enhancements

1. **Incremental Updates**: Only regenerate files for changed species
2. **Smart Caching**: Use database modification timestamps
3. **Validation**: Verify all expected files exist after generation
4. **Manifest Generation**: Create manifest file with checksums
5. **Notifications**: Send alerts on completion/failure
