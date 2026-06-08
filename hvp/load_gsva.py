#!/usr/bin/env python3
# load_gsva.py
import argparse
import io
import sys
import traceback
from typing import Iterable, List, Tuple, Optional

import pandas as pd
import psycopg2

# -----------------------------
# Config
# -----------------------------
# Staging mapping for the GSVA sample metadata CSV
SAMPLE_COLS_MAP = {
    "IMG.taxon_oid": "img_taxon_oid",
    "Domain": "domain",
    "Study.Name": "study_name",
    "Genome.Name...Sample.Name": "genome_or_sample",
    "Geographic.Location": "geographic_location",
    "Isolation.Country": "isolation_country",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Sequencing.Center": "sequencing_center",
    "Is.Public": "is_public",
    "Is.Published": "is_published",
    "NCBI.Taxon.ID": "ncbi_taxon_id",
    "NCBI.Project.ID": "ncbi_bioproject",
    "IMG.Genome.ID": "img_genome_id",
    "Habitat": "habitat",
    "GOLD.Ecosystem": "gold_ecosystem",
    "GOLD.Ecosystem.Category": "gold_category",
    "GOLD.Ecosystem.Type": "gold_type",
    "GOLD.Ecosystem.Subtype": "gold_subtype",
    "GOLD.Specific.Ecosystem": "gold_specific",
    "Altitude.In.Meters": "altitude_m",
    "Elevation.In.Meters": "elevation_m",
}

CONTIG_COLS = ["contig_id", "contig_length", "n_genes", "genomad_taxonomy"]
GENE_COLS = ["gene_id", "contig_id", "start_coordinate", "end_coordinate", "strand"]

CHUNK_ROWS = 100_000
PROT_BATCH = 200_000
NUC_BATCH = 2_000_000

# -----------------------------
# SQL blocks
# -----------------------------
SQL_HELPERS = r"""
-- === Helper lookup-id functions (SELECT-first to avoid sequence burn) ===
CREATE OR REPLACE FUNCTION get_sample_type_id(_name text) RETURNS smallint AS $$
DECLARE _id smallint;
BEGIN
  SELECT sample_type_id INTO _id FROM sample_type WHERE name = _name;
  IF _id IS NOT NULL THEN RETURN _id; END IF;

  INSERT INTO sample_type(name) VALUES(_name)
  RETURNING sample_type_id INTO _id;
  RETURN _id;

EXCEPTION WHEN unique_violation THEN
  SELECT sample_type_id INTO _id FROM sample_type WHERE name = _name;
  RETURN _id;
END$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_organism_type_id(_name text) RETURNS smallint AS $$
DECLARE _id smallint;
BEGIN
  SELECT organism_type_id INTO _id FROM organism_type WHERE name = _name;
  IF _id IS NOT NULL THEN RETURN _id; END IF;

  INSERT INTO organism_type(name) VALUES(_name)
  RETURNING organism_type_id INTO _id;
  RETURN _id;

EXCEPTION WHEN unique_violation THEN
  SELECT organism_type_id INTO _id FROM organism_type WHERE name = _name;
  RETURN _id;
END$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_environment_type_id(_name text) RETURNS smallint AS $$
DECLARE _id smallint;
BEGIN
  SELECT environment_type_id INTO _id FROM environment_type WHERE name = _name;
  IF _id IS NOT NULL THEN RETURN _id; END IF;

  INSERT INTO environment_type(name) VALUES(_name)
  RETURNING environment_type_id INTO _id;
  RETURN _id;

EXCEPTION WHEN unique_violation THEN
  SELECT environment_type_id INTO _id FROM environment_type WHERE name = _name;
  RETURN _id;
END$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_environment_scheme_id(
  _name   text,
  _desc   text DEFAULT NULL,
  _is_hier bool DEFAULT true
) RETURNS smallint AS $$
DECLARE _id smallint;
BEGIN
  SELECT scheme_id INTO _id FROM environment_scheme WHERE name = _name;
  IF _id IS NOT NULL THEN
    -- best-effort update of optional fields if caller provided them
    UPDATE environment_scheme
    SET description     = COALESCE(environment_scheme.description, _desc),
        is_hierarchical = COALESCE(_is_hier, environment_scheme.is_hierarchical)
    WHERE scheme_id = _id;
    RETURN _id;
  END IF;

  INSERT INTO environment_scheme(name, description, is_hierarchical)
  VALUES(_name, _desc, COALESCE(_is_hier, true))
  RETURNING scheme_id INTO _id;
  RETURN _id;

EXCEPTION WHEN unique_violation THEN
  SELECT scheme_id INTO _id FROM environment_scheme WHERE name = _name;
  RETURN _id;
END$$ LANGUAGE plpgsql;

-- === Generic cleaner to LTREE (kept for non-taxonomy uses like environment paths) ===
CREATE OR REPLACE FUNCTION to_ltree_path(_tx text) RETURNS ltree AS $$
BEGIN
  IF _tx IS NULL OR btrim(_tx) = '' THEN
    RETURN NULL;
  END IF;
  RETURN REPLACE(
           REGEXP_REPLACE(_tx, '[^A-Za-z0-9;]+', '_', 'g'),
           ';', '.'
         )::ltree;
EXCEPTION WHEN others THEN
  RETURN NULL;
END$$ LANGUAGE plpgsql;

-- === Shared canonical taxonomy normalizer to LTREE ===
CREATE OR REPLACE FUNCTION normalize_taxonomy_ltree(
  _tx text,
  _strip_rank_prefix boolean DEFAULT true
) RETURNS ltree AS $$
DECLARE
  parts text[];
  p text;
  cleaned text;
  out_parts text[] := ARRAY[]::text[];
BEGIN
  IF _tx IS NULL OR btrim(_tx) = '' THEN
    RETURN NULL;
  END IF;

  -- split on semicolons with optional surrounding whitespace
  parts := regexp_split_to_array(_tx, '\s*;\s*');

  FOREACH p IN ARRAY parts LOOP
    p := btrim(p);

    -- skip blanks / NA-like values
    IF p IS NULL OR p = '' OR lower(p) IN ('na', 'n/a', 'none', 'null') THEN
      CONTINUE;
    END IF;

    -- optionally strip GTDB/checkM rank prefixes like d__, p__, k__, etc.
    IF _strip_rank_prefix THEN
      p := regexp_replace(p, '^[A-Za-z]__', '');
    END IF;

    -- normalize common "Unclassified (...)" variants
    IF p ~* '^unclassified' THEN
      p := 'Unclassified';
    END IF;

    -- remove parenthetical notes like "(UID203)"
    p := regexp_replace(p, '\s*\(.*?\)\s*', '', 'g');

    -- sanitize to ltree label
    cleaned := regexp_replace(p, '[^A-Za-z0-9]+', '_', 'g');
    cleaned := regexp_replace(cleaned, '_+', '_', 'g');
    cleaned := btrim(cleaned, '_');

    IF cleaned IS NULL OR cleaned = '' THEN
      CONTINUE;
    END IF;

    -- ltree labels should not start with a digit
    IF cleaned ~ '^[0-9]' THEN
      cleaned := 'x' || cleaned;
    END IF;

    out_parts := array_append(out_parts, cleaned);
  END LOOP;

  IF array_length(out_parts, 1) IS NULL THEN
    RETURN NULL;
  END IF;

  RETURN array_to_string(out_parts, '.')::ltree;

EXCEPTION WHEN others THEN
  RETURN NULL;
END
$$ LANGUAGE plpgsql IMMUTABLE;

-- === Extract IMG taxon OID (numeric key) from contig_id variants ===
CREATE OR REPLACE FUNCTION extract_img_oid(_id text) RETURNS text AS $$
DECLARE m text;
BEGIN
  IF _id IS NULL THEN RETURN NULL; END IF;
  SELECT COALESCE(
    (regexp_match(_id, '^(?:img:)?([0-9]{6,})'))[1],
    (regexp_match(_id, 'taxon_oid=([0-9]{6,})'))[1]
  ) INTO m;
  RETURN m;
END$$ LANGUAGE plpgsql IMMUTABLE;
"""

SQL_STAGING = r"""
DROP TABLE IF EXISTS st_gsva_samples         CASCADE;
DROP TABLE IF EXISTS st_gsva_contigs         CASCADE;
DROP TABLE IF EXISTS st_gsva_genes           CASCADE;
DROP TABLE IF EXISTS st_gsva_proteins        CASCADE;
DROP TABLE IF EXISTS st_gsva_amg             CASCADE;
DROP TABLE IF EXISTS st_gsva_contig_fasta    CASCADE;
DROP TABLE IF EXISTS st_gsva_crispr_hosts    CASCADE;
DROP TABLE IF EXISTS st_gsva_functions       CASCADE;
DROP TABLE IF EXISTS st_gsva_votu            CASCADE;
DROP TABLE IF EXISTS st_gsva_clusters        CASCADE;

CREATE TABLE st_gsva_samples (
  img_taxon_oid        text,
  domain               text,
  study_name           text,
  genome_or_sample     text,
  geographic_location  text,
  isolation_country    text,
  latitude             text,
  longitude            text,
  sequencing_center    text,
  is_public            text,
  is_published         text,
  ncbi_taxon_id        text,
  ncbi_bioproject      text,
  img_genome_id        text,
  habitat              text,
  gold_ecosystem       text,
  gold_category        text,
  gold_type            text,
  gold_subtype         text,
  gold_specific        text,
  altitude_m           text,
  elevation_m          text
);

CREATE TABLE st_gsva_contigs (
  contig_id            text,
  contig_length        integer,
  n_genes              integer,
  genomad_taxonomy     text
);

CREATE TABLE st_gsva_genes (
  gene_id              text,
  contig_id            text,
  start_coordinate     integer,
  end_coordinate       integer,
  strand               integer
);

-- Staging for proteins (protein header id and uppercase AA sequence)
CREATE TABLE st_gsva_proteins (
  gene_id   text,
  aa_seq    text
);

-- Staging for AMG/CAT annotations
CREATE TABLE st_gsva_amg (
  amg_cat     text,
  contig_name text,
  gene_name   text,
  gene_index  integer,
  upstream    text,
  downstream  text
);

-- Staging for contig nucleotide sequences (FASTA)
CREATE TABLE st_gsva_contig_fasta (
  contig_id   text,
  nt_seq      text
);

-- Staging for CRISPR host predictions
-- Accepts flexible inputs; minimally contig_id + host_species OR host_taxonomy
CREATE TABLE st_gsva_crispr_hosts (
  contig_id       text,
  host_species    text,
  host_taxonomy   text,
  ncbi_taxon_id   integer,
  score           real,
  details         text
);

-- Staging for generic functional annotations (beyond AMG)
CREATE TABLE st_gsva_functions (
  gene_id        text,
  function_name  text,
  ontology_id    text,
  method_name    text,
  confidence     real,
  resource_url   text
);

-- Generalized cluster staging: set, name, contig, representative flag
CREATE TABLE st_gsva_clusters (
  cluster_set_name   text,  -- e.g., 'vOTU', 'genus_cluster', 'family_cluster'
  cluster_name       text,
  contig_id          text,
  is_representative  integer
);
"""

SQL_RESOURCE = r"""
INSERT INTO resource (doi, title, url)
SELECT NULL, 'Global Soil Viromes (GSVA) imports', 'internal://GSVA'
WHERE NOT EXISTS (
  SELECT 1 FROM resource
  WHERE url = 'internal://GSVA'
     OR doi = 'internal://GSVA'
);
"""

# Locations, Samples (+environment & elevation), Studies, Metagenomes, and resource links
# - sample_type => 'Metagenome'
# - organism_type at sample stays broader ('Domain'); contig/metagenome get genomad leaf (set later)
SQL_NORMALIZE_SAMPLES_ENV_MG = r"""
DO $$
DECLARE
  _sample_type_id   smallint := get_sample_type_id('Metagenome');
  _resource_id      bigint;
  _scheme_gold_id   smallint;
BEGIN
  -- Ensure GSVA resource id
  SELECT resource_id INTO _resource_id
  FROM resource WHERE COALESCE(doi, url) = 'internal://GSVA';

  -- Ensure GOLD environment scheme
  _scheme_gold_id := get_environment_scheme_id('GOLD', 'DOE-JGI GOLD ecosystem classification', true);

  /*
    Build a normalized, de-duplicated sample set and persist to a TEMP table:
    - loc_name: COALESCE(geographic_location, isolation_country, 'Unknown')
    - lat_norm / lon_norm: swap if obviously reversed; else keep; else NULL
    - DISTINCT ON (img_taxon_oid): prefer rows with valid coords and richer GOLD fields
  */
  CREATE TEMP TABLE _s_pick ON COMMIT DROP AS
  WITH s_norm AS (
    SELECT
      btrim(img_taxon_oid)                                   AS img_taxon_oid,
      btrim(domain)                                          AS domain,
      btrim(study_name)                                      AS study_name,
      COALESCE(NULLIF(btrim(geographic_location), ''),
               NULLIF(btrim(isolation_country), ''),
               'Unknown')                                    AS loc_name,
      NULLIF(btrim(habitat), '')                             AS habitat,
      NULLIF(btrim(gold_ecosystem), '')                      AS gold_ecosystem,
      NULLIF(btrim(gold_category), '')                       AS gold_category,
      NULLIF(btrim(gold_type), '')                           AS gold_type,
      NULLIF(btrim(gold_subtype), '')                        AS gold_subtype,
      NULLIF(btrim(gold_specific), '')                       AS gold_specific,
      -- Normalize coordinates (swap if obviously reversed)
      CASE
        WHEN NULLIF(latitude,'')::double precision BETWEEN -90 AND 90
             AND (NULLIF(longitude,'')::double precision BETWEEN -180 AND 180 OR NULLIF(longitude,'') IS NULL)
             THEN NULLIF(latitude,'')::double precision
        WHEN NULLIF(longitude,'')::double precision BETWEEN -90 AND 90
             AND NULLIF(latitude,'')::double precision BETWEEN -180 AND 180
             THEN NULLIF(longitude,'')::double precision
        ELSE NULL
      END                                                    AS lat_norm,
      CASE
        WHEN NULLIF(longitude,'')::double precision BETWEEN -180 AND 180
             AND (NULLIF(latitude,'')::double precision BETWEEN -90 AND 90 OR NULLIF(latitude,'') IS NULL)
             THEN NULLIF(longitude,'')::double precision
        WHEN NULLIF(latitude,'')::double precision BETWEEN -180 AND 180
             AND NULLIF(longitude,'')::double precision BETWEEN -90 AND 90
             THEN NULLIF(latitude,'')::double precision
        ELSE NULL
      END                                                    AS lon_norm,
      COALESCE(NULLIF(elevation_m,'')::double precision,
               NULLIF(altitude_m,'')::double precision)      AS elevation_m
    FROM st_gsva_samples
    WHERE img_taxon_oid IS NOT NULL AND btrim(img_taxon_oid) <> ''
  ),
  s_pick AS (
    SELECT DISTINCT ON (img_taxon_oid)
      img_taxon_oid, domain, study_name, loc_name, habitat,
      gold_ecosystem, gold_category, gold_type, gold_subtype, gold_specific,
      lat_norm, lon_norm, elevation_m
    FROM s_norm
    ORDER BY
      img_taxon_oid,
      (lat_norm IS NULL), (lon_norm IS NULL),
      (gold_ecosystem IS NULL),
      (gold_category IS NULL),
      (gold_type IS NULL),
      (gold_subtype IS NULL),
      (gold_specific IS NULL)
  )
  SELECT * FROM s_pick;

  -- Locations (idempotent)
  INSERT INTO location(name, latitude, longitude)
  SELECT DISTINCT sp.loc_name, sp.lat_norm, sp.lon_norm
  FROM _s_pick sp
  WHERE NOT EXISTS (
    SELECT 1 FROM location l
    WHERE l.name = sp.loc_name
      AND l.latitude  IS NOT DISTINCT FROM sp.lat_norm
      AND l.longitude IS NOT DISTINCT FROM sp.lon_norm
  );

  -- Upsert studies from Study.Name
  INSERT INTO study(name)
  SELECT DISTINCT btrim(study_name)
  FROM st_gsva_samples
  WHERE study_name IS NOT NULL AND btrim(study_name) <> ''
  ON CONFLICT (name) DO NOTHING;

  -- Link resource ↔ studies
  INSERT INTO resource_study(resource_id, study_id)
  SELECT DISTINCT _resource_id, st.study_id
  FROM study st
  JOIN (
    SELECT DISTINCT btrim(study_name) AS sn
    FROM st_gsva_samples
    WHERE study_name IS NOT NULL AND btrim(study_name) <> ''
  ) q ON q.sn = st.name
  ON CONFLICT DO NOTHING;

  -- Insert/Upsert samples (from deduped set)
  INSERT INTO sample (
    sample_type_id,
    organism_type_id,
    anatomical_site_id,
    location_id,
    external_id,
    collection_date,
    elevation_m,
    environment_scheme_id,
    environment_path,
    environment_text,
    environment_details
  )
  SELECT
    _sample_type_id,
    get_organism_type_id(COALESCE(NULLIF(btrim(sp.domain), ''), 'Unknown')),
    NULL::smallint,
    l.location_id,
    sp.img_taxon_oid,
    NULL::date,
    sp.elevation_m,
    _scheme_gold_id,
    to_ltree_path(
      array_to_string(ARRAY[
        sp.gold_ecosystem,
        sp.gold_category,
        sp.gold_type,
        sp.gold_subtype,
        sp.gold_specific
      ]::text[], ';')
    ) AS environment_path,
    NULL::text AS environment_text,
    sp.habitat AS environment_details
  FROM _s_pick sp
  JOIN location l
    ON l.name = sp.loc_name
   AND l.latitude  IS NOT DISTINCT FROM sp.lat_norm
   AND l.longitude IS NOT DISTINCT FROM sp.lon_norm
  ON CONFLICT (external_id) DO UPDATE SET
    sample_type_id        = EXCLUDED.sample_type_id,
    organism_type_id      = EXCLUDED.organism_type_id,
    location_id           = EXCLUDED.location_id,
    elevation_m           = COALESCE(EXCLUDED.elevation_m, sample.elevation_m),
    environment_scheme_id = EXCLUDED.environment_scheme_id,
    environment_path      = EXCLUDED.environment_path,
    environment_text      = EXCLUDED.environment_text,
    environment_details   = COALESCE(EXCLUDED.environment_details, sample.environment_details);

  -- Link samples ↔ studies
  INSERT INTO sample_study(sample_id, study_id)
  SELECT DISTINCT smp.sample_id, st.study_id
  FROM st_gsva_samples s
  JOIN sample smp ON smp.external_id = s.img_taxon_oid
  JOIN study  st  ON st.name = btrim(s.study_name)
  WHERE s.study_name IS NOT NULL AND btrim(s.study_name) <> ''
  ON CONFLICT DO NOTHING;

  -- Metagenomes
  INSERT INTO metagenome (sample_id, name, external_link)
  SELECT
    smp.sample_id,
    sp.img_taxon_oid,
    CONCAT('img:', sp.img_taxon_oid)
  FROM _s_pick sp
  JOIN sample smp ON smp.external_id = sp.img_taxon_oid
  WHERE NOT EXISTS (
    SELECT 1 FROM metagenome m WHERE m.name = sp.img_taxon_oid
  );

  -- resource ↔ metagenome
  INSERT INTO resource_metagenome(resource_id, metagenome_id)
  SELECT DISTINCT _resource_id, m.metagenome_id
  FROM metagenome m
  JOIN sample smp ON smp.sample_id = m.sample_id
  JOIN _s_pick sp  ON sp.img_taxon_oid = smp.external_id
  ON CONFLICT DO NOTHING;

  -- resource ↔ sample
  INSERT INTO resource_sample(resource_id, sample_id)
  SELECT DISTINCT _resource_id, smp.sample_id
  FROM sample smp
  JOIN _s_pick sp ON sp.img_taxon_oid = smp.external_id
  ON CONFLICT DO NOTHING;
END$$;
"""

# -----------------------------------------------------------------------
# Build virus_taxon hierarchy and contig taxon assignments using the same
# canonical taxonomy normalizer for both tree construction and leaf lookup.
# -----------------------------------------------------------------------
SQL_NORMALIZE_TAXON_CONTIG = r"""
DO $$
DECLARE
  _rec     record;
  _parts   text[];
  _rank    text;
  _path    ltree;
  _parent  bigint;
  _cur_id  bigint;
  _i       int;
BEGIN
  FOR _rec IN
    SELECT DISTINCT normalize_taxonomy_ltree(genomad_taxonomy) AS tax_path
    FROM st_gsva_contigs
    WHERE genomad_taxonomy IS NOT NULL
      AND btrim(genomad_taxonomy) <> ''
      AND normalize_taxonomy_ltree(genomad_taxonomy) IS NOT NULL
  LOOP
    _parts  := string_to_array(_rec.tax_path::text, '.');
    _parent := NULL;
    _path   := NULL;

    FOR _i IN 1 .. array_length(_parts, 1) LOOP
      _rank := _parts[_i];
      IF _rank IS NULL OR _rank = '' THEN CONTINUE; END IF;

      IF _i = 1 THEN
        _path := _rank::ltree;
      ELSE
        _path := _path || _rank::ltree;
      END IF;

      SELECT taxon_id INTO _cur_id
      FROM virus_taxon
      WHERE parent_id IS NOT DISTINCT FROM _parent
        AND name = _rank;

      IF _cur_id IS NULL THEN
        INSERT INTO virus_taxon (name, rank, parent_id, path)
        VALUES (_rank, NULL, _parent, _path)
        ON CONFLICT (parent_id, name) DO UPDATE
          SET path = EXCLUDED.path
        RETURNING taxon_id INTO _cur_id;
      ELSE
        UPDATE virus_taxon
        SET path = _path
        WHERE taxon_id = _cur_id
          AND (path IS DISTINCT FROM _path);
      END IF;

      _parent := _cur_id;
    END LOOP;
  END LOOP;
END$$;

WITH m AS (
  SELECT metagenome_id, name AS img_taxon_oid
  FROM metagenome
),
taxed AS (
  SELECT
    c.contig_id,
    c.contig_length,
    c.n_genes,
    extract_img_oid(c.contig_id) AS img_taxon_oid,
    normalize_taxonomy_ltree(c.genomad_taxonomy) AS tax_path
  FROM st_gsva_contigs c
),
rows AS (
  SELECT
    t.contig_id,
    t.contig_length,
    t.n_genes,
    t.img_taxon_oid,
    t.tax_path,
    CASE
      WHEN t.tax_path IS NOT NULL THEN
        split_part(
          t.tax_path::text,
          '.',
          array_length(string_to_array(t.tax_path::text, '.'), 1)
        )
      ELSE NULL
    END AS leaf_name
  FROM taxed t
)
INSERT INTO viral_contig (metagenome_id, name, taxon_id, contig_length, n_genes, organism_type_id)
SELECT
  m.metagenome_id,
  r.contig_id,
  vt.taxon_id,
  r.contig_length,
  r.n_genes,
  CASE
    WHEN r.leaf_name IS NOT NULL AND btrim(r.leaf_name) <> ''
    THEN get_organism_type_id(r.leaf_name)
    ELSE NULL
  END
FROM rows r
JOIN m ON m.img_taxon_oid = r.img_taxon_oid
LEFT JOIN virus_taxon vt ON vt.path = r.tax_path
ON CONFLICT (metagenome_id, name) DO UPDATE
SET taxon_id         = COALESCE(EXCLUDED.taxon_id, viral_contig.taxon_id),
    contig_length    = COALESCE(EXCLUDED.contig_length, viral_contig.contig_length),
    n_genes          = COALESCE(EXCLUDED.n_genes, viral_contig.n_genes),
    organism_type_id = COALESCE(EXCLUDED.organism_type_id, viral_contig.organism_type_id);

-- Derive dominant organism_type per metagenome (mode over contigs)
WITH counts AS (
  SELECT metagenome_id, organism_type_id, COUNT(*) AS n
  FROM viral_contig
  WHERE organism_type_id IS NOT NULL
  GROUP BY metagenome_id, organism_type_id
),
winners AS (
  SELECT DISTINCT ON (metagenome_id)
         metagenome_id, organism_type_id
  FROM counts
  ORDER BY metagenome_id, n DESC, organism_type_id
)
UPDATE metagenome m
SET organism_type_id = w.organism_type_id
FROM winners w
WHERE w.metagenome_id = m.metagenome_id
  AND (m.organism_type_id IS DISTINCT FROM w.organism_type_id);
"""

SQL_NORMALIZE_AVG_GENE = r"""
WITH rows AS (
  SELECT g.gene_id, g.contig_id, g.start_coordinate, g.end_coordinate, g.strand
  FROM st_gsva_genes g
)
INSERT INTO avg_gene (contig_id, name, start_nt, end_nt, strand, length_nt)
SELECT
  vc.contig_id,
  r.gene_id,
  r.start_coordinate,
  r.end_coordinate,
  CASE WHEN r.strand IN (-1,1) THEN r.strand ELSE NULL END,
  CASE WHEN r.start_coordinate IS NOT NULL AND r.end_coordinate IS NOT NULL
       THEN GREATEST(0, r.end_coordinate - r.start_coordinate + 1)
       ELSE NULL END
FROM rows r
JOIN viral_contig vc ON vc.name = r.contig_id
WHERE NOT EXISTS (
  SELECT 1 FROM avg_gene ag
  WHERE ag.contig_id = vc.contig_id AND ag.name = r.gene_id
);
"""

# Store protein sequences into avg_sequence (generic store)
SQL_NORMALIZE_PROTEINS = r"""
WITH s AS (
  SELECT gene_id, UPPER(REGEXP_REPLACE(aa_seq, '[^A-Za-z\*\-]', '', 'g')) AS aa_seq
  FROM st_gsva_proteins
),
m AS (
  SELECT ag.avg_id, s.aa_seq
  FROM s
  JOIN avg_gene ag ON ag.name = s.gene_id
)
INSERT INTO avg_sequence (avg_id, sequence, length, seq_type)
SELECT avg_id, aa_seq, LENGTH(aa_seq), 'Protein'::sequence_kind
FROM m
ON CONFLICT (avg_id) DO UPDATE
SET sequence = EXCLUDED.sequence,
    length   = EXCLUDED.length,
    seq_type = 'Protein'::sequence_kind;
"""

# Contig nucleotide sequences to viral_contig_sequence
SQL_NORMALIZE_CONTIG_FASTA = r"""
WITH s AS (
  SELECT contig_id, UPPER(REGEXP_REPLACE(nt_seq, '[^ACGTRYSWKMBDHVNU\.\-]', '', 'g')) AS nt_seq
  FROM st_gsva_contig_fasta
),
m AS (
  SELECT vc.contig_id, s.nt_seq
  FROM s
  JOIN viral_contig vc ON vc.name = s.contig_id
)
INSERT INTO viral_contig_sequence (contig_id, sequence, length, seq_type)
SELECT contig_id, nt_seq, LENGTH(nt_seq), 'Nucleotide'::sequence_kind
FROM m
ON CONFLICT (contig_id) DO UPDATE
SET sequence = EXCLUDED.sequence,
    length   = EXCLUDED.length,
    seq_type = 'Nucleotide'::sequence_kind;
"""

# AMG/CAT annotations
SQL_NORMALIZE_AMG = r"""
DO $$
DECLARE
  _method_id   bigint;
  _res_id_gsva bigint;
BEGIN
  -- Ensure AMG-CAT evidence method
  SELECT method_id INTO _method_id FROM evidence_method WHERE method_name = 'AMG-CAT';
  IF _method_id IS NULL THEN
    INSERT INTO evidence_method(method_name, evidence_type, version, parameters)
    VALUES ('AMG-CAT', 'Computational'::evidence_kind, NULL, NULL::jsonb)
    RETURNING method_id INTO _method_id;
  END IF;

  -- Ensure method scopes
  INSERT INTO method_scope(method_id, applies_to) VALUES
    (_method_id, 'avg'), (_method_id, 'avg_function')
  ON CONFLICT DO NOTHING;

  -- Use single GSVA resource for all annotations
  SELECT resource_id INTO _res_id_gsva FROM resource WHERE url = 'internal://GSVA';

  -- Normalize AMG staging into a temp table
  CREATE TEMP TABLE _amg_norm ON COMMIT DROP AS
  SELECT
    btrim(gene_name)              AS gene_name,
    btrim(contig_name)            AS contig_name,
    gene_index::int               AS gene_index,
    lower(btrim(amg_cat))         AS amg_cat_norm,
    NULLIF(btrim(upstream),   '') AS upstream,
    NULLIF(btrim(downstream), '') AS downstream
  FROM st_gsva_amg
  WHERE amg_cat IS NOT NULL AND btrim(amg_cat) <> '';

  CREATE INDEX ON _amg_norm(gene_name);
  CREATE INDEX ON _amg_norm(contig_name, gene_index);

  -- Function terms (AMG_cat0, AMG_cat1, AMG_cat2, ...)
  INSERT INTO function_term(name, ontology_id)
  SELECT DISTINCT 'AMG_' || amg_cat_norm, 'AMG_CAT'
  FROM _amg_norm
  ON CONFLICT (name) DO NOTHING;

  -- Materialize matches to avg_gene by (1) exact GeneName OR (2) ContigName_GeneIndex
  CREATE TEMP TABLE _amg_matched ON COMMIT DROP AS
  SELECT DISTINCT
    COALESCE(ag1.avg_id, ag2.avg_id) AS avg_id,
    n.amg_cat_norm,
    n.contig_name,
    n.gene_index,
    n.upstream,
    n.downstream
  FROM _amg_norm n
  LEFT JOIN avg_gene ag1
    ON ag1.name = n.gene_name
  LEFT JOIN avg_gene ag2
    ON ag2.name = n.contig_name || '_' || n.gene_index::text
  WHERE COALESCE(ag1.avg_id, ag2.avg_id) IS NOT NULL;

  CREATE INDEX ON _amg_matched(avg_id);
  CREATE INDEX ON _amg_matched(amg_cat_norm);

  -- avg_function links (AVG ↔ AMG_catX)
  INSERT INTO avg_function (avg_id, function_id, resource_id, method_id, confidence_score)
  SELECT m.avg_id, ft.function_id, _res_id_gsva, _method_id, NULL::real
  FROM _amg_matched m
  JOIN function_term ft ON ft.name = 'AMG_' || m.amg_cat_norm
  ON CONFLICT (avg_id, function_id, resource_id, method_id) DO NOTHING;

  -- One avg_evidence row per AVG: aggregate all matched AMG hits into a single JSON payload
  CREATE TEMP TABLE _amg_evidence_agg ON COMMIT DROP AS
  SELECT
    avg_id,
    json_build_object(
      'source', 'AMG-CAT',
      'n_hits', COUNT(*),
      'amg_categories', array_agg(DISTINCT amg_cat_norm ORDER BY amg_cat_norm),
      'hits',
        json_agg(
          json_build_object(
            'amg_cat',    amg_cat_norm,
            'contig',     contig_name,
            'gene_index', gene_index,
            'upstream',   upstream,
            'downstream', downstream
          )
          ORDER BY amg_cat_norm, contig_name, gene_index
        )
    )::text AS details
  FROM _amg_matched
  GROUP BY avg_id;

  INSERT INTO avg_evidence (avg_id, method_id, resource_id, details, score)
  SELECT
    e.avg_id,
    _method_id,
    _res_id_gsva,
    e.details,
    NULL::real
  FROM _amg_evidence_agg e
  ON CONFLICT (avg_id, method_id, resource_id) DO UPDATE
  SET details = EXCLUDED.details;

END$$;
"""

# Generic functional annotations (PFAM/CAZy/KEGG)
SQL_NORMALIZE_FUNCTIONS = r"""
DO $$
DECLARE
  _res_id_gsva bigint;
BEGIN
  -- Single GSVA resource for all function annotations
  SELECT resource_id INTO _res_id_gsva FROM resource WHERE url = 'internal://GSVA';

  -- Ensure evidence methods
  INSERT INTO evidence_method(method_name, evidence_type, version, parameters)
  SELECT DISTINCT f.method_name, 'Computational'::evidence_kind, NULL, NULL::jsonb
  FROM st_gsva_functions f
  WHERE f.method_name IS NOT NULL AND btrim(f.method_name) <> ''
  ON CONFLICT (method_name) DO NOTHING;

  -- Method scope: avg + avg_function
  INSERT INTO method_scope(method_id, applies_to)
  SELECT em.method_id, 'avg'
  FROM evidence_method em
  JOIN (SELECT DISTINCT method_name FROM st_gsva_functions WHERE method_name IS NOT NULL AND btrim(method_name) <> '') q
    ON q.method_name = em.method_name
  ON CONFLICT DO NOTHING;

  INSERT INTO method_scope(method_id, applies_to)
  SELECT em.method_id, 'avg_function'
  FROM evidence_method em
  JOIN (SELECT DISTINCT method_name FROM st_gsva_functions WHERE method_name IS NOT NULL AND btrim(method_name) <> '') q
    ON q.method_name = em.method_name
  ON CONFLICT DO NOTHING;

  -- Function terms
  INSERT INTO function_term(name, ontology_id)
  SELECT DISTINCT btrim(function_name), NULLIF(btrim(ontology_id), '')
  FROM st_gsva_functions
  WHERE function_name IS NOT NULL AND btrim(function_name) <> ''
  ON CONFLICT (name) DO UPDATE SET
    ontology_id = COALESCE(EXCLUDED.ontology_id, function_term.ontology_id);

  -- Link AVG ↔ function (always use GSVA resource)
  INSERT INTO avg_function (avg_id, function_id, resource_id, method_id, confidence_score)
  SELECT ag.avg_id,
         ft.function_id,
         _res_id_gsva,
         em.method_id,
         f.confidence
  FROM st_gsva_functions f
  JOIN avg_gene ag ON ag.name = f.gene_id
  JOIN function_term ft ON ft.name = btrim(f.function_name)
  LEFT JOIN evidence_method em ON em.method_name = NULLIF(btrim(f.method_name), '')
  ON CONFLICT (avg_id, function_id, resource_id, method_id) DO NOTHING;
END$$;
"""

# CRISPR-Spacer predicted hosts (contig level)
# - De-duplicates hosts by (species, ncbi_taxon_id, taxonomy)
# - Supports either species strings or GTDB-style taxonomy paths in staging
SQL_NORMALIZE_CRISPR_HOSTS = r"""
DO $$
DECLARE
  _method_id  bigint;
  _res_id     bigint;
BEGIN
  -- Ensure CRISPR-Spacer method and scope (contig-level)
  SELECT method_id INTO _method_id FROM evidence_method WHERE method_name = 'CRISPR-Spacer';
  IF _method_id IS NULL THEN
    INSERT INTO evidence_method(method_name, evidence_type, version, parameters)
    VALUES ('CRISPR-Spacer', 'Experimental'::evidence_kind, NULL, NULL::jsonb)
    RETURNING method_id INTO _method_id;
  END IF;
  INSERT INTO method_scope(method_id, applies_to) VALUES (_method_id, 'contig')
  ON CONFLICT DO NOTHING;

  -- Use single GSVA resource
  SELECT resource_id INTO _res_id
  FROM resource WHERE url = 'internal://GSVA';

  -- Normalize and de-duplicate incoming host rows
  CREATE TEMP TABLE _hosts_norm ON COMMIT DROP AS
  SELECT DISTINCT
    NULLIF(btrim(h.host_species),'') AS species,
    normalize_taxonomy_ltree(NULLIF(btrim(h.host_taxonomy),'')) AS taxonomy,
    h.ncbi_taxon_id,
    h.contig_id,
    h.score,
    h.details
  FROM st_gsva_crispr_hosts h
  WHERE (NULLIF(btrim(h.host_species),'') IS NOT NULL OR NULLIF(btrim(h.host_taxonomy),'') IS NOT NULL);

  CREATE INDEX ON _hosts_norm(species, ncbi_taxon_id);
  CREATE INDEX ON _hosts_norm(taxonomy);

  -- Prefer explicit species; else use taxonomy leaf
  CREATE TEMP TABLE _hosts_final ON COMMIT DROP AS
  SELECT
    COALESCE(
      NULLIF(hn.species, ''),
      NULLIF(
        subpath(hn.taxonomy, nlevel(hn.taxonomy)-1, 1)::text,
        ''
      )
    ) AS species_clean,
    hn.taxonomy,
    hn.ncbi_taxon_id,
    hn.contig_id,
    hn.score,
    hn.details
  FROM _hosts_norm hn;

  CREATE INDEX ON _hosts_final(species_clean, ncbi_taxon_id);
  CREATE INDEX ON _hosts_final(taxonomy);

  -- Insert new hosts using non-null species_clean
  INSERT INTO host(species, taxonomy, ncbi_taxon_id, strain)
  SELECT hf.species_clean, hf.taxonomy, hf.ncbi_taxon_id, NULL::text
  FROM _hosts_final hf
  WHERE hf.species_clean IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM host ho
      WHERE ho.species       IS NOT DISTINCT FROM hf.species_clean
        AND ho.ncbi_taxon_id IS NOT DISTINCT FROM hf.ncbi_taxon_id
        AND ho.taxonomy      IS NOT DISTINCT FROM hf.taxonomy
    );

  -- Map to stable host_id
  CREATE TEMP TABLE _hosts_map ON COMMIT DROP AS
  SELECT
    hf.contig_id,
    (SELECT MIN(ho.host_id) FROM host ho
      WHERE ho.species       IS NOT DISTINCT FROM hf.species_clean
        AND ho.ncbi_taxon_id IS NOT DISTINCT FROM hf.ncbi_taxon_id
        AND ho.taxonomy      IS NOT DISTINCT FROM hf.taxonomy) AS host_id,
    hf.score,
    hf.details
  FROM _hosts_final hf;

  CREATE INDEX ON _hosts_map(host_id);

  -- Link contig ↔ host
  INSERT INTO viral_contig_host (contig_id, host_id, method_id, resource_id, score, details)
  SELECT
    vc.contig_id,
    hm.host_id,
    _method_id,
    _res_id,
    hm.score,
    COALESCE(NULLIF(hm.details, ''), json_build_object('source','CRISPR-Spacer')::text)
  FROM _hosts_map hm
  JOIN viral_contig vc ON vc.name = hm.contig_id
  WHERE hm.host_id IS NOT NULL
  ON CONFLICT (contig_id, host_id, resource_id, method_id) DO UPDATE
  SET score   = COALESCE(EXCLUDED.score, viral_contig_host.score),
      details = COALESCE(EXCLUDED.details, viral_contig_host.details);
END$$;
"""

# -----------------------------------------------------------------------
# Removed legacy st_gsva_votu references. Only the generalized
# st_gsva_clusters table is used now.
# -----------------------------------------------------------------------
SQL_NORMALIZE_CLUSTERS = r"""
DO $$
BEGIN
  -- Ensure cluster_set rows exist for any seen set names
  INSERT INTO contig_cluster_set(name, method, version, parameters)
  SELECT DISTINCT btrim(cluster_set_name), NULL::text, NULL::text, NULL::jsonb
  FROM st_gsva_clusters
  WHERE cluster_set_name IS NOT NULL AND btrim(cluster_set_name) <> ''
  ON CONFLICT (name, method, version) DO NOTHING;

  -- Insert clusters from generalized staging
  INSERT INTO contig_cluster(cluster_set_id, name)
  SELECT DISTINCT ccs.cluster_set_id, btrim(s.cluster_name)
  FROM st_gsva_clusters s
  JOIN contig_cluster_set ccs ON ccs.name = btrim(s.cluster_set_name)
  WHERE s.cluster_name IS NOT NULL AND btrim(s.cluster_name) <> ''
  ON CONFLICT (cluster_set_id, name) DO NOTHING;

  -- Members from generalized staging
  INSERT INTO contig_cluster_member (contig_id, cluster_id)
  SELECT vc.contig_id, cc.cluster_id
  FROM st_gsva_clusters s
  JOIN viral_contig vc ON vc.name = s.contig_id
  JOIN contig_cluster_set ccs ON ccs.name = btrim(s.cluster_set_name)
  JOIN contig_cluster cc ON cc.cluster_set_id = ccs.cluster_set_id
                        AND cc.name = btrim(s.cluster_name)
  ON CONFLICT DO NOTHING;

  -- Representatives from generalized staging
  WITH reps AS (
    SELECT DISTINCT btrim(cluster_set_name) AS set_name,
           btrim(cluster_name) AS cname,
           btrim(contig_id)    AS contig_name
    FROM st_gsva_clusters
    WHERE COALESCE(is_representative,0) <> 0
  )
  UPDATE contig_cluster cc
  SET representative_contig_id = vc.contig_id
  FROM reps r
  JOIN contig_cluster_set ccs ON ccs.name = r.set_name
  JOIN viral_contig vc ON vc.name = r.contig_name
  WHERE cc.cluster_set_id = ccs.cluster_set_id
    AND cc.name = r.cname
    AND (cc.representative_contig_id IS DISTINCT FROM vc.contig_id);
END$$;
"""

SQL_SANITY = r"""
SELECT 'samples' AS what, count(*) FROM sample
UNION ALL SELECT 'metagenomes', count(*) FROM metagenome
UNION ALL SELECT 'contigs', count(*) FROM viral_contig
UNION ALL SELECT 'contig_seq', count(*) FROM viral_contig_sequence
UNION ALL SELECT 'avg_gene', count(*) FROM avg_gene
UNION ALL SELECT 'avg_sequence', count(*) FROM avg_sequence
UNION ALL SELECT 'avg_function', count(*) FROM avg_function
UNION ALL SELECT 'avg_evidence', count(*) FROM avg_evidence
UNION ALL SELECT 'virus_taxon', count(*) FROM virus_taxon
UNION ALL SELECT 'contig_cluster_members', count(*) FROM contig_cluster_member
UNION ALL SELECT 'contig_hosts', count(*) FROM viral_contig_host;
"""

SQL_MISMATCH_REPORT = r"""
WITH
  s  AS (SELECT DISTINCT gene_id   FROM st_gsva_proteins),
  a  AS (SELECT DISTINCT name      FROM avg_gene),
  s2 AS (SELECT DISTINCT gene_name FROM st_gsva_amg),
  a2 AS (SELECT DISTINCT name      FROM avg_gene),
  cs  AS (SELECT DISTINCT contig_id FROM st_gsva_contig_fasta),
  vc1 AS (SELECT DISTINCT name      FROM viral_contig)
SELECT 'proteins_without_matching_gene' AS issue, COUNT(*) AS n
FROM s LEFT JOIN a ON a.name = s.gene_id
WHERE a.name IS NULL

UNION ALL
SELECT 'genes_without_protein', COUNT(*)
FROM avg_gene ag
LEFT JOIN avg_sequence seq ON seq.avg_id = ag.avg_id AND seq.seq_type = 'Protein'
WHERE seq.avg_id IS NULL

UNION ALL
SELECT 'contigs_without_genes', COUNT(*)
FROM viral_contig vc
LEFT JOIN avg_gene ag ON ag.contig_id = vc.contig_id
WHERE ag.avg_id IS NULL

UNION ALL
SELECT 'contig_fasta_without_matching_contig', COUNT(*)
FROM cs LEFT JOIN vc1 ON vc1.name = cs.contig_id
WHERE vc1.name IS NULL

UNION ALL
SELECT 'metagenomes_without_contigs', COUNT(*)
FROM metagenome m
LEFT JOIN viral_contig vc ON vc.metagenome_id = m.metagenome_id
WHERE vc.contig_id IS NULL

UNION ALL
SELECT 'amg_rows_without_matching_gene', COUNT(*)
FROM s2 LEFT JOIN a2 ON a2.name = s2.gene_name
WHERE a2.name IS NULL;
"""

# -----------------------------
# Utilities
# -----------------------------
def log(msg: str):
    print(msg, file=sys.stderr, flush=True)


def copy_dataframe(conn, df: pd.DataFrame, table: str, columns: List[str]):
    if df.empty:
        return
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    buf.seek(0)
    with conn.cursor() as cur:
        cur.copy_expert(
            f"COPY {table} ({', '.join(columns)}) FROM STDIN WITH (FORMAT csv)",
            buf,
        )
    conn.commit()


def load_samples_staging(conn, path: str):
    want = list(SAMPLE_COLS_MAP.keys())
    out_cols = list(SAMPLE_COLS_MAP.values())
    log(f"Loading samples staging from {path}")
    nrows = 0
    for chunk in pd.read_csv(
        path,
        dtype=str,
        chunksize=CHUNK_ROWS,
        encoding_errors="ignore",
    ):
        for c in want:
            if c not in chunk.columns:
                chunk[c] = ""
        sub = chunk[want].rename(columns=SAMPLE_COLS_MAP)
        copy_dataframe(conn, sub, "st_gsva_samples", out_cols)
        nrows += len(sub)
        log(f"  +{len(sub)} rows (total {nrows})")
    log(f"Samples staging loaded: {nrows} rows")


def _parse_host_prediction_to_species_and_taxonomy(val: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Accepts a predicted host string and returns (species, taxonomy_string).

    Rules:
      - If the string contains '__' (GTDB/checkM-style ranks), ALWAYS treat the whole
        string as a taxonomy string — even if there are no semicolons.
      - Only set 'species' when a terminal 's__' rank exists; otherwise leave it None.
      - If no '__' is present, treat the whole string as a plain species name.
    """
    if not isinstance(val, str):
        return None, None
    s = val.strip().strip(";,")

    if not s:
        return None, None

    # GTDB/checkM-style ranks
    if "__" in s:
        taxonomy = s  # DB will normalize with normalize_taxonomy_ltree()
        species = None
        parts = [p.strip() for p in s.split(";") if p.strip()]
        for p in reversed(parts):
            if p.startswith("s__"):
                sp = p[3:].strip()
                species = sp or None
                break
        return species, taxonomy

    # Otherwise: plain species string (no taxonomy)
    return s, None


def load_contigs_staging(conn, path: str):
    log(f"Loading contigs staging from {path}")
    nrows = 0
    host_rows = 0
    cluster_rows = 0
    for chunk in pd.read_csv(
        path,
        sep="\t",
        dtype=str,
        chunksize=CHUNK_ROWS,
        encoding_errors="ignore",
    ):
        # Ensure core columns
        for c in CONTIG_COLS:
            if c not in chunk.columns:
                chunk[c] = ""

        # Stash core contig metadata
        sub = chunk[CONTIG_COLS].copy()
        for c in ["contig_length", "n_genes"]:
            sub[c] = pd.to_numeric(sub[c], errors="coerce").astype("Int64")
        sub["contig_length"] = sub["contig_length"].astype(object).where(
            sub["contig_length"].notna(), None
        )
        sub["n_genes"] = sub["n_genes"].astype(object).where(
            sub["n_genes"].notna(), None
        )
        copy_dataframe(conn, sub, "st_gsva_contigs", CONTIG_COLS)
        nrows += len(sub)

        # Case-insensitive accessors for optional columns
        cols_lower = {str(c).strip().lower(): c for c in chunk.columns}
        host_col = cols_lower.get("predicted_host")
        votu_col = cols_lower.get("votu")
        genus_col = cols_lower.get("genus_cluster")
        family_col = cols_lower.get("family_cluster")

        # Predicted hosts -> st_gsva_crispr_hosts
        if host_col:
            host_df = chunk[["contig_id", host_col]].copy()
            host_df.rename(columns={host_col: "predicted_host_raw"}, inplace=True)
            host_df["predicted_host_raw"] = host_df["predicted_host_raw"].fillna("").astype(str)

            # Split multiple predictions on pipe or comma — NOT semicolons
            host_df = host_df.assign(
                predicted_host_raw=host_df["predicted_host_raw"].str.split(r"[|,]")
            ).explode("predicted_host_raw")
            host_df["predicted_host_raw"] = host_df["predicted_host_raw"].astype(str).str.strip()

            # Parse species + taxonomy
            species_list: List[Optional[str]] = []
            tax_list: List[Optional[str]] = []
            for v in host_df["predicted_host_raw"].tolist():
                sp, tx = _parse_host_prediction_to_species_and_taxonomy(v)
                species_list.append(sp)
                tax_list.append(tx)

            host_df["host_species"] = species_list
            host_df["host_taxonomy"] = tax_list
            host_df = host_df[
                (host_df["contig_id"].notna()) &
                ((host_df["host_species"].notna()) | (host_df["host_taxonomy"].notna()))
            ]

            if not host_df.empty:
                host_df["ncbi_taxon_id"] = pd.NA
                host_df["score"] = None
                host_df["details"] = None
                copy_dataframe(
                    conn,
                    host_df[["contig_id", "host_species", "host_taxonomy", "ncbi_taxon_id", "score", "details"]],
                    "st_gsva_crispr_hosts",
                    ["contig_id", "host_species", "host_taxonomy", "ncbi_taxon_id", "score", "details"],
                )
                host_rows += len(host_df)

        # Clusters -> st_gsva_clusters ONLY
        cluster_frames: List[pd.DataFrame] = []

        def add_cluster(colname: Optional[str], set_name: str):
            if not colname:
                return
            df = chunk[["contig_id", colname]].copy()
            df.rename(columns={colname: "cluster_name"}, inplace=True)
            df["cluster_name"] = df["cluster_name"].fillna("").astype(str)
            df["cluster_name"] = df["cluster_name"].str.replace("|", ";", regex=False)
            df = df.assign(cluster_name=df["cluster_name"].str.split(r"[;,]")).explode("cluster_name")
            df["cluster_name"] = df["cluster_name"].astype(str).str.strip()
            df = df[(df["cluster_name"] != "") & df["contig_id"].notna()]
            if not df.empty:
                df["cluster_set_name"] = set_name
                df["is_representative"] = 0
                cluster_frames.append(df[["cluster_set_name", "cluster_name", "contig_id", "is_representative"]])

        add_cluster(votu_col, "vOTU")
        add_cluster(genus_col, "genus_cluster")
        add_cluster(family_col, "family_cluster")

        if cluster_frames:
            out = pd.concat(cluster_frames, ignore_index=True)
            copy_dataframe(
                conn,
                out,
                "st_gsva_clusters",
                ["cluster_set_name", "cluster_name", "contig_id", "is_representative"],
            )
            cluster_rows += len(out)

        log(f"  +{len(sub)} contigs (total {nrows}); +hosts {host_rows}; +clusters {cluster_rows}")
    log(f"Contigs staging loaded: {nrows} rows (hosts {host_rows}, clusters {cluster_rows})")


def load_genes_staging(conn, path: str):
    log(f"Loading genes staging from {path}")
    nrows = 0
    for chunk in pd.read_csv(
        path,
        sep="\t",
        dtype=str,
        chunksize=CHUNK_ROWS,
        encoding_errors="ignore",
    ):
        for c in GENE_COLS:
            if c not in chunk.columns:
                chunk[c] = ""
        sub = chunk[GENE_COLS].copy()
        for c in ["start_coordinate", "end_coordinate", "strand"]:
            sub[c] = pd.to_numeric(sub[c], errors="coerce").astype("Int64")
            sub[c] = sub[c].astype(object).where(sub[c].notna(), None)
        copy_dataframe(conn, sub, "st_gsva_genes", GENE_COLS)
        nrows += len(sub)
        log(f"  +{len(sub)} rows (total {nrows})")
    log(f"Genes staging loaded: {nrows} rows")


def load_functions_from_genes(conn, path: str):
    """
    Extract PFAM / CAZy / KEGG KO from the genes metadata into st_gsva_functions.
    Uses columns: pfam, cazyme, kegg_ortholog (case-insensitive).
    """
    log(f"Extracting PFAM/CAZy/KEGG from {path} into function staging")
    total = 0
    for chunk in pd.read_csv(path, sep="\t", dtype=str, chunksize=CHUNK_ROWS, encoding_errors="ignore"):
        if "gene_id" not in chunk.columns:
            continue
        df = chunk.copy()
        df["gene_id"] = df["gene_id"].fillna("").astype(str)

        cols = {str(c).strip().lower(): c for c in df.columns}
        pfam_col = cols.get("pfam")
        cazy_col = cols.get("cazyme")
        ko_col   = cols.get("kegg_ortholog")

        outs = []

        def explode_col(colname: Optional[str], ontology: str, method: str, resource: str):
            if not colname or colname not in df.columns:
                return None
            sub = df[["gene_id", colname]].copy()
            sub[colname] = sub[colname].fillna("").astype(str)
            # normalize delimiters and explode
            sub[colname] = sub[colname].str.replace("|", ";", regex=False)
            sub = sub.assign(function_name=sub[colname].str.split(r"[;,]")).explode("function_name")
            sub["function_name"] = sub["function_name"].astype(str).str.strip()
            sub = sub[(sub["gene_id"] != "") & (sub["function_name"] != "")]
            if sub.empty:
                return None
            sub["ontology_id"] = ontology
            sub["method_name"] = method
            sub["confidence"] = None
            sub["resource_url"] = resource
            return sub[["gene_id", "function_name", "ontology_id", "method_name", "confidence", "resource_url"]]

        pf = explode_col(pfam_col, "PFAM", "PFAM HMM", "https://pfam.xfam.org")
        cz = explode_col(cazy_col, "CAZy", "dbCAN", "http://bcb.unl.edu/dbCAN2/")
        ko = explode_col(ko_col,   "KEGG_KO", "KEGG", "https://www.kegg.jp/kegg/ko.html")

        for fr in (pf, cz, ko):
            if fr is not None and not fr.empty:
                outs.append(fr)

        if outs:
            out = pd.concat(outs, ignore_index=True)
            copy_dataframe(
                conn,
                out,
                "st_gsva_functions",
                ["gene_id", "function_name", "ontology_id", "method_name", "confidence", "resource_url"],
            )
            total += len(out)
            log(f"  +{len(out)} function rows (total {total})")
    log(f"Function rows from genes loaded: {total}")


def fasta_iter(path: str) -> Iterable[Tuple[str, str]]:
    """
    Stream a FASTA file yielding (header_token, sequence).
    header_token = first whitespace-delimited token after '>'
    """
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        header = None
        seq_chunks: List[str] = []
        for line in fh:
            if line.startswith(">"):
                if header is not None:
                    seq = (
                        "".join(seq_chunks)
                        .replace(" ", "")
                        .replace("\r", "")
                        .replace("\n", "")
                        .upper()
                    )
                    yield (header, seq)
                header = line[1:].strip().split()[0]
                seq_chunks = []
            else:
                seq_chunks.append(line.strip())
        if header is not None:
            seq = (
                "".join(seq_chunks)
                .replace(" ", "")
                .replace("\r", "")
                .replace("\n", "")
                .upper()
            )
            yield (header, seq)


def load_proteins_staging(conn, fasta_paths: List[str]):
    if not fasta_paths:
        return
    log(f"Loading protein staging from {len(fasta_paths)} FASTA file(s)")
    buf_gene: List[str] = []
    buf_seq: List[str] = []
    total = 0
    chars = 0

    def flush():
        nonlocal buf_gene, buf_seq, total, chars
        if not buf_gene:
            return
        df = pd.DataFrame({"gene_id": buf_gene, "aa_seq": buf_seq})
        copy_dataframe(conn, df, "st_gsva_proteins", ["gene_id", "aa_seq"])
        total += len(buf_gene)
        log(f"  +{len(buf_gene)} proteins (total {total})")
        buf_gene, buf_seq = [], []
        chars = 0

    for p in fasta_paths:
        log(f"  parsing {p}")
        for header, seq in fasta_iter(p):
            if not header:
                continue
            buf_gene.append(header)
            buf_seq.append(seq)
            chars += len(seq)
            if chars >= PROT_BATCH:
                flush()
    flush()
    log(
        f"Proteins staging loaded: {total} sequences from {len(fasta_paths)} file(s)"
    )


def load_contig_fasta_staging(conn, fasta_paths: List[str]):
    """
    Load contig nucleotide FASTA but ONLY for contig IDs present in st_gsva_contigs
    (avoid extra unrelated viral sequences).
    """
    if not fasta_paths:
        return

    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT contig_id FROM st_gsva_contigs "
            "WHERE contig_id IS NOT NULL AND btrim(contig_id) <> ''"
        )
        allowed = {row[0] for row in cur.fetchall()}

    log(f"Loading contig FASTA staging from {len(fasta_paths)} FASTA file(s)")
    log(f"  (Filtering to {len(allowed)} contig IDs present in metadata)")

    buf_contig: List[str] = []
    buf_seq: List[str] = []
    total = 0
    chars = 0

    def flush():
        nonlocal buf_contig, buf_seq, total, chars
        if not buf_contig:
            return
        df = pd.DataFrame({"contig_id": buf_contig, "nt_seq": buf_seq})
        copy_dataframe(conn, df, "st_gsva_contig_fasta", ["contig_id", "nt_seq"])
        total += len(buf_contig)
        log(f"  +{len(buf_contig)} contigs (total {total})")
        buf_contig, buf_seq = [], []
        chars = 0

    for p in fasta_paths:
        log(f"  parsing {p}")
        for header, seq in fasta_iter(p):
            if not header:
                continue
            if header not in allowed:
                continue
            buf_contig.append(header)
            buf_seq.append(seq)
            chars += len(seq)
            if chars >= NUC_BATCH:
                flush()
    flush()
    log(f"Contig FASTA staging loaded: {total} sequences from {len(fasta_paths)} file(s)")


def load_amg_staging(conn, path: str):
    """
    Parse AMG_withCAT_new.txt.

    Actual file structure:
      Header row: 5 tab fields
        AMG_Cat, ContigName, GeneName, GeneIndex, UpstreamDownstream
      Data rows: 6 tab fields
        AMG_Cat, ContigName, GeneName, GeneIndex, Upstream, Downstream

    So we skip the header row and provide the real 6-column schema explicitly.
    """
    log(f"Loading AMG/CAT staging from {path}")
    nrows = 0

    read_cols = ["AMG_Cat", "ContigName", "GeneName", "GeneIndex", "Upstream", "Downstream"]
    rename_map = {
        "AMG_Cat": "amg_cat",
        "ContigName": "contig_name",
        "GeneName": "gene_name",
        "GeneIndex": "gene_index",
        "Upstream": "upstream",
        "Downstream": "downstream",
    }

    first_chunk = True

    for chunk in pd.read_csv(
        path,
        sep="\t",
        names=read_cols,
        header=None,
        skiprows=1,
        dtype=str,
        chunksize=CHUNK_ROWS,
        encoding_errors="ignore",
        engine="python",
        keep_default_na=False,
        na_filter=False,
    ):
        df = chunk.rename(columns=rename_map).copy()

        # normalize empties
        for c in ["amg_cat", "contig_name", "gene_name", "upstream", "downstream"]:
            df[c] = df[c].replace("", None)

        df["gene_index"] = pd.to_numeric(df["gene_index"], errors="coerce").astype("Int64")
        df["gene_index"] = df["gene_index"].astype(object).where(df["gene_index"].notna(), None)

        # fail fast if parsing is obviously wrong
        cat_like = df["amg_cat"].fillna("").astype(str).str.fullmatch(r"cat\d+").mean()
        gene_like = df["gene_name"].fillna("").astype(str).str.contains(r"_\d+$").mean()
        gidx_like = df["gene_index"].notna().mean()

        if cat_like < 0.95 or gene_like < 0.95 or gidx_like < 0.95:
            raise ValueError(
                f"AMG parse sanity check failed: "
                f"cat_like={cat_like:.3f}, gene_like={gene_like:.3f}, gene_index_nonnull={gidx_like:.3f}"
            )

        if first_chunk:
            vc = (
                df["amg_cat"]
                .fillna("NULL")
                .astype(str)
                .value_counts(dropna=False)
                .head(10)
                .to_dict()
            )
            log(f"  AMG parse sanity: cat_like={cat_like:.3f}, gene_like={gene_like:.3f}, gene_index_nonnull={gidx_like:.3f}")
            log(f"  Top AMG categories (first chunk): {vc}")
            first_chunk = False

        copy_dataframe(
            conn,
            df,
            "st_gsva_amg",
            ["amg_cat", "contig_name", "gene_name", "gene_index", "upstream", "downstream"],
        )
        nrows += len(df)
        log(f"  +{len(df)} rows (total {nrows})")

    log(f"AMG/CAT staging loaded: {nrows} rows")


# -----------------------------
# Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser(
        description=(
            "Load GSVA soil virus data into the schema (idempotent). "
            "Adds environment (GOLD), elevation, studies; contigs+taxonomy with canonical taxonomy normalization; "
            "genes+proteins; contig nucleotide sequences; CRISPR host predictions (from contig metadata); "
            "AMG/CAT; and generic function annotations (PFAM/CAZy/KEGG from gene metadata); "
            "plus contig clusters (vOTU/genus/family) from contig metadata."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument(
        "--dsn",
        required=True,
        help='psycopg2 DSN, e.g., "dbname=hvp user=me host=/tmp gssencmode=disable"',
    )
    ap.add_argument("--samples", required=True, help="Path to GSVA_sample_metadata_5.csv")
    ap.add_argument(
        "--contigs", required=True, help="Path to GSVA_soil_viruses_genome_metadata_2.tsv"
    )
    ap.add_argument(
        "--genes", required=True, help="Path to GSVA_soil_viruses_gene_metadata_4.tsv"
    )
    ap.add_argument(
        "--proteins",
        nargs="*",
        default=[],
        help="One or more .faa files with protein sequences (headers = gene IDs)",
    )
    ap.add_argument(
        "--contig-fasta",
        nargs="*",
        default=[],
        help="One or more .fna files with contig nucleotide sequences (headers = contig IDs)",
    )
    ap.add_argument("--amg", default="", help="Path to AMG_withCAT_new.txt (AMG annotations)")
    ap.add_argument(
        "--keep-staging", action="store_true", help="Keep staging tables (default: drop at end)"
    )
    args = ap.parse_args()

    conn = psycopg2.connect(args.dsn)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            log("Installing helper SQL (upserts, environment scheme, taxonomy normalizer, extract_img_oid)...")
            cur.execute(SQL_HELPERS)
            conn.commit()

            log("Creating staging tables...")
            cur.execute(SQL_STAGING)
            conn.commit()

            log("Ensuring GSVA resource row exists...")
            cur.execute(SQL_RESOURCE)
            conn.commit()

        # Load staging from provided files
        load_samples_staging(conn, args.samples)
        load_contigs_staging(conn, args.contigs)               # also fills hosts + clusters
        load_genes_staging(conn, args.genes)
        load_functions_from_genes(conn, args.genes)            # fills st_gsva_functions from pfam/cazyme/KO

        if args.proteins:
            load_proteins_staging(conn, args.proteins)
        if args.contig_fasta:
            load_contig_fasta_staging(conn, args.contig_fasta)
        if args.amg:
            load_amg_staging(conn, args.amg)

        # Normalize to main tables
        with conn.cursor() as cur:
            log("Normalizing: locations, studies, samples (+environment & elevation), metagenomes, resource links...")
            cur.execute(SQL_NORMALIZE_SAMPLES_ENV_MG)
            conn.commit()

            log("Normalizing: taxonomy hierarchy + contigs (shared canonical normalizer; leaf -> organism_type)...")
            cur.execute(SQL_NORMALIZE_TAXON_CONTIG)
            conn.commit()

            log("Normalizing: AVG genes...")
            cur.execute(SQL_NORMALIZE_AVG_GENE)
            conn.commit()

            if args.proteins:
                log("Normalizing: protein sequences -> avg_sequence (Protein)...")
                cur.execute(SQL_NORMALIZE_PROTEINS)
                conn.commit()

            if args.contig_fasta:
                log("Normalizing: contig nucleotide sequences -> viral_contig_sequence...")
                cur.execute(SQL_NORMALIZE_CONTIG_FASTA)
                conn.commit()

            if args.amg:
                log("Normalizing: AMG/CAT -> avg_function + avg_evidence (one evidence row per AVG)...")
                cur.execute(SQL_NORMALIZE_AMG)
                conn.commit()

            log("Normalizing: generic functions (PFAM/CAZy/KEGG) -> avg_function...")
            cur.execute(SQL_NORMALIZE_FUNCTIONS)
            conn.commit()

            log("Normalizing: CRISPR host predictions (contig-level) -> viral_contig_host...")
            cur.execute(SQL_NORMALIZE_CRISPR_HOSTS)
            conn.commit()

            log("Normalizing: all contig clusters (vOTU/genus/family) + representatives...")
            cur.execute(SQL_NORMALIZE_CLUSTERS)
            conn.commit()

            log("Sanity counts:")
            cur.execute(SQL_SANITY)
            for what, cnt in cur.fetchall():
                log(f"  {what:24s} {cnt}")

            log("Mismatch report:")
            cur.execute(SQL_MISMATCH_REPORT)
            for issue, n in cur.fetchall():
                log(f"  {issue:34s} {n}")

        if not args.keep_staging:
            with conn.cursor() as cur:
                log("Dropping staging tables...")
                cur.execute(
                    """
                    DROP TABLE IF EXISTS st_gsva_clusters;
                    DROP TABLE IF EXISTS st_gsva_votu;
                    DROP TABLE IF EXISTS st_gsva_functions;
                    DROP TABLE IF EXISTS st_gsva_crispr_hosts;
                    DROP TABLE IF EXISTS st_gsva_contig_fasta;
                    DROP TABLE IF EXISTS st_gsva_amg;
                    DROP TABLE IF EXISTS st_gsva_proteins;
                    DROP TABLE IF EXISTS st_gsva_genes;
                    DROP TABLE IF EXISTS st_gsva_contigs;
                    DROP TABLE IF EXISTS st_gsva_samples;
                    """
                )
                conn.commit()

        log("✅ Load complete.")
    except Exception as e:
        conn.rollback()
        log("❌ Error during load. Transaction rolled back.")
        log(str(e))
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()