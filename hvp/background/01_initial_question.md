# 01_initial_question.md

## Brief Background

The HVP (Human Virome Project) database integrates two major soil virome datasets into a single PostgreSQL schema: the Global Soil Virus Atlas (GSVA; Graham et al. 2024, Nature Microbiology) and a Hi-C metagenomics study of soil phage-host interactions (Wu et al. 2023, Nature Communications).

The GSVA contributes 49,649 quality-controlled viral contigs from 2,953 globally distributed soil metagenomes, carrying 1,432,147 predicted viral genes with protein sequences and functional annotations across PFAM, KEGG, and CAZy. Phage-host associations come from CRISPR spacer matching against a database of 1.6 million bacterial and archaeal genomes.

The Wu Hi-C dataset provides 583 viral contigs from grassland soils near Prosser, WA, with experimentally validated phage-host links via Hi-C proximity ligation, a method that chemically cross-links phage DNA to host DNA inside intact cells, capturing active infections at the time of sampling. This is complemented by independent CRISPR spacer predictions. Notably, zero overlap was found between Hi-C-detected and CRISPR-predicted phage-host pairs in the Wu study, demonstrating that these methods capture fundamentally different aspects of phage-host biology (active infection vs. historical immunity memory).

Note, the published numbers may differ from the number of metagenomes, genes, contigs, etc in the database.

**Important note on gene terminology:** The 1,432,147 genes in the database are ALL predicted genes on viral contigs. The vast majority are core viral functions (capsid proteins, terminases, replication machinery, etc.). The GSVA paper identified only 5,043 as putative Auxiliary Metabolic Genes (AMGs) based on genomic context (flanked by viral hallmark genes). The database labels these broadly as "avg_gene" (auxiliary viral gene) but this is a misnaming. They are viral genes, not all auxiliary. The AMG-CAT categories (cat0 through cat5, with 924,645 total annotations loaded) indicate confidence levels for AMG classification based on upstream/downstream viral gene context, but even the highest-confidence categories are putative assignments, not experimentally validated AMGs.

## Question

How do phage-host interaction patterns differ between CRISPR-predicted links and
Hi-C experimental links in the integrated soil virome database? Specifically, how
do link counts, unique viral contigs, and unique hosts compare across evidence
methods, and what does that imply about the biology each method captures?

## Hypothesis

Hi-C and CRISPR-spacer links show different host-connectivity distributions
because the two methods capture different biology: CRISPR records historical
immunity (accumulated past infections), while Hi-C captures physical proximity at
sampling time (active infection). We therefore expect CRISPR to yield many more
links and broader host breadth, with little direct overlap between the two
evidence sets. Raw counts are therefore not directly comparable without restricting to
a shared contig/host space.

> Suggested first iteration: summarise `viral_contig_host` links by evidence
> method (count links, unique contigs, unique hosts per method). You run it and
> interpret it. Remember that the methods capture different biology, so raw counts
> are not directly comparable.


## Domain Context and Extended Background

### Data Source 1: Global Soil Virus Atlas (GSVA)

**Citation:** Graham, E.B., Camargo, A.P., Wu, R. et al. A global atlas of soil viruses reveals unexplored biodiversity and potential biogeochemical impacts. Nature Microbiology 9, 1873-1883 (2024).

**Scope:** 2,953 soil metagenomic samples from global repositories (JGI IMG/M, MG-RAST, Earth Microbiome Project, NEON, and individual collaborators), representing 1.25 × 10¹² assembled base pairs.

**Key findings from the paper:**
- 616,935 uncultivated viral genomes (UViGs) screened, 49,649 passed quality control
- Clustered into 38,508 species-level vOTUs (95% ANI, 85% AF); only 13.9% appeared in more than one sample
- 21,160 genus-level and 7,598 family-level clusters
- Rarefaction curves did not saturate, which suggests soil viral diversity remains vastly underexplored
- 1,432,147 viral genes predicted; only ~18% (260,258) had any functional annotation
- 5,043 genes classified as putative AMGs mapping to 83 KEGG pathways
- Most abundant putative AMGs related to carbohydrate metabolism (GT4, GH73, CBM50), suggesting potential impact on soil carbon cycling
- 1,450 viruses linked to hosts from 82 bacterial/archaeal orders via CRISPR spacers
- High host specificity: mean 0.42 hosts per vOTU; most multi-host associations were within the same phylogenetic clade
- Host taxa correlated with soil properties: Acidobacteriales/Geobacterales with nitrogen/SOC/CEC; Pseudomonadales/Mycobacteriales with bulk density/pH

**Virus identification pipeline:** geNomad v1.3.3 for detection + taxonomic assignment, CheckV v1.0.1 for quality assessment. Stringent thresholds applied (virus score >0.8 for >10kb contigs, >0.9 for 5-10kb).

**CRISPR host prediction:** Viral contigs queried against 1.6 million bacterial/archaeal CRISPR spacer database. Required ≥25bp alignment, ≤2 mismatches, ≥95% spacer coverage, ≥2 spacers at the assigned taxonomic rank representing >70% of matches.

### Data Source 2: Wu et al. Hi-C Soil Phage-Host Interactions

**Citation:** Wu, R., Davison, M.R., Nelson, W.C. et al. Hi-C metagenome sequencing reveals soil phage-host interactions. Nature Communications 14, 7666 (2023).

**Scope:** Six replicate grassland soil samples from Prosser, WA (46°15'04"N, 119°43'43"W), collected pre- and post-desiccation (2-week drying incubation at 30°C simulating summer conditions).

**Key findings from the paper:**
- 583 viral contigs identified, clustered into 479 vOTUs (all Caudoviricetes)
- 148 unique MAGs spanning 9 bacterial phyla binned via Hi-C deconvolution
- 118 unique phage-host pairs identified by Hi-C sequencing
- Zero overlap between Hi-C and CRISPR spacer predictions (121 CRISPR pairs, 118 Hi-C pairs, 0 shared)
- Soil drying shifted phage lifestyle from lytic to lysogenic: higher VPH (viral copies per host) but lower transcriptional activity post-desiccation
- Pre-desiccation: VPH negatively correlated with host abundance (p<0.001), suggesting lytic killing
- Post-desiccation: no VPH-abundance correlation, consistent with lysogenic dormancy
- Phage hosts were among the most central nodes in bacterial co-occurrence networks
- Actinobacterial MAG B117 was targeted by 6 vOTUs post-desiccation and was highly central in community networks
- Phage generalists (infecting multiple host MAGs) detected with direct experimental evidence

**Hi-C method:** ProxiMeta Hi-C Kit (Phase Genomics), formaldehyde cross-linking of DNA within intact cells, restriction enzyme digestion (Sau3AI + MlucI), proximity ligation with biotinylated nucleotides, streptavidin pulldown, sequencing on Illumina NovaSeq.

**Why Hi-C matters:** CRISPR spacers record historical immunity (spacers conserved for years, most do not represent current infections). Hi-C captures physically co-localized DNA at the time of sampling, providing direct evidence of active infection. The complete non-overlap between methods means they are complementary, not redundant.


## Database Schema Summary

### Core Tables

| Table | Rows | Description |
|-------|------|-------------|
| `sample` | 2,960 | Soil samples (2,953 GSVA + 6 Wu + 1 Wu fallback) |
| `metagenome` | 2,960 | Sequencing runs/assemblies linked to samples |
| `viral_contig` | 51,398 | Viral contigs (49,649 GSVA + 1,749 Wu across samples) |
| `viral_contig_sequence` | 51,398 | Nucleotide sequences for all contigs |
| `avg_gene` | 1,432,147 | Predicted genes on viral contigs (GSVA only; see note below) |
| `avg_sequence` | 1,432,147 | Protein sequences for all predicted genes |
| `avg_function` | 1,267,490 | Gene↔function annotations (PFAM/CAZy/KEGG/AMG-CAT) |
| `avg_evidence` | 924,537 | AMG-CAT upstream/downstream context (JSON) |
| `virus_taxon` | 93 | Viral taxonomy tree nodes (geNomad + demovir) |
| `viral_contig_host` | 1,856 | Contig-level phage↔host associations |
| `host` | 338 | Bacterial/archaeal host MAGs (Wu data) |
| `host_alias` | 338 | Alternative host names |
| `contig_cluster` | ~106K | vOTU/genus/family clusters |
| `contig_cluster_member` | 200,345 | Contig↔cluster membership |

### Lookup / Metadata Tables

| Table | Rows | Description |
|-------|------|-------------|
| `resource` | 4+ | Data source citations (GSVA internal, Wu DOI, Wu internal) |
| `study` | 84 | Research studies |
| `location` | 823 | Geographic sampling locations with coordinates |
| `organism_type` | 56 | Controlled vocabulary (Bacteria, Archaea, Bacteriophage, taxonomy leaves) |
| `environment_scheme` | 1 | GOLD ecosystem classification |
| `evidence_method` | 10 | Methods catalog (Hi-C, CRISPR-Spacer, AMG-CAT, PFAM HMM, dbCAN, KEGG, etc.) |
| `function_term` | 54,450+ | Functional annotation vocabulary |

### Important Design Notes

**Wu contigs have NO gene-level data.** The Wu study did not publish gene predictions for their viral contigs. The 1,749 Wu viral_contig rows have no corresponding avg_gene entries. This is reflected in the mismatch report: `contigs_without_genes = 1,749`. Gene-level analyses (avg_gene, avg_sequence, avg_function) are GSVA-only.

**`avg_host` is intentionally empty (0 rows).** An earlier version propagated contig-level host links down to every gene on the contig. This was removed because: (1) GSVA genes are not AMGs. They are all viral genes, and propagating a CRISPR spacer match to 1.4M core viral genes is scientifically meaningless; (2) the contig to host relationship is already queryable via joins through `avg_gene`, `viral_contig`, and `viral_contig_host`; (3) gene-level host evidence should come from direct experimental data (e.g., protein homology to host genes), not bulk inheritance.

**Wu contigs appear under MULTIPLE metagenomes.** Each Wu viral contig was detected in multiple samples (pre/post-desiccation replicates), so a single contig name like `PNNL_D15_k127_29030829` appears as separate `viral_contig` rows under metagenomes SM297, SM306, SM317, etc. The 583 unique contig sequences produce 1,749 viral_contig rows.


## CRITICAL NOTE: Gene Terminology

The database column and table names use "avg" (auxiliary viral gene) broadly, but this is misleading:

**What the 1,432,147 `avg_gene` rows actually are based on the paper:**
- ALL predicted genes on quality-controlled viral contigs from GSVA
- The vast majority (~82%) have NO functional annotation at all
- These include core viral functions: capsid proteins, terminases, portal proteins, tail fibers, DNA polymerases, integrases, etc.
- Only 5,043 were classified as putative AMGs by the GSVA paper's AMG pipeline.
  Note, in our database, we have an updated version with 924,645 annotations.

**AMG-CAT categories loaded (924,645 annotations):**

| Category | Count | Description |
|----------|-------|-------------|
| cat0 | 27,400 | Both upstream AND downstream neighbors are viral hallmark genes (VV-1) |
| cat1 | 38,117 | Both neighbors are virus-specific (hallmark or non-hallmark: VV-1 or V*-0) |
| cat2 | 16,511 | One neighbor is virus-specific, one is unclassified |
| cat3 | 9,231 | Both neighbors are unclassified but on a viral contig |
| cat4 | 8,542 | One neighbor is virus-specific, one is host-like |
| cat5 | 199 | Both neighbors are host-like (least confident as AMG) |

**Interpretation:** Lower category numbers indicate higher confidence that the gene is a true AMG (flanked by viral genes, unlikely to be a misassembled host fragment). However, even cat0/cat1 assignments are computational predictions based on genomic context, not experimental validation. The GSVA paper's published AMG set of 5,043 genes applied additional filters beyond these categories (requiring KEGG pathway membership).


**More Clarification:** 
avg_gene is the GSVA viral gene table and currently contains 1,432,147 viral genes. It is not restricted to confirmed AVGs. Putative AVG-like genes are best represented by the subset with AMG-CAT evidence loaded from AMG_withCAT_new.txt, which appear as AMG_cat0-AMG_cat5 function terms (ontology_id = 'AMG_CAT') and corresponding avg_evidence rows, but this is broader than the paper’s final filtered putative AMG set. In the current build this AMG-CAT-labeled subset contains 924,537 genes. avg_host is 0 because host assignments are currently stored only at the viral contig level (viral_contig_host) and have not been propagated to the gene level (avg_host).

**For analysis:** When studying AMGs specifically, filter to genes that have AMG-CAT annotations AND functional annotations (PFAM/CAZy/KEGG). When studying general viral gene content, the full avg_gene table is appropriate. Additionally, depending on the analysis, avg_host could be propagated from the avg_genes and host_contig data for GSVA and a gene caller could be used for the Hi C Wu Data. However, you must be clear when this happens and that these are called putative avgs rather than evidence linked avgs. 


## ENUM TYPES

| Type | Values | Used By |
|------|--------|---------|
| `evidence_kind` | `'Computational'`, `'Experimental'` | `evidence_method.evidence_type` |
| `sequence_kind` | `'Protein'`, `'Nucleotide'` | `avg_sequence.seq_type`, `viral_contig_sequence.seq_type` |

## EXTENSIONS

citext (case-insensitive text), ltree (hierarchical labels), pg_trgm (trigram fuzzy matching)


## TABLE-BY-TABLE SCHEMA

### 1. resource: Publication / data source references
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `resource_id` | BIGSERIAL | PK | Auto-increment ID |
| `doi` | CITEXT | UNIQUE, nullable | Digital Object Identifier |
| `title` | TEXT | | Human-readable title |
| `url` | TEXT | UNIQUE, nullable | URL (fallback when no DOI) |

Check: At least one of doi or url must be non-NULL.
Seeded with: `'internal://GSVA'`, `'internal://HiC_Wu'`, Wu et al. DOI.

### 2. sample_type: Controlled vocabulary for sample types
| Column | Type | Constraints |
|--------|------|-------------|
| `sample_type_id` | SMALLSERIAL | PK |
| `name` | TEXT | UNIQUE NOT NULL |

Expected values: `'Metagenome'`, `'Soil'`, etc.

### 3. organism_type: Controlled vocabulary for organism classification
| Column | Type | Constraints |
|--------|------|-------------|
| `organism_type_id` | SMALLSERIAL | PK |
| `name` | TEXT | UNIQUE NOT NULL |

Expected values: `'Bacteria'`, `'Archaea'`, `'Microbiome'`, `'Bacteriophage'`, geNomad taxonomy leaf names, `'Unknown'`.

### 4. environment_type: Legacy environment tags
| Column | Type | Constraints |
|--------|------|-------------|
| `environment_type_id` | SMALLSERIAL | PK |
| `name` | TEXT | UNIQUE |

### 5. anatomical_site: Body site (for human-associated samples)
| Column | Type | Constraints |
|--------|------|-------------|
| `anatomical_site_id` | SMALLSERIAL | PK |
| `name` | TEXT | UNIQUE |

Current data: Mostly NULL (soil samples).

### 6. location: Geographic sampling locations
| Column | Type | Constraints |
|--------|------|-------------|
| `location_id` | BIGSERIAL | PK |
| `name` | TEXT | NOT NULL |
| `latitude` | DOUBLE PRECISION | CHECK -90 to 90 |
| `longitude` | DOUBLE PRECISION | CHECK -180 to 180 |

Examples: `'Prosser, WA, USA'`, GSVA geographic locations, `'Unknown'`.

### 7. environment_scheme: Classification system metadata
| Column | Type | Constraints |
|--------|------|-------------|
| `scheme_id` | SMALLSERIAL | PK |
| `name` | CITEXT | UNIQUE NOT NULL |
| `description` | TEXT | |
| `is_hierarchical` | BOOLEAN | DEFAULT true |

Seeded: `'GOLD'` (DOE-JGI GOLD ecosystem classification).

### 8. study: Research studies
| Column | Type | Constraints |
|--------|------|-------------|
| `study_id` | BIGSERIAL | PK |
| `name` | CITEXT | UNIQUE NOT NULL |
| `description` | TEXT | |

Examples: `'Wu et al. Hi-C Soil'`, various GSVA study names.

### 9. resource_study: Many-to-many resources and studies
| Column | Type | Constraints |
|--------|------|-------------|
| `resource_id` | BIGINT | FK → resource, PK part |
| `study_id` | BIGINT | FK → study, PK part |

### 10. sample: Biological samples (central sample record)
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `sample_id` | BIGSERIAL | PK | |
| `sample_type_id` | SMALLINT | FK → sample_type | |
| `organism_type_id` | SMALLINT | FK → organism_type | |
| `anatomical_site_id` | SMALLINT | FK → anatomical_site | |
| `location_id` | BIGINT | FK → location | |
| `external_id` | TEXT | UNIQUE | IMG taxon OID (GSVA) or `'SM297'` etc. (Wu) or `'Wu_HiC_Soil'` |
| `collection_date` | DATE | | |
| `elevation_m` | DOUBLE PRECISION | | Meters |
| `environment_scheme_id` | SMALLINT | FK → environment_scheme | |
| `environment_path` | LTREE | | Hierarchical GOLD path, e.g. `'terrestrial.soil.grassland'` |
| `environment_text` | TEXT | | For non-hierarchical schemes |
| `environment_details` | TEXT | | Free text, e.g. habitat description |

Check: Only one of environment_path or environment_text can be non-NULL.

### 11. sample_study: Many-to-many samples and studies
| Column | Type | Constraints |
|--------|------|-------------|
| `sample_id` | BIGINT | FK → sample, PK part |
| `study_id` | BIGINT | FK → study, PK part |

### 12. resource_sample: Many-to-many resources and samples
| Column | Type | Constraints |
|--------|------|-------------|
| `resource_id` | BIGINT | FK → resource, PK part |
| `sample_id` | BIGINT | FK → sample, PK part |

### 13. sample_environment: Legacy many-to-many samples and environment tags
| Column | Type | Constraints |
|--------|------|-------------|
| `sample_id` | BIGINT | FK → sample, PK part |
| `environment_type_id` | SMALLINT | FK → environment_type, PK part |

### 14. metagenome: Sequencing runs / assemblies
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `metagenome_id` | BIGSERIAL | PK | |
| `sample_id` | BIGINT | FK → sample | |
| `name` | TEXT | NOT NULL | IMG taxon OID (GSVA) or `'SM297'`/`'Wu Soil Hi-C'` (Wu) |
| `external_link` | TEXT | | e.g. `'img:2124908027'` or `'internal://HiC_Wu'` |
| `organism_type_id` | SMALLINT | FK → organism_type | Dominant type across contigs |

### 15. resource_metagenome: Many-to-many resources and metagenomes
| Column | Type | Constraints |
|--------|------|-------------|
| `resource_id` | BIGINT | FK → resource, PK part |
| `metagenome_id` | BIGINT | FK → metagenome, PK part |

### 16. virus_taxon: Viral taxonomy tree (self-referential)
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `taxon_id` | BIGSERIAL | PK | |
| `name` | TEXT | | Node name |
| `rank` | TEXT | | e.g. `'family'`, `'genus'` (often NULL) |
| `parent_id` | BIGINT | FK → self, CHECK ≠ self | |
| `path` | LTREE | GiST-indexed | e.g. `'Viruses.Duplodnaviria.Heunggongvirae...'` |

UNIQUE: (parent_id, name). Siblings must be distinct.
Sources: geNomad taxonomy from GSVA contigs; demovir family classification from Wu contigs (Siphoviridae/Myoviridae/Podoviridae mapped to canonical Caudoviricetes lineage).

### 17. viral_contig: Individual viral contigs ★ CORE TABLE ★
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `contig_id` | BIGSERIAL | PK | |
| `metagenome_id` | BIGINT | FK → metagenome | |
| `name` | TEXT | NOT NULL | Full contig ID |
| `taxon_id` | BIGINT | FK → virus_taxon | |
| `organism_type_id` | SMALLINT | FK → organism_type | Taxonomy leaf as type |
| `img_oid` | TEXT | Trigger-parsed | Digits-only IMG OID |
| `assembly_tag` | TEXT | Trigger-parsed | e.g. `'a'` from `2124908027.a:...` |
| `contig_label` | TEXT | Trigger-parsed | Right-of-colon part |
| `contig_length` | INTEGER | | Nucleotides |
| `n_genes` | INTEGER | | Gene count from metadata |

UNIQUE: (metagenome_id, name).
Trigger: trg_vc_parse_name auto-parses img_oid, assembly_tag, contig_label on INSERT/UPDATE.
Note: Wu contigs appear under MULTIPLE metagenomes (583 unique → 1,749 rows).

### 18. viral_contig_sequence: Nucleotide sequences for contigs
| Column | Type | Constraints |
|--------|------|-------------|
| `contig_id` | BIGINT | PK, FK → viral_contig |
| `sequence` | TEXT | NOT NULL, alphabet-checked |
| `length` | INTEGER | |
| `seq_type` | sequence_kind | DEFAULT `'Nucleotide'` |

### 19. avg_gene: Viral genes on contigs ★ CORE TABLE ★ (see terminology note above)
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `avg_id` | BIGSERIAL | PK | |
| `contig_id` | BIGINT | FK → viral_contig | Parent contig |
| `name` | TEXT | | Full gene ID, e.g. `'2124908027.a:MRS2a_Contig_939_12'` |
| `start_nt` | INTEGER | CHECK ≥ 1 | Start coordinate |
| `end_nt` | INTEGER | CHECK ≥ start | End coordinate |
| `strand` | SMALLINT | CHECK IN (-1, 1) | Forward/reverse |
| `strand_num` | SMALLINT | CHECK IN (1, 2) | Single/double-stranded |
| `length_nt` | INTEGER | | Computed: end - start + 1 |
| `gene_index` | INTEGER | Trigger-parsed | Trailing `_12` → 12 |

UNIQUE: (contig_id, name).
Source: GSVA gene metadata only. Wu contigs have no gene predictions.

### 20. avg_sequence: Protein (or nucleotide) sequences for genes
| Column | Type | Constraints |
|--------|------|-------------|
| `avg_id` | BIGINT | PK, FK → avg_gene |
| `sequence` | TEXT | NOT NULL, alphabet-checked |
| `length` | INTEGER | |
| `seq_type` | sequence_kind | DEFAULT `'Protein'` |

Source: GSVA .faa FASTA files.

### 21. contig_cluster_set: Clustering run definitions
| Column | Type | Constraints |
|--------|------|-------------|
| `cluster_set_id` | BIGSERIAL | PK |
| `name` | TEXT | NOT NULL |
| `method` | TEXT | |
| `version` | TEXT | |
| `parameters` | JSONB | |

UNIQUE: (name, method, version).
Expected sets: `'vOTU'`, `'genus_cluster'`, `'family_cluster'` (GSVA); `'vOTU'` with method `'Dereplication'` (Wu).

### 22. contig_cluster: Individual clusters
| Column | Type | Constraints |
|--------|------|-------------|
| `cluster_id` | BIGSERIAL | PK |
| `cluster_set_id` | BIGINT | FK → contig_cluster_set |
| `name` | TEXT | NOT NULL |
| `representative_contig_id` | BIGINT | FK → viral_contig |

UNIQUE: (cluster_set_id, name).

### 23. contig_cluster_member: Contig and cluster membership
| Column | Type | Constraints |
|--------|------|-------------|
| `contig_id` | BIGINT | FK → viral_contig, PK part |
| `cluster_id` | BIGINT | FK → contig_cluster, PK part |

### 24. evidence_method: Methods used to generate evidence
| Column | Type | Constraints |
|--------|------|-------------|
| `method_id` | BIGSERIAL | PK |
| `method_name` | TEXT | UNIQUE NOT NULL |
| `evidence_type` | evidence_kind | NOT NULL |
| `version` | TEXT | |
| `parameters` | JSONB | |

Seeded Values:
| method_name | evidence_type | Notes |
|-------------|---------------|-------|
| VirSorter2 | Computational | |
| CRISPR-spacer | Experimental | Seeded (GSVA) |
| Hi-C | Experimental | Seeded + Wu filtered links |
| qPCR | Experimental | |
| Hi-C Unfiltered | Experimental | Wu Supp.4 |
| CRISPR-Spacer | Experimental | Wu Supp.7 |
| AMG-CAT | Computational | GSVA AMG context |
| PFAM HMM | Computational | |
| dbCAN | Computational | CAZy annotations |
| KEGG | Computational | |

### 25. applies_to: Scope codes for evidence methods
| Column | Type | Constraints |
|--------|------|-------------|
| `code` | TEXT | PK |
| `description` | TEXT | |

Values: `'avg'`, `'avg_function'`, `'avg_host'`, `'avg_linked_gene'`, `'contig'`, `'taxon'`, `'cluster'`.

### 26. method_scope: Which scopes each method applies to
| Column | Type | Constraints |
|--------|------|-------------|
| `method_id` | BIGINT | FK → evidence_method, PK part |
| `applies_to` | TEXT | FK → applies_to, PK part |

### 27. avg_evidence: Evidence assertions about genes
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `avg_id` | BIGINT | FK → avg_gene, PK part | |
| `method_id` | BIGINT | FK → evidence_method, PK part | |
| `resource_id` | BIGINT | FK → resource, PK part | |
| `details` | TEXT | | JSON with AMG-CAT context |
| `score` | REAL | | |

Content: AMG-CAT upstream/downstream gene context as JSON (924,537 rows).

### 28. function_term: Functional annotation vocabulary
| Column | Type | Constraints |
|--------|------|-------------|
| `function_id` | BIGSERIAL | PK |
| `name` | TEXT | UNIQUE NOT NULL |
| `ontology_id` | TEXT | |

Examples: `'AMG_cat1'`, `'AMG_cat2'`, PFAM domain IDs, CAZyme families, KEGG KO terms.
Ontology IDs: `'AMG_CAT'`, `'PFAM'`, `'CAZy'`, `'KEGG_KO'`.

### 29. avg_function: Gene and function assignments with provenance
| Column | Type | Constraints |
|--------|------|-------------|
| `avg_id` | BIGINT | FK → avg_gene, PK part |
| `function_id` | BIGINT | FK → function_term, PK part |
| `resource_id` | BIGINT | FK → resource, PK part |
| `method_id` | BIGINT | FK → evidence_method, PK part |
| `confidence_score` | REAL | |

This is where PFAM, CAZy, KEGG, and AMG category annotations live (1,267,490 rows).

### 30. host: Bacterial/archaeal host organisms
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `host_id` | BIGSERIAL | PK | |
| `species` | TEXT | NOT NULL | MAG alias (e.g., `PNNL_SM297_bin_1`) |
| `taxonomy` | LTREE | GiST-indexed | GTDB taxonomy as ltree path |
| `ncbi_taxon_id` | INTEGER | | NCBI taxonomy ID (currently all NULL) |
| `strain` | TEXT | | |
| `mag_file_path` | TEXT | | Relative path to MAG .fsa file |

Source: Wu MAG names from Supp. 5/6/7 with GTDB taxonomy from Supp. 6. MAG genome files (.fsa) available on disk.

### 31. host_alias: Alternative names for hosts
| Column | Type | Constraints |
|--------|------|-------------|
| `host_id` | BIGINT | FK → host, PK part |
| `alias` | CITEXT | PK part, GIN trigram-indexed |

### 32. avg_host: Gene-level host links (INTENTIONALLY EMPTY)
| Column | Type | Constraints |
|--------|------|-------------|
| `avg_id` | BIGINT | FK → avg_gene, PK part |
| `host_id` | BIGINT | FK → host, PK part |
| `method_id` | BIGINT | FK → evidence_method, PK part |
| `resource_id` | BIGINT | FK → resource, PK part |

**0 rows.** See design notes above. Gene-level host associations should come from direct evidence (protein homology), not contig-level inheritance.

### 33. viral_contig_host: Contig-level host associations ★ KEY TABLE ★
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `contig_id` | BIGINT | FK → viral_contig, PK part | |
| `host_id` | BIGINT | FK → host, PK part | |
| `method_id` | BIGINT | FK → evidence_method, PK part | Hi-C / CRISPR-Spacer / Hi-C Unfiltered |
| `resource_id` | BIGINT | FK → resource, PK part | |
| `score` | REAL | | Linkage density or bit score |
| `details` | TEXT | | Full row JSON from supplementary data |

### 34. host_gene: Host genes (placeholder)
| Column | Type | Constraints |
|--------|------|-------------|
| `host_gene_id` | BIGSERIAL | PK |
| `symbol` | TEXT | NOT NULL |
| `function` | TEXT | |

Currently 0 rows. This is a placeholder for future Hi-C proximity data.

### 35. avg_linked_host_gene: Gene and proximal host gene links (placeholder)
| Column | Type | Constraints |
|--------|------|-------------|
| `avg_id` | BIGINT | FK → avg_gene, PK part |
| `host_gene_id` | BIGINT | FK → host_gene, PK part |
| `method_id` | BIGINT | FK → evidence_method, PK part |
| `distance_bp` | INTEGER | |
| `resource_id` | BIGINT | FK → resource, PK part |

Currently 0 rows.


## VIEWS

**v_sample_overview** joins: sample + sample_type + organism_type + anatomical_site + location + environment_scheme. Adds: n_metagenomes, n_contigs, n_avg_genes, environment_leaf.

**v_contig_overview** joins: viral_contig + metagenome + sample + organism_type + virus_taxon. Adds: has_nt_sequence, n_avg_genes, n_host_links, votu_clusters, genus_clusters, family_clusters, taxon_leaf.

**v_avg_overview** joins: avg_gene + viral_contig + metagenome + sample + location + virus_taxon + avg_sequence. Adds: has_protein_sequence, protein_length, n_functions, n_evidence, n_avg_host_links.

**v_avg_function_annotations** joins: avg_function + avg_gene + viral_contig + metagenome + sample + function_term + evidence_method + resource. Full provenance chain.

**v_contig_cluster_members** joins: contig_cluster_member + contig_cluster + contig_cluster_set + viral_contig + metagenome. Adds: cluster_size, is_representative.


## ENTITY-RELATIONSHIP FLOW

```
resource ──┬── resource_study ── study ── sample_study ──┐
           ├── resource_sample ──────────────────────────┤
           └── resource_metagenome ──────────────────┐   │
                                                     │   │
sample_type ─┐                                       │   │
organism_type┼── sample ─── metagenome ──── viral_contig ──┬── avg_gene
anatomical_site┘    │           │               │    │     │     │
location ───────────┘           │          virus_taxon│     │     ├── avg_sequence
environment_scheme ─────────────┘               │          │     ├── avg_function ── function_term
                                                │          │     ├── avg_evidence
                                    viral_contig_sequence  │     ├── avg_host ──── host (EMPTY)
                                                           │     └── avg_linked_host_gene ── host_gene (EMPTY)
                                    viral_contig_host ─────┘
                                         │
                                        host ── host_alias
                                         │
                              contig_cluster_member
                                    │
                              contig_cluster ── contig_cluster_set
```


## COMPLETE ROW COUNTS (from latest build)

| Table | Rows |
|-------|------|
| sample | 2,960 |
| metagenome | 2,960 |
| viral_contig | 51,398 |
| viral_contig_sequence | 51,398 |
| avg_gene | 1,432,147 |
| avg_sequence | 1,432,147 |
| avg_function | 1,267,490 |
| avg_evidence | 924,537 |
| avg_host | 0 |
| virus_taxon | 93 |
| viral_contig_host | 1,856 |
| host | 338 |
| host_alias | 338 |
| contig_cluster_member | 200,345 |
| resource | 4+ |
| organism_type | 56 |
| location | 823 |
| study | 84 |
| function_term | 54,450+ |
| evidence_method | 10 |


## Host-Link Breakdown by Method

| Method | Hosts | Contigs | Notes |
|--------|-------|---------|-------|
| Hi-C (filtered) | - | - | TSV + Supp.5 (active infections at sampling time) |
| Hi-C Unfiltered | - | - | Supp.4 (includes borderline links) |
| CRISPR-Spacer | - | - | Wu Supp.7 + GSVA CRISPR predictions (historical immunity) |

Total viral_contig_host rows: 1,856.

*Note: The Wu and GSVA CRISPR methods use different evidence sources. Wu matches spacers from their own MAGs, GSVA matches against a 1.6M genome spacer database. Both are stored with method_name `'CRISPR-Spacer'` but differ by resource_id.*


## Known Data Gaps

### 1. No NCBI Taxon IDs for Hosts
All hosts have `ncbi_taxon_id = NULL`. To retrieve host counterpart sequences from NCBI, GTDB taxonomy must be mapped to NCBI via GTDB-to-NCBI mapping tables (https://data.gtdb.ecogenomic.org/) or NCBI Taxonomy name search.

### 2. Wu Contigs Have No Gene Predictions
The 583 Wu viral contigs (1,749 rows across samples) have nucleotide sequences but no gene calls. Gene-level analyses may require running a gene caller (e.g., Prodigal in metagenomic mode) on `viral_contigs.fna`.

### 3. Mismatch Report from Build

| Issue | Count |
|-------|-------|
| metagenomes_without_contigs | 1,731 |
| contigs_without_genes | 1,749 |
| amg_rows_without_matching_gene | 108 |
| genes_without_protein | 0 |
| proteins_without_matching_gene | 0 |
| contig_fasta_without_matching_contig | 0 |

**metagenomes_without_contigs (1,731):** GSVA metagenomes where no viral contigs passed quality control. Expected. Only 1,229 of 2,953 GSVA samples yielded quality contigs.

**contigs_without_genes (1,749):** All Wu contigs. Expected. Wu did not publish gene predictions.

**amg_rows_without_matching_gene (108):** AMG file entries where the gene name didn't match any avg_gene row. Minor data quality issue.


## Database Interface

**Connection:** PostgreSQL 16, database name `hvp`

**Command-line queries:**
```bash
psql -d hvp -c "YOUR SQL HERE"
```

**Export results to CSV:**
```bash
psql -d hvp -c "\COPY (SELECT * FROM avg_gene LIMIT 100) TO '/tmp/output.csv' WITH (FORMAT csv, HEADER true)"
```


## Example Queries

### Table counts
```sql
psql -d hvp -c "
SELECT 'sample' tbl, count(*) FROM sample
UNION ALL SELECT 'metagenome', count(*) FROM metagenome
UNION ALL SELECT 'viral_contig', count(*) FROM viral_contig
UNION ALL SELECT 'avg_gene', count(*) FROM avg_gene
UNION ALL SELECT 'avg_sequence', count(*) FROM avg_sequence
UNION ALL SELECT 'avg_function', count(*) FROM avg_function
UNION ALL SELECT 'avg_evidence', count(*) FROM avg_evidence
UNION ALL SELECT 'host', count(*) FROM host
UNION ALL SELECT 'viral_contig_host', count(*) FROM viral_contig_host
UNION ALL SELECT 'avg_host', count(*) FROM avg_host
ORDER BY tbl;
"
```

### Host-link method breakdown
```sql
psql -d hvp -c "
SELECT em.method_name,
       count(DISTINCT vch.host_id) AS n_hosts,
       count(DISTINCT vch.contig_id) AS n_contigs
FROM viral_contig_host vch
JOIN evidence_method em ON em.method_id = vch.method_id
GROUP BY em.method_name;
"
```

### AMG-CAT category distribution
```sql
psql -d hvp -c "
SELECT ft.name AS amg_category, count(*) AS n_genes
FROM avg_function af
JOIN function_term ft ON ft.function_id = af.function_id
WHERE ft.ontology_id = 'AMG_CAT'
GROUP BY ft.name ORDER BY ft.name;
"
```

### Genes with BOTH functional annotation AND host link (via contig)
```sql
psql -d hvp -c "
SELECT count(DISTINCT g.avg_id) AS genes_with_function_and_host
FROM avg_gene g
JOIN avg_function af ON af.avg_id = g.avg_id
JOIN viral_contig_host vch ON vch.contig_id = g.contig_id;
"
```

### Top functional categories among host-linked genes
```sql
psql -d hvp -c "
SELECT ft.ontology_id, ft.name, count(DISTINCT af.avg_id) AS n_genes
FROM avg_function af
JOIN function_term ft ON ft.function_id = af.function_id
WHERE af.avg_id IN (
  SELECT g.avg_id FROM avg_gene g
  JOIN viral_contig_host vch ON vch.contig_id = g.contig_id
)
GROUP BY ft.ontology_id, ft.name
ORDER BY n_genes DESC LIMIT 20;
"
```


## External Resources Needed

The database contains viral gene protein sequences and host associations but does NOT contain host counterpart gene sequences. External databases are needed for comparative/evolutionary analyses:

**What's IN the database:**
- Viral gene protein sequences (1,432,147 sequences, 100% coverage)
- Host MAG names and GTDB taxonomy paths (338 hosts)
- Host MAG genome files on disk (338 .fsa files in MAGs_dir)
- Functional annotations linking genes to PFAM/CAZy/KEGG terms
- Viral taxonomy (geNomad + demovir) for contigs
- Evidence provenance (which method linked which host)

**What must come from EXTERNAL sources:**
- Host counterpart protein sequences → NCBI Protein, UniProt
- Host genome annotations → NCBI RefSeq, IMG/M
- Protein domain architectures for comparison → InterPro, Pfam
- Phylogenetic reference trees → GTDB, NCBI Taxonomy
- Sequence similarity search → NCBI BLASTp, DIAMOND
- Multiple sequence alignment → MAFFT, MUSCLE, Clustal Omega
- Phylogenetic inference → IQ-TREE, FastTree, RAxML

**Useful API endpoints:**
- NCBI BLAST: https://blast.ncbi.nlm.nih.gov/Blast.cgi
- NCBI Protein: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
- NCBI Taxonomy: efetch with db=taxonomy
- UniProt: https://rest.uniprot.org/uniprotkb/search
- GTDB: https://data.gtdb.ecogenomic.org/
