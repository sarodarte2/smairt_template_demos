#!/usr/bin/env python3
# load_hic_wu.py

import argparse
import glob
import io
import json
import os
import re
import sys
import traceback
from typing import Dict, List, Optional, Tuple

import pandas as pd
import psycopg2
from psycopg2.extensions import adapt

CHUNK_ROWS = 200_000
MG_NAME = "Wu Soil Hi-C"


# =========================================================
# SQL helpers / compatibility
# =========================================================
SQL_HELPERS = r"""
CREATE OR REPLACE FUNCTION get_sample_type_id(_name text) RETURNS smallint AS $$
DECLARE _id smallint;
BEGIN
  SELECT sample_type_id INTO _id FROM sample_type WHERE name=_name;
  IF _id IS NOT NULL THEN RETURN _id; END IF;
  INSERT INTO sample_type(name) VALUES(_name) RETURNING sample_type_id INTO _id;
  RETURN _id;
EXCEPTION WHEN unique_violation THEN
  SELECT sample_type_id INTO _id FROM sample_type WHERE name=_name; RETURN _id;
END$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_organism_type_id(_name text) RETURNS smallint AS $$
DECLARE _id smallint;
BEGIN
  SELECT organism_type_id INTO _id FROM organism_type WHERE name=_name;
  IF _id IS NOT NULL THEN RETURN _id; END IF;
  INSERT INTO organism_type(name) VALUES(_name) RETURNING organism_type_id INTO _id;
  RETURN _id;
EXCEPTION WHEN unique_violation THEN
  SELECT organism_type_id INTO _id FROM organism_type WHERE name=_name; RETURN _id;
END$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION ensure_evidence_method(_name text, _etype evidence_kind)
RETURNS bigint AS $$
DECLARE _id bigint;
BEGIN
  SELECT method_id INTO _id FROM evidence_method WHERE method_name=_name;
  IF _id IS NOT NULL THEN RETURN _id; END IF;
  INSERT INTO evidence_method(method_name, evidence_type, version, parameters)
  VALUES (_name, _etype, NULL, NULL) RETURNING method_id INTO _id;
  RETURN _id;
EXCEPTION WHEN unique_violation THEN
  SELECT method_id INTO _id FROM evidence_method WHERE method_name=_name; RETURN _id;
END$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION ensure_method_scope(_method_id bigint, _applies text)
RETURNS void AS $$
BEGIN
  INSERT INTO method_scope(method_id, applies_to) VALUES (_method_id, _applies)
  ON CONFLICT DO NOTHING;
END$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION contig_name_token(_name text)
RETURNS text AS $$
DECLARE m text[];
BEGIN
  IF _name IS NULL THEN
    RETURN NULL;
  END IF;

  m := regexp_match(lower(_name), '(k[0-9]+_[0-9]+|node_[0-9]+|scaffold_[0-9]+)');
  IF m IS NULL THEN
    RETURN lower(_name);
  END IF;
  RETURN m[1];
END$$ LANGUAGE plpgsql IMMUTABLE;
"""

SQL_SCHEMA_COMPAT = r"""
ALTER TABLE host ADD COLUMN IF NOT EXISTS mag_file_path text;
"""


# =========================================================
# Staging tables
# =========================================================
SQL_STAGING = r"""
DROP TABLE IF EXISTS st_wu_contigs          CASCADE;
DROP TABLE IF EXISTS st_wu_links            CASCADE;
DROP TABLE IF EXISTS st_wu_mags             CASCADE;
DROP TABLE IF EXISTS st_wu_viral_taxonomy   CASCADE;

DROP TABLE IF EXISTS st_wu_s2_votu          CASCADE;
DROP TABLE IF EXISTS st_wu_s4_unfilt        CASCADE;
DROP TABLE IF EXISTS st_wu_s5_filtered      CASCADE;
DROP TABLE IF EXISTS st_wu_s6_magtax        CASCADE;
DROP TABLE IF EXISTS st_wu_s7_crispr        CASCADE;

DROP TABLE IF EXISTS st_wu_contig_sample    CASCADE;
DROP TABLE IF EXISTS st_wu_links_legacy     CASCADE;

CREATE TABLE st_wu_contigs (
  name         text,
  contig_token text,
  seq          text,
  length       integer
);

CREATE TABLE st_wu_contig_sample (
  contig_name  text,
  contig_token text,
  sample_ext   text,
  src          text,
  prio         smallint
);

CREATE TABLE st_wu_links (
  sample_ext         text,
  viral_contig_name  text,
  contig_token       text,
  cluster_name       text,
  preferred_score    double precision,
  row_json           text
);

CREATE TABLE st_wu_mags (
  alias         text,
  mag_file_path text
);

CREATE TABLE st_wu_viral_taxonomy (
  contig_name   text,
  contig_token  text,
  taxonomy      text
);

CREATE TABLE st_wu_s2_votu (
  contig_id          text,
  contig_token       text,
  length             integer,
  votu               text,
  is_representative  integer,
  qc_json            text
);

CREATE TABLE st_wu_s4_unfilt (
  sample_ext         text,
  viral_contig_name  text,
  contig_token       text,
  host_alias         text,
  score              double precision,
  row_json           text
);

CREATE TABLE st_wu_s5_filtered (
  sample_ext         text,
  viral_contig_name  text,
  contig_token       text,
  host_alias         text,
  host_taxonomy      text,
  score              double precision,
  row_json           text
);

CREATE TABLE st_wu_s6_magtax (
  alias     text,
  taxonomy  text
);

CREATE TABLE st_wu_s7_crispr (
  sample_ext         text,
  viral_contig_name  text,
  contig_token       text,
  host_alias         text,
  score              double precision,
  row_json           text
);
"""


# =========================================================
# Core SQL
# =========================================================
SQL_INTERNAL_RESOURCE = r"""
INSERT INTO resource (doi, title, url)
SELECT NULL, 'Wu et al. Hi-C soil resource', 'internal://HiC_Wu'
WHERE NOT EXISTS (
  SELECT 1 FROM resource WHERE url='internal://HiC_Wu' OR doi='internal://HiC_Wu'
);
"""

SQL_ENSURE_STUDY_RESOURCE = r"""
DO $$
DECLARE
  _study text := %(study_name)s;
  _doi   text := %(doi)s;
BEGIN
  IF _doi IS NOT NULL THEN
    INSERT INTO resource(doi, title, url)
    SELECT _doi, 'Wu et al. Hi-C soil data package', NULL
    WHERE NOT EXISTS (SELECT 1 FROM resource WHERE doi=_doi);
  END IF;

  INSERT INTO resource(doi, title, url)
  SELECT NULL, 'Wu et al. Hi-C soil resource', 'internal://HiC_Wu'
  WHERE NOT EXISTS (SELECT 1 FROM resource WHERE url='internal://HiC_Wu');

  IF _study IS NOT NULL THEN
    INSERT INTO study(name) VALUES(_study)
    ON CONFLICT (name) DO NOTHING;
  END IF;
END$$;
"""

SQL_LINK_SAMPLES_TO_STUDY = r"""
DO $$
DECLARE
  _study_id bigint;
BEGIN
  SELECT study_id INTO _study_id
  FROM study
  WHERE name = %(study_name)s
  LIMIT 1;

  IF _study_id IS NULL THEN
    RAISE NOTICE '[sample_study] study not found: %', %(study_name)s;
    RETURN;
  END IF;

  INSERT INTO sample_study (sample_id, study_id)
  SELECT s.sample_id, _study_id
  FROM sample s
  WHERE s.external_id ~ '^SM[0-9]+$'
  ON CONFLICT DO NOTHING;

  INSERT INTO sample_study (sample_id, study_id)
  SELECT s.sample_id, _study_id
  FROM sample s
  WHERE s.external_id = 'Wu_HiC_Soil'
  ON CONFLICT DO NOTHING;

  INSERT INTO resource_study (resource_id, study_id)
  SELECT r.resource_id, _study_id
  FROM resource r
  WHERE r.url = 'internal://HiC_Wu'
     OR r.doi = %(doi)s
  ON CONFLICT DO NOTHING;
END$$;
"""

SQL_WU_METAGENOME = r"""
DO $$
DECLARE
  _st_metagenome  smallint := get_sample_type_id('Metagenome');
  _ot_microbiome  smallint := get_organism_type_id('Microbiome');
  _sid            bigint;
  _mgid           bigint;
  _locid          bigint;
  _gold_path_txt  text    := 'terrestrial.soil.grassland.arid_grassland.arid_grassland_soils';
  _env_details    text    := 'grassland soil';
  _elev           integer := 117;
BEGIN
  SELECT location_id INTO _locid
  FROM location
  WHERE name = 'Prosser, WA, USA'
  ORDER BY location_id
  LIMIT 1;

  SELECT sample_id INTO _sid
  FROM sample
  WHERE external_id = 'Wu_HiC_Soil'
  LIMIT 1;

  IF _sid IS NULL THEN
    INSERT INTO sample(
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
    VALUES (
      _st_metagenome,
      _ot_microbiome,
      NULL,
      _locid,
      'Wu_HiC_Soil',
      NULL,
      _elev,
      NULL,
      NULLIF(btrim(_gold_path_txt),'')::ltree,
      NULL,
      _env_details
    )
    RETURNING sample_id INTO _sid;
  ELSE
    UPDATE sample
       SET sample_type_id        = _st_metagenome,
           organism_type_id      = _ot_microbiome,
           location_id           = COALESCE(_locid, location_id),
           elevation_m           = COALESCE(_elev, elevation_m),
           environment_scheme_id = NULL,
           environment_path      = NULLIF(btrim(_gold_path_txt),'')::ltree,
           environment_text      = NULL,
           environment_details   = _env_details
     WHERE sample_id = _sid;
  END IF;

  SELECT metagenome_id INTO _mgid
  FROM metagenome
  WHERE name = %(mg_name)s
  ORDER BY metagenome_id
  LIMIT 1;

  IF _mgid IS NULL THEN
    INSERT INTO metagenome(sample_id, name, external_link)
    VALUES (_sid, %(mg_name)s, 'internal://HiC_Wu')
    RETURNING metagenome_id INTO _mgid;
  ELSE
    UPDATE metagenome
       SET sample_id     = _sid,
           external_link = 'internal://HiC_Wu'
     WHERE metagenome_id = _mgid;
  END IF;
END$$;
"""

SQL_PER_SAMPLE_METAGENOMES = r"""
DO $$
DECLARE
  r RECORD;
  _mgid bigint;
BEGIN
  FOR r IN
    SELECT s.sample_id, s.external_id
    FROM sample s
    WHERE s.external_id ~ '^SM[0-9]+$'
  LOOP
    SELECT metagenome_id INTO _mgid
    FROM metagenome
    WHERE name = r.external_id
    ORDER BY metagenome_id
    LIMIT 1;

    IF _mgid IS NULL THEN
      INSERT INTO metagenome(sample_id, name, external_link)
      VALUES (r.sample_id, r.external_id, 'internal://HiC_Wu')
      RETURNING metagenome_id INTO _mgid;
    ELSE
      UPDATE metagenome
         SET sample_id = r.sample_id,
             external_link = COALESCE(external_link, 'internal://HiC_Wu')
       WHERE metagenome_id = _mgid;
    END IF;
  END LOOP;
END$$;
"""

SQL_NORMALIZE_CONTIGS = r"""
DO $$
DECLARE
  _phage_ot smallint := get_organism_type_id('Bacteriophage');
  _fallback_mg bigint;
  _ins_map integer := 0;
  _ins_fb  integer := 0;
BEGIN
  SELECT metagenome_id INTO _fallback_mg
  FROM metagenome
  WHERE name = %(mg_name)s
  ORDER BY metagenome_id
  LIMIT 1;

  WITH map_all AS (
    SELECT DISTINCT ON (contig_name, sample_ext)
           contig_name, sample_ext
    FROM st_wu_contig_sample
    WHERE sample_ext ~ '^SM[0-9]+$'
    ORDER BY contig_name, sample_ext, prio
  )
  INSERT INTO viral_contig (metagenome_id, name, organism_type_id, contig_length)
  SELECT
    mg.metagenome_id,
    c.name,
    _phage_ot,
    c.length
  FROM st_wu_contigs c
  JOIN map_all m ON m.contig_name = c.name
  JOIN metagenome mg ON mg.name = m.sample_ext
  ON CONFLICT (metagenome_id, name) DO UPDATE
    SET contig_length    = COALESCE(EXCLUDED.contig_length, viral_contig.contig_length),
        organism_type_id = COALESCE(EXCLUDED.organism_type_id, viral_contig.organism_type_id);

  GET DIAGNOSTICS _ins_map = ROW_COUNT;

  INSERT INTO viral_contig (metagenome_id, name, organism_type_id, contig_length)
  SELECT
    _fallback_mg,
    c.name,
    _phage_ot,
    c.length
  FROM st_wu_contigs c
  WHERE NOT EXISTS (
    SELECT 1
    FROM st_wu_contig_sample m
    WHERE m.contig_name = c.name
      AND m.sample_ext ~ '^SM[0-9]+$'
  )
  ON CONFLICT (metagenome_id, name) DO UPDATE
    SET contig_length    = COALESCE(EXCLUDED.contig_length, viral_contig.contig_length),
        organism_type_id = COALESCE(EXCLUDED.organism_type_id, viral_contig.organism_type_id);

  GET DIAGNOSTICS _ins_fb = ROW_COUNT;

  RAISE NOTICE '[contigs] inserted_by_map=% fallback=%', _ins_map, _ins_fb;

  WITH map_all AS (
    SELECT DISTINCT ON (contig_name, sample_ext)
           contig_name, sample_ext
    FROM st_wu_contig_sample
    WHERE sample_ext ~ '^SM[0-9]+$'
    ORDER BY contig_name, sample_ext, prio
  )
  INSERT INTO viral_contig_sequence (contig_id, sequence, length, seq_type)
  SELECT
    vc.contig_id,
    c.seq,
    c.length,
    'Nucleotide'::sequence_kind
  FROM st_wu_contigs c
  LEFT JOIN map_all m ON m.contig_name = c.name
  LEFT JOIN metagenome mg ON mg.name = m.sample_ext
  JOIN viral_contig vc
    ON vc.name = c.name
   AND vc.metagenome_id = COALESCE(mg.metagenome_id, _fallback_mg)
  ON CONFLICT (contig_id) DO UPDATE
    SET sequence = EXCLUDED.sequence,
        length   = EXCLUDED.length,
        seq_type = EXCLUDED.seq_type;
END$$;
"""

SQL_NORMALIZE_WU_TAXONOMY = r"""
DO $$
DECLARE
  _rec     record;
  _parts   text[];
  _rank    text;
  _path    ltree;
  _parent  bigint;
  _cur_id  bigint;
  _clean   text;
  _i       int;
BEGIN
  FOR _rec IN
    SELECT DISTINCT taxonomy
    FROM st_wu_viral_taxonomy
    WHERE taxonomy IS NOT NULL AND btrim(taxonomy) <> ''
  LOOP
    _parts  := regexp_split_to_array(btrim(_rec.taxonomy), '\s*;\s*');
    _parent := NULL;
    _path   := NULL;

    FOR _i IN 1 .. array_length(_parts, 1) LOOP
      _rank := btrim(_parts[_i]);
      IF _rank = '' THEN
        CONTINUE;
      END IF;

      _clean := REGEXP_REPLACE(_rank, '[^A-Za-z0-9]+', '_', 'g');
      IF _path IS NULL THEN
        _path := _clean::ltree;
      ELSE
        _path := _path || _clean::ltree;
      END IF;

      SELECT taxon_id INTO _cur_id
      FROM virus_taxon
      WHERE parent_id IS NOT DISTINCT FROM _parent
        AND name = _rank;

      IF _cur_id IS NULL THEN
        INSERT INTO virus_taxon (name, rank, parent_id, path)
        VALUES (_rank, NULL, _parent, _path)
        ON CONFLICT (parent_id, name) DO UPDATE SET path = EXCLUDED.path
        RETURNING taxon_id INTO _cur_id;
      ELSE
        UPDATE virus_taxon
        SET path = _path
        WHERE taxon_id = _cur_id
          AND path IS DISTINCT FROM _path;
      END IF;

      _parent := _cur_id;
    END LOOP;
  END LOOP;
END$$;

WITH leaf_ids AS (
  SELECT DISTINCT
    wt.contig_token,
    vt.taxon_id,
    split_part(
      wt.taxonomy,
      ';',
      array_length(regexp_split_to_array(wt.taxonomy, ';'), 1)
    ) AS leaf_name
  FROM st_wu_viral_taxonomy wt
  JOIN virus_taxon vt
    ON vt.path = to_ltree_path(wt.taxonomy)
)
UPDATE viral_contig vc
SET taxon_id = li.taxon_id,
    organism_type_id = get_organism_type_id(li.leaf_name)
FROM leaf_ids li
WHERE contig_name_token(vc.name) = li.contig_token
  AND (
    vc.taxon_id IS DISTINCT FROM li.taxon_id
    OR vc.organism_type_id IS DISTINCT FROM get_organism_type_id(li.leaf_name)
  );
"""

SQL_NORMALIZE_MAGS = r"""
INSERT INTO host (species, taxonomy, mag_file_path)
SELECT DISTINCT
  s.alias,
  NULLIF(btrim(s.taxonomy),'')::ltree,
  m.mag_file_path
FROM st_wu_s6_magtax s
LEFT JOIN st_wu_mags m ON m.alias = s.alias
WHERE s.alias IS NOT NULL AND btrim(s.alias) <> ''
  AND NOT EXISTS (
    SELECT 1 FROM host h WHERE h.species IS NOT DISTINCT FROM s.alias
  );

UPDATE host h
SET taxonomy = COALESCE(h.taxonomy, NULLIF(btrim(s.taxonomy),'')::ltree),
    mag_file_path = COALESCE(h.mag_file_path, m.mag_file_path)
FROM st_wu_s6_magtax s
LEFT JOIN st_wu_mags m ON m.alias = s.alias
WHERE h.species IS NOT DISTINCT FROM s.alias;

INSERT INTO host_alias (host_id, alias)
SELECT DISTINCT h.host_id, s.alias
FROM st_wu_s6_magtax s
JOIN host h ON h.species IS NOT DISTINCT FROM s.alias
WHERE s.alias IS NOT NULL AND btrim(s.alias) <> ''
  AND NOT EXISTS (
    SELECT 1 FROM host_alias ha
    WHERE ha.host_id = h.host_id
      AND ha.alias IS NOT DISTINCT FROM s.alias
  );

INSERT INTO host (species, mag_file_path)
SELECT DISTINCT m.alias, m.mag_file_path
FROM st_wu_mags m
WHERE m.alias IS NOT NULL AND btrim(m.alias) <> ''
  AND NOT EXISTS (
    SELECT 1 FROM host h WHERE h.species IS NOT DISTINCT FROM m.alias
  );

UPDATE host h
SET mag_file_path = COALESCE(h.mag_file_path, m.mag_file_path)
FROM st_wu_mags m
WHERE h.species IS NOT DISTINCT FROM m.alias;

INSERT INTO host_alias (host_id, alias)
SELECT DISTINCT h.host_id, m.alias
FROM st_wu_mags m
JOIN host h ON h.species IS NOT DISTINCT FROM m.alias
WHERE m.alias IS NOT NULL AND btrim(m.alias) <> ''
  AND NOT EXISTS (
    SELECT 1 FROM host_alias ha
    WHERE ha.host_id = h.host_id AND ha.alias IS NOT DISTINCT FROM m.alias
  );
"""

SQL_NORMALIZE_VOTU = r"""
INSERT INTO contig_cluster_set(name, method, version, parameters)
VALUES ('vOTU', 'Dereplication', NULL, NULL)
ON CONFLICT (name, method, version) DO NOTHING;

INSERT INTO contig_cluster(cluster_set_id, name)
SELECT DISTINCT ccs.cluster_set_id, s.votu
FROM st_wu_s2_votu s
JOIN contig_cluster_set ccs ON ccs.name = 'vOTU'
WHERE s.votu IS NOT NULL AND btrim(s.votu) <> ''
ON CONFLICT (cluster_set_id, name) DO NOTHING;

INSERT INTO contig_cluster_member(contig_id, cluster_id)
SELECT DISTINCT
  vc.contig_id,
  cc.cluster_id
FROM st_wu_s2_votu s
JOIN viral_contig vc
  ON contig_name_token(vc.name) = s.contig_token
JOIN contig_cluster_set ccs
  ON ccs.name = 'vOTU'
JOIN contig_cluster cc
  ON cc.cluster_set_id = ccs.cluster_set_id
 AND cc.name = s.votu
WHERE s.votu IS NOT NULL AND btrim(s.votu) <> ''
ON CONFLICT DO NOTHING;

WITH reps AS (
  SELECT DISTINCT
    s.votu,
    s.contig_token
  FROM st_wu_s2_votu s
  WHERE COALESCE(s.is_representative, 0) = 1
    AND s.votu IS NOT NULL
    AND btrim(s.votu) <> ''
),
rep_match AS (
  SELECT
    r.votu,
    MIN(vc.contig_id) AS representative_contig_id
  FROM reps r
  JOIN viral_contig vc
    ON contig_name_token(vc.name) = r.contig_token
  GROUP BY r.votu
)
UPDATE contig_cluster cc
SET representative_contig_id = rm.representative_contig_id
FROM rep_match rm
JOIN contig_cluster_set ccs
  ON ccs.name = 'vOTU'
WHERE cc.cluster_set_id = ccs.cluster_set_id
  AND cc.name = rm.votu
  AND cc.representative_contig_id IS DISTINCT FROM rm.representative_contig_id;
"""

SQL_NORMALIZE_LINKS = r"""
DO $$
DECLARE
  _m_hic    bigint := ensure_evidence_method('Hi-C', 'Experimental');
  _m_hic_u  bigint := ensure_evidence_method('Hi-C Unfiltered', 'Experimental');
  _m_cr     bigint := ensure_evidence_method('CRISPR-Spacer', 'Experimental');
  _res_id   bigint;
BEGIN
  PERFORM ensure_method_scope(_m_hic,   'contig');
  PERFORM ensure_method_scope(_m_hic_u, 'contig');
  PERFORM ensure_method_scope(_m_cr,    'contig');

  SELECT resource_id INTO _res_id
  FROM resource
  WHERE (doi = %(doi)s AND %(doi)s IS NOT NULL)
     OR url = 'internal://HiC_Wu'
  ORDER BY (CASE WHEN doi = %(doi)s THEN 0 ELSE 1 END), resource_id
  LIMIT 1;

  INSERT INTO host (species)
  SELECT DISTINCT l.cluster_name
  FROM st_wu_links l
  WHERE l.cluster_name IS NOT NULL AND btrim(l.cluster_name) <> ''
    AND NOT EXISTS (SELECT 1 FROM host h WHERE h.species IS NOT DISTINCT FROM l.cluster_name);

  INSERT INTO host_alias (host_id, alias)
  SELECT DISTINCT h.host_id, l.cluster_name
  FROM st_wu_links l
  JOIN host h ON h.species IS NOT DISTINCT FROM l.cluster_name
  WHERE NOT EXISTS (
    SELECT 1 FROM host_alias ha
    WHERE ha.host_id = h.host_id
      AND ha.alias IS NOT DISTINCT FROM l.cluster_name
  );

  INSERT INTO host (species)
  SELECT DISTINCT f.host_alias
  FROM st_wu_s5_filtered f
  WHERE f.host_alias IS NOT NULL AND btrim(f.host_alias) <> ''
    AND NOT EXISTS (SELECT 1 FROM host h WHERE h.species IS NOT DISTINCT FROM f.host_alias);

  UPDATE host h
  SET taxonomy = COALESCE(h.taxonomy, NULLIF(btrim(f.host_taxonomy),'')::ltree)
  FROM st_wu_s5_filtered f
  WHERE h.species IS NOT DISTINCT FROM f.host_alias;

  INSERT INTO host_alias (host_id, alias)
  SELECT DISTINCT h.host_id, f.host_alias
  FROM st_wu_s5_filtered f
  JOIN host h ON h.species IS NOT DISTINCT FROM f.host_alias
  WHERE NOT EXISTS (
    SELECT 1 FROM host_alias ha
    WHERE ha.host_id = h.host_id
      AND ha.alias IS NOT DISTINCT FROM f.host_alias
  );

  INSERT INTO host (species)
  SELECT DISTINCT u.host_alias
  FROM st_wu_s4_unfilt u
  WHERE u.host_alias IS NOT NULL AND btrim(u.host_alias) <> ''
    AND NOT EXISTS (SELECT 1 FROM host h WHERE h.species IS NOT DISTINCT FROM u.host_alias);

  INSERT INTO host_alias (host_id, alias)
  SELECT DISTINCT h.host_id, u.host_alias
  FROM st_wu_s4_unfilt u
  JOIN host h ON h.species IS NOT DISTINCT FROM u.host_alias
  WHERE NOT EXISTS (
    SELECT 1 FROM host_alias ha
    WHERE ha.host_id = h.host_id
      AND ha.alias IS NOT DISTINCT FROM u.host_alias
  );

  INSERT INTO host (species)
  SELECT DISTINCT c.host_alias
  FROM st_wu_s7_crispr c
  WHERE c.host_alias IS NOT NULL AND btrim(c.host_alias) <> ''
    AND NOT EXISTS (SELECT 1 FROM host h WHERE h.species IS NOT DISTINCT FROM c.host_alias);

  INSERT INTO host_alias (host_id, alias)
  SELECT DISTINCT h.host_id, c.host_alias
  FROM st_wu_s7_crispr c
  JOIN host h ON h.species IS NOT DISTINCT FROM c.host_alias
  WHERE NOT EXISTS (
    SELECT 1 FROM host_alias ha
    WHERE ha.host_id = h.host_id
      AND ha.alias IS NOT DISTINCT FROM c.host_alias
  );

  INSERT INTO viral_contig_host (contig_id, host_id, method_id, resource_id, score, details)
  SELECT DISTINCT ON (vc.contig_id, h.host_id, _res_id, _m_hic)
    vc.contig_id,
    h.host_id,
    _m_hic,
    _res_id,
    l.preferred_score,
    l.row_json
  FROM st_wu_links l
  JOIN metagenome mg
    ON mg.name = l.sample_ext
  JOIN viral_contig vc
    ON vc.metagenome_id = mg.metagenome_id
   AND contig_name_token(vc.name) = l.contig_token
  JOIN host h
    ON h.species IS NOT DISTINCT FROM l.cluster_name
  ORDER BY vc.contig_id, h.host_id, _res_id, _m_hic, l.preferred_score DESC
  ON CONFLICT (contig_id, host_id, resource_id, method_id)
  DO UPDATE SET
    score   = GREATEST(EXCLUDED.score, viral_contig_host.score),
    details = COALESCE(EXCLUDED.details, viral_contig_host.details);

  INSERT INTO viral_contig_host (contig_id, host_id, method_id, resource_id, score, details)
  SELECT DISTINCT ON (vc.contig_id, h.host_id, _res_id, _m_hic)
    vc.contig_id,
    h.host_id,
    _m_hic,
    _res_id,
    f.score,
    f.row_json
  FROM st_wu_s5_filtered f
  JOIN metagenome mg
    ON mg.name = f.sample_ext
  JOIN viral_contig vc
    ON vc.metagenome_id = mg.metagenome_id
   AND contig_name_token(vc.name) = f.contig_token
  JOIN host h
    ON h.species IS NOT DISTINCT FROM f.host_alias
  ORDER BY vc.contig_id, h.host_id, _res_id, _m_hic, f.score DESC
  ON CONFLICT (contig_id, host_id, resource_id, method_id)
  DO UPDATE SET
    score   = GREATEST(EXCLUDED.score, viral_contig_host.score),
    details = COALESCE(EXCLUDED.details, viral_contig_host.details);

  INSERT INTO viral_contig_host (contig_id, host_id, method_id, resource_id, score, details)
  SELECT DISTINCT ON (vc.contig_id, h.host_id, _res_id, _m_hic_u)
    vc.contig_id,
    h.host_id,
    _m_hic_u,
    _res_id,
    u.score,
    u.row_json
  FROM st_wu_s4_unfilt u
  JOIN metagenome mg
    ON mg.name = u.sample_ext
  JOIN viral_contig vc
    ON vc.metagenome_id = mg.metagenome_id
   AND contig_name_token(vc.name) = u.contig_token
  JOIN host h
    ON h.species IS NOT DISTINCT FROM u.host_alias
  ORDER BY vc.contig_id, h.host_id, _res_id, _m_hic_u, u.score DESC
  ON CONFLICT (contig_id, host_id, resource_id, method_id)
  DO UPDATE SET
    score   = COALESCE(EXCLUDED.score, viral_contig_host.score),
    details = COALESCE(EXCLUDED.details, viral_contig_host.details);

  INSERT INTO viral_contig_host (contig_id, host_id, method_id, resource_id, score, details)
  SELECT DISTINCT ON (vc.contig_id, h.host_id, _res_id, _m_cr)
    vc.contig_id,
    h.host_id,
    _m_cr,
    _res_id,
    c.score,
    c.row_json
  FROM st_wu_s7_crispr c
  JOIN metagenome mg
    ON mg.name = c.sample_ext
  JOIN viral_contig vc
    ON vc.metagenome_id = mg.metagenome_id
   AND contig_name_token(vc.name) = c.contig_token
  JOIN host h
    ON h.species IS NOT DISTINCT FROM c.host_alias
  ORDER BY vc.contig_id, h.host_id, _res_id, _m_cr, c.score DESC
  ON CONFLICT (contig_id, host_id, resource_id, method_id)
  DO UPDATE SET
    score   = COALESCE(EXCLUDED.score, viral_contig_host.score),
    details = COALESCE(EXCLUDED.details, viral_contig_host.details);
END$$;
"""

SQL_SANITY = r"""
SELECT 'metagenomes' as what, count(*) FROM metagenome
UNION ALL SELECT 'contigs', count(*) FROM viral_contig
UNION ALL SELECT 'contig_seq', count(*) FROM viral_contig_sequence
UNION ALL SELECT 'hosts', count(*) FROM host
UNION ALL SELECT 'host_alias', count(*) FROM host_alias
UNION ALL SELECT 'hic_links', count(*) FROM viral_contig_host
UNION ALL SELECT 'virus_taxon', count(*) FROM virus_taxon;
"""


# =========================================================
# Python helpers
# =========================================================
def sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    return adapt(value).getquoted().decode("utf-8")


def render_sql(sql_text: str, **params: object) -> str:
    out = sql_text
    for key, value in params.items():
        out = out.replace(f"%({key})s", sql_literal(value))
    return out


def contig_token(name: object) -> Optional[str]:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return None
    s = str(name).strip().lower()
    if not s:
        return None
    m = re.search(r'(k\d+_\d+|node_\d+|scaffold_\d+)', s)
    if m:
        return m.group(1)
    return s


def normalize_headers(cols: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for c in cols:
        c0 = str(c).strip()
        c1 = re.sub(r"\(.*?\)", "", c0)
        c2 = re.sub(r"[^A-Za-z0-9_]+", "_", c1).strip("_").lower()
        out[c] = c2
    return out


def read_tabular_any(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path, dtype=str)
    try:
        return pd.read_csv(path, dtype=str)
    except Exception:
        return pd.read_csv(path, sep="\t", dtype=str, engine="python")


def find_file(base: str, stem: str) -> str:
    pats = [
        f"{stem}.*",
        f"{stem}.csv",
        f"{stem}.tsv",
        f"{stem}.xlsx",
        f"{stem}.xls",
    ]
    for p in pats:
        hits = glob.glob(os.path.join(base, p))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"Expected file not found for {stem} in {base}")


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


def ltree_sanitize(tax: Optional[str]) -> Optional[str]:
    if tax is None or (isinstance(tax, float) and pd.isna(tax)):
        return None
    s = str(tax).strip()
    if not s:
        return None
    parts = re.split(r"[;\|]+|\s{2,}", s)
    clean = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        p = re.sub(r"^[a-z]__", "", p, flags=re.IGNORECASE)
        p = p.lower()
        p = re.sub(r"[^a-z0-9_]+", "_", p)
        p = re.sub(r"_+", "_", p).strip("_")
        if not p:
            continue
        if not re.match(r"^[a-z]", p):
            p = "x" + p
        clean.append(p)
    if not clean:
        return None
    return ".".join(clean)


def normalize_bin_name(raw: object) -> Optional[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s:
        return None
    if re.fullmatch(r"PNNL_SM\d{3}_bin_\d+", s):
        return s
    m = re.match(r'^(\d{3})PNNLbin_(\d+)$', s)
    if m:
        return f"PNNL_SM{m.group(1)}_bin_{m.group(2)}"
    return s


def canonical_wu_viral_taxonomy(raw_family: object) -> Optional[str]:
    if raw_family is None or (isinstance(raw_family, float) and pd.isna(raw_family)):
        return None
    s = str(raw_family).strip()
    if not s:
        return None
    low = s.lower()

    if low in {"siphoviridae", "myoviridae", "podoviridae", "caudoviricetes"}:
        return "Viruses;Duplodnaviria;Heunggongvirae;Uroviricota;Caudoviricetes"

    if low in {"unassigned", "unclassified", "na", "n/a", "none"}:
        return None

    return None


def find_first_matching_column(df: pd.DataFrame, *patterns: str) -> Optional[str]:
    for c in df.columns:
        low = str(c).lower()
        if all(p in low for p in patterns):
            return c
    return None


def normalize_sample_value(x: object) -> Optional[str]:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s = str(x).strip().upper()
    if not s:
        return None
    s = re.sub(r'^\s*(\d{3})\s*$', r'SM\1', s)
    m = re.search(r'(SM\d{3})', s)
    if m:
        return m.group(1)
    return None


def has_column(conn, table: str, column: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
              AND column_name = %s
            LIMIT 1;
            """,
            (table, column),
        )
        return cur.fetchone() is not None


# =========================================================
# JSON metadata loader
# =========================================================
def _gold_path_from_json(gold: Optional[Dict[str, str]]) -> Optional[str]:
    if not gold or not isinstance(gold, dict):
        return None
    parts = []
    for k in ("ecosystem", "ecosystem_category", "ecosystem_type", "ecosystem_subtype", "specific_ecosystem"):
        v = gold.get(k)
        if v is None:
            continue
        s = str(v).strip().lower()
        s = re.sub(r"[^a-z0-9]+", "_", s)
        s = re.sub(r"_+", "_", s).strip("_")
        if s:
            parts.append(s)
    return ".".join(parts) if parts else None


def apply_json_metadata(conn, json_path: str):
    if not os.path.isfile(json_path):
        print(f"[json] metadata file not found, skipping: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as fh:
        meta = json.load(fh)

    print(f"[json] applying metadata from: {json_path}")

    with conn.cursor() as cur:
        for r in meta.get("resources", []):
            doi = r.get("doi")
            title = r.get("title")
            url = r.get("url")
            if not (doi or url):
                continue
            cur.execute(
                """
                SELECT resource_id FROM resource
                WHERE (doi IS NOT DISTINCT FROM %s) OR (url IS NOT DISTINCT FROM %s)
                LIMIT 1;
                """,
                (doi, url),
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    """
                    UPDATE resource
                       SET title = COALESCE(%s, title),
                           url   = COALESCE(%s, url)
                     WHERE resource_id = %s;
                    """,
                    (title, url, row[0]),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO resource(doi, title, url)
                    VALUES (%s, %s, %s);
                    """,
                    (doi, title, url),
                )

        for s in meta.get("studies", []):
            name = s.get("name")
            if not name:
                continue
            desc = s.get("description")
            cur.execute("SELECT 1 FROM study WHERE name=%s LIMIT 1;", (name,))
            if cur.fetchone() is None:
                cur.execute("INSERT INTO study(name, description) VALUES (%s, %s);", (name, desc))
            else:
                cur.execute(
                    "UPDATE study SET description = COALESCE(%s, description) WHERE name=%s;",
                    (desc, name),
                )

        for loc in meta.get("locations", []):
            name = loc.get("name")
            if not name:
                continue
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            elev = loc.get("elevation_m")
            cur.execute("SELECT location_id FROM location WHERE name=%s LIMIT 1;", (name,))
            row = cur.fetchone()
            if row is None:
                if has_column(conn, "location", "elevation_m"):
                    cur.execute(
                        "INSERT INTO location(name, latitude, longitude, elevation_m) VALUES (%s, %s, %s, %s);",
                        (name, lat, lon, elev),
                    )
                else:
                    cur.execute(
                        "INSERT INTO location(name, latitude, longitude) VALUES (%s, %s, %s);",
                        (name, lat, lon),
                    )
            else:
                if has_column(conn, "location", "elevation_m"):
                    cur.execute(
                        """
                        UPDATE location
                           SET latitude=COALESCE(%s,latitude),
                               longitude=COALESCE(%s,longitude),
                               elevation_m=COALESCE(%s,elevation_m)
                         WHERE location_id=%s;
                        """,
                        (lat, lon, elev, row[0]),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE location
                           SET latitude=COALESCE(%s,latitude),
                               longitude=COALESCE(%s,longitude)
                         WHERE location_id=%s;
                        """,
                        (lat, lon, row[0]),
                    )

        cur.execute("SELECT get_sample_type_id(%s);", ("Metagenome",))
        cur.execute("SELECT get_organism_type_id(%s);", ("Microbiome",))

        for s in meta.get("samples", []):
            ext = s.get("external_id")
            if not ext:
                continue
            loc_name = s.get("location_name")

            cur.execute("SELECT get_sample_type_id(%s);", ("Metagenome",))
            sample_type_id = cur.fetchone()[0]
            cur.execute("SELECT get_organism_type_id(%s);", ("Microbiome",))
            organism_type_id = cur.fetchone()[0]

            location_id = None
            if loc_name:
                cur.execute("SELECT location_id FROM location WHERE name=%s LIMIT 1;", (loc_name,))
                row = cur.fetchone()
                if row:
                    location_id = row[0]

            env_details = "grassland soil"
            elevation_m = s.get("elevation_m") or 117
            gold_path = _gold_path_from_json(s.get("gold")) or "terrestrial.soil.grassland.arid_grassland.arid_grassland_soils"

            cur.execute("SELECT sample_id FROM sample WHERE external_id=%s LIMIT 1;", (ext,))
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    """
                    INSERT INTO sample(
                      sample_type_id, organism_type_id, anatomical_site_id, location_id, external_id,
                      collection_date, elevation_m, environment_scheme_id, environment_path,
                      environment_text, environment_details
                    )
                    VALUES (%s, %s, NULL, %s, %s, NULL, %s, NULL, %s, %s, %s);
                    """,
                    (sample_type_id, organism_type_id, location_id, ext, elevation_m, gold_path, None, env_details),
                )
            else:
                cur.execute(
                    """
                    UPDATE sample
                       SET sample_type_id=COALESCE(%s,sample_type_id),
                           organism_type_id=COALESCE(%s,organism_type_id),
                           location_id=COALESCE(%s,location_id),
                           elevation_m=COALESCE(%s,elevation_m),
                           environment_path=COALESCE(%s,environment_path),
                           environment_text=NULL,
                           environment_details=COALESCE(%s,environment_details)
                     WHERE sample_id=%s;
                    """,
                    (sample_type_id, organism_type_id, location_id, elevation_m, gold_path, env_details, row[0]),
                )

    conn.commit()
    print("[json] resources/studies/location/types/samples ensured")


# =========================================================
# Staging loaders
# =========================================================
def _append_contig_sample_map(
    conn,
    contig_names: List[str],
    sample_col: Optional[pd.Series],
    src: str,
    prio: int,
):
    if sample_col is None:
        return
    df = pd.DataFrame({"contig_name": contig_names, "sample_raw": sample_col})
    df["sample_ext"] = df["sample_raw"].apply(normalize_sample_value)
    df["contig_token"] = df["contig_name"].apply(contig_token)
    df["src"] = src
    df["prio"] = prio
    df = df.dropna(subset=["contig_name", "sample_ext", "contig_token"])
    if not df.empty:
        copy_dataframe(
            conn,
            df[["contig_name", "contig_token", "sample_ext", "src", "prio"]],
            "st_wu_contig_sample",
            ["contig_name", "contig_token", "sample_ext", "src", "prio"],
        )


def _append_contig_sample_from_bins(conn, contig_names: List[str], bin_col: pd.Series):
    df = pd.DataFrame({"contig_name": contig_names, "bin_raw": bin_col})
    df["sample_digits"] = df["bin_raw"].astype(str).str.extract(r'^\s*(\d{3})\s*PNNLbin_\d+\s*$', expand=False)
    df["sample_ext"] = df["sample_digits"].where(df["sample_digits"].isna(), "SM" + df["sample_digits"])
    df["contig_token"] = df["contig_name"].apply(contig_token)
    df["src"] = "Supp7"
    df["prio"] = 4
    df = df.dropna(subset=["contig_name", "sample_ext", "contig_token"])
    if not df.empty:
        copy_dataframe(
            conn,
            df[["contig_name", "contig_token", "sample_ext", "src", "prio"]],
            "st_wu_contig_sample",
            ["contig_name", "contig_token", "sample_ext", "src", "prio"],
        )


def load_fna_to_staging(conn, fna_path: str):
    print(f"[stage] Loading contigs from FASTA: {fna_path}")
    rows = []
    map_rows = []
    n = 0

    with open(fna_path, "rt", encoding="utf-8", errors="replace") as fh:
        name, buf = None, []
        for line in fh:
            if line.startswith(">"):
                if name is not None:
                    seq = re.sub(r"[^ACGTRYSWKMBDHVN\.\-]", "", "".join(buf).upper())
                    rows.append((name, contig_token(name), seq, len(seq)))
                header = line[1:].strip()
                name = header.split()[0]
                tok = contig_token(name)
                for sm in re.findall(r"sample=(SM\d{3})", header, flags=re.IGNORECASE):
                    map_rows.append((name, tok, sm.upper(), "FASTA", 1))
                buf = []
                n += 1
                if len(rows) >= 10000:
                    copy_dataframe(
                        conn,
                        pd.DataFrame(rows, columns=["name", "contig_token", "seq", "length"]),
                        "st_wu_contigs",
                        ["name", "contig_token", "seq", "length"],
                    )
                    rows = []
            else:
                buf.append(line.strip())

        if name is not None:
            seq = re.sub(r"[^ACGTRYSWKMBDHVN\.\-]", "", "".join(buf).upper())
            rows.append((name, contig_token(name), seq, len(seq)))

    if rows:
        copy_dataframe(
            conn,
            pd.DataFrame(rows, columns=["name", "contig_token", "seq", "length"]),
            "st_wu_contigs",
            ["name", "contig_token", "seq", "length"],
        )

    if map_rows:
        copy_dataframe(
            conn,
            pd.DataFrame(map_rows, columns=["contig_name", "contig_token", "sample_ext", "src", "prio"]),
            "st_wu_contig_sample",
            ["contig_name", "contig_token", "sample_ext", "src", "prio"],
        )
        print(f"[stage] st_wu_contig_sample rows (from FASTA headers): {len(map_rows)}")
    else:
        print("[stage] st_wu_contig_sample: no sample=SM### tags found in FASTA headers")

    print(f"[stage] st_wu_contigs rows: ~{n}")


def load_hic_tsv(conn, tsv_path: str):
    print(f"[stage] Loading primary Hi-C TSV: {tsv_path}")
    total = 0
    for chunk in pd.read_csv(tsv_path, sep="\t", dtype=str, chunksize=CHUNK_ROWS, encoding_errors="ignore"):
        cols_map = normalize_headers(list(chunk.columns))
        c = chunk.rename(columns=cols_map).copy()

        for k in ("sample", "viral_contig_name", "cluster_name"):
            if k not in c.columns:
                c[k] = None

        def prefer(d: Dict[str, str]) -> Optional[float]:
            for key in (
                "adjusted_inter_connective_linkage_density",
                "adjusted_inter_connective_linkage_density_reads_kbp_2",
                "raw_inter_vs_intra_ratio",
                "hic_score",
            ):
                v = d.get(key)
                if v is None or str(v).strip() == "":
                    continue
                try:
                    return float(str(v).replace(",", ""))
                except Exception:
                    continue
            return None

        c["sample_ext"] = c["sample"].apply(normalize_sample_value)
        c["contig_token"] = c["viral_contig_name"].apply(contig_token)
        c["preferred_score"] = c.apply(
            lambda r: prefer({k: (None if k not in c.columns else r.get(k)) for k in c.columns}),
            axis=1,
        )
        c["row_json"] = c.apply(
            lambda r: json.dumps({k: (None if pd.isna(r[k]) else r[k]) for k in c.columns}, ensure_ascii=False),
            axis=1,
        )

        sub = c[["sample_ext", "viral_contig_name", "contig_token", "cluster_name", "preferred_score", "row_json"]]
        sub = sub.dropna(subset=["sample_ext", "viral_contig_name", "contig_token", "cluster_name"])
        copy_dataframe(
            conn,
            sub,
            "st_wu_links",
            ["sample_ext", "viral_contig_name", "contig_token", "cluster_name", "preferred_score", "row_json"],
        )
        total += len(sub)

        _append_contig_sample_map(conn, c["viral_contig_name"].tolist(), c["sample"], src="TSV", prio=2)

    print(f"[stage] st_wu_links rows: {total}")
    return total


def load_mags_dir_aliases(conn, mags_dir: str, base_dir: str):
    print(f"[stage] Scanning MAGs_dir for aliases: {mags_dir}")
    aliases = []
    for path in sorted(glob.glob(os.path.join(mags_dir, "**", "*.fsa"), recursive=True)):
        alias = os.path.splitext(os.path.basename(path))[0]
        rel_path = os.path.relpath(path, start=base_dir)
        aliases.append((alias, rel_path))
    if not aliases:
        print("[stage] MAGs_dir: no .fsa files found")
        return 0
    copy_dataframe(
        conn,
        pd.DataFrame(aliases, columns=["alias", "mag_file_path"]),
        "st_wu_mags",
        ["alias", "mag_file_path"],
    )
    print(f"[stage] st_wu_mags rows: {len(aliases)}")
    return len(aliases)


def parse_s1_meta(df: pd.DataFrame) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    doi = None
    biop = None
    study = "Wu et al. Hi-C Soil"
    try:
        for col in df.columns:
            s = df[col].astype(str).fillna("")
            hit = s[s.str.contains(r"\b10\.", na=False)]
            if not hit.empty:
                doi = hit.iloc[0].strip()
                break
        for name in df.columns:
            if "bioproject" in str(name).lower():
                vals = df[name].dropna().astype(str).values
                if len(vals):
                    v = str(vals[0]).strip()
                    biop = v if v else None
                    break
    except Exception:
        pass
    return study, doi, biop


def stage_wu_viral_taxonomy(conn, contig_names: pd.Series, family_series: pd.Series):
    tax_df = pd.DataFrame({
        "contig_name": contig_names.astype(str),
        "contig_token": contig_names.astype(str).apply(contig_token),
        "taxonomy": family_series.apply(canonical_wu_viral_taxonomy),
    })
    tax_df = tax_df.dropna(subset=["contig_name", "contig_token", "taxonomy"]).drop_duplicates()
    if not tax_df.empty:
        copy_dataframe(
            conn,
            tax_df,
            "st_wu_viral_taxonomy",
            ["contig_name", "contig_token", "taxonomy"],
        )


def load_s2(conn, path: str):
    print(f"[stage] Loading Supp.2 (vOTU/QC): {path}")
    df = read_tabular_any(path)
    df = df.rename(columns=normalize_headers(df.columns.tolist()))

    if "viral_contig_name" not in df.columns:
        raise ValueError(f"Supp2: missing 'viral_contig_name'. Found columns: {list(df.columns)}")

    df["contig_id"] = df["viral_contig_name"].astype(str)
    df["contig_token"] = df["contig_id"].apply(contig_token)
    df["length"] = pd.to_numeric(df.get("length"), errors="coerce").astype("Int64")
    df["votu"] = df["votu_assignment"] if "votu_assignment" in df.columns else None

    rep_col = "representative_of_votu" if "representative_of_votu" in df.columns else None
    if rep_col:
        df["is_representative"] = (df["contig_id"] == df[rep_col].astype(str)).astype(int)
    else:
        df["is_representative"] = 0

    keep = set(df.columns) - {"contig_id", "contig_token", "length", "votu", "is_representative"}
    df["qc_json"] = df.apply(
        lambda r: json.dumps({k: (None if pd.isna(r[k]) else r[k]) for k in keep}, ensure_ascii=False),
        axis=1,
    )

    out = df[["contig_id", "contig_token", "length", "votu", "is_representative", "qc_json"]]
    copy_dataframe(
        conn,
        out,
        "st_wu_s2_votu",
        ["contig_id", "contig_token", "length", "votu", "is_representative", "qc_json"],
    )
    print(f"[stage] st_wu_s2_votu rows: {len(out)}")

    if rep_col:
        print(f"[stage] st_wu_s2_votu representatives detected: {int(df['is_representative'].sum())}")

    demo_col = None
    if "demovir_taxonomy_classification" in df.columns:
        demo_col = "demovir_taxonomy_classification"
    else:
        demo_col = find_first_matching_column(df, "demovir", "taxonomy")

    if demo_col:
        stage_wu_viral_taxonomy(conn, df["contig_id"], df[demo_col])
        n_tax = int(df[demo_col].apply(canonical_wu_viral_taxonomy).notna().sum())
        print(f"[stage] st_wu_viral_taxonomy rows added from Supp.2: {n_tax}")


def load_s4(conn, path: str):
    print(f"[stage] Loading Supp.4 (unfiltered Hi-C): {path}")
    df = read_tabular_any(path)
    df = df.rename(columns=normalize_headers(df.columns.tolist()))

    for n in ("mobile_contig_name", "bin_cluster_name"):
        if n not in df.columns:
            raise ValueError(f"Supp4: missing '{n}'")

    sample_col_name = "sample" if "sample" in df.columns else None
    df["sample_ext"] = df[sample_col_name].apply(normalize_sample_value) if sample_col_name else None
    df["viral_contig_name"] = df["mobile_contig_name"].astype(str)
    df["contig_token"] = df["viral_contig_name"].apply(contig_token)
    df["host_alias"] = df["bin_cluster_name"].astype(str)

    score_cols = [c for c in df.columns if c in (
        "adjusted_inter_connective_linkage_density",
        "adjusted_inter_vs_intra_ratio",
        "raw_inter_vs_intra_ratio",
    )]
    if score_cols:
        df["score"] = pd.to_numeric(df[score_cols[0]], errors="coerce")
    else:
        df["score"] = None

    df["row_json"] = df.apply(
        lambda r: json.dumps({k: (None if pd.isna(r[k]) else r[k]) for k in df.columns}, ensure_ascii=False),
        axis=1,
    )

    out = df[["sample_ext", "viral_contig_name", "contig_token", "host_alias", "score", "row_json"]]
    out = out.dropna(subset=["sample_ext", "viral_contig_name", "contig_token", "host_alias"])
    copy_dataframe(
        conn,
        out,
        "st_wu_s4_unfilt",
        ["sample_ext", "viral_contig_name", "contig_token", "host_alias", "score", "row_json"],
    )

    if sample_col_name:
        _append_contig_sample_map(conn, df["viral_contig_name"].tolist(), df[sample_col_name], src="Supp4", prio=3)

    print(f"[stage] st_wu_s4_unfilt rows: {len(out)}")


def load_s5(conn, path: str):
    print(f"[stage] Loading Supp.5 (filtered Hi-C): {path}")
    df = read_tabular_any(path)
    df = df.rename(columns=normalize_headers(df.columns.tolist()))

    for n in ("viral_contig_name", "host_mag_name"):
        if n not in df.columns:
            raise ValueError(f"Supp5: missing '{n}'")

    sample_col_name = "sampleid" if "sampleid" in df.columns else ("sample" if "sample" in df.columns else None)
    df["sample_ext"] = df[sample_col_name].apply(normalize_sample_value) if sample_col_name else None
    df["host_alias"] = df["host_mag_name"].astype(str)
    df["contig_token"] = df["viral_contig_name"].apply(contig_token)

    tax_cols = [c for c in df.columns if "host_lineage" in c or c == "host_lineage"]
    host_tax_raw = df[tax_cols[0]] if tax_cols else pd.Series([None] * len(df))
    host_tax_sanitized = host_tax_raw.apply(ltree_sanitize)
    df["host_taxonomy"] = host_tax_sanitized

    pref = None
    for c in ("hi_c_adjusted_inter_connective_linkage_density", "hi_c_adjusted_inter_vs_intra_ratio"):
        if c in df.columns:
            pref = c
            break
    df["score"] = pd.to_numeric(df[pref], errors="coerce") if pref else None

    df["row_json"] = df.apply(
        lambda r: json.dumps({k: (None if pd.isna(r[k]) else r[k]) for k in df.columns}, ensure_ascii=False),
        axis=1,
    )

    out = df[["sample_ext", "viral_contig_name", "contig_token", "host_alias", "host_taxonomy", "score", "row_json"]]
    out = out.dropna(subset=["sample_ext", "viral_contig_name", "contig_token", "host_alias"])
    copy_dataframe(
        conn,
        out,
        "st_wu_s5_filtered",
        ["sample_ext", "viral_contig_name", "contig_token", "host_alias", "host_taxonomy", "score", "row_json"],
    )

    if sample_col_name:
        _append_contig_sample_map(conn, df["viral_contig_name"].tolist(), df[sample_col_name], src="Supp5", prio=2)

    demo_col = None
    if "demovir_taxonomy_classification" in df.columns:
        demo_col = "demovir_taxonomy_classification"
    else:
        demo_col = find_first_matching_column(df, "demovir", "taxonomy")

    if demo_col:
        stage_wu_viral_taxonomy(conn, df["viral_contig_name"], df[demo_col])

    print(f"[stage] st_wu_s5_filtered rows: {len(out)}")
    nulled = host_tax_raw.notna() & host_tax_sanitized.isna()
    if nulled.any():
        print(f"[warn] {int(nulled.sum())} Supp.5 host taxonomy rows could not be sanitized and were stored as NULL")


def load_s6(conn, path: str):
    print(f"[stage] Loading Supp.6 (MAG taxonomy): {path}")
    df = read_tabular_any(path)
    df = df.rename(columns=normalize_headers(df.columns.tolist()))

    alias_col = None
    for cand in ("uniq_bin_id", "host_mag_name", "bin"):
        if cand in df.columns:
            alias_col = cand
            break
    if not alias_col:
        raise ValueError("Supp6: could not find MAG alias column (e.g., 'Uniq bin-ID')")

    raw_tax = df["gtdb_classification"] if "gtdb_classification" in df.columns else pd.Series([None] * len(df))
    sanitized = raw_tax.apply(ltree_sanitize)

    out = pd.DataFrame({
        "alias": df[alias_col].astype(str),
        "taxonomy": sanitized.astype(object),
    })
    out = out[(out["alias"].notna()) & (out["alias"].str.strip() != "")]
    copy_dataframe(conn, out, "st_wu_s6_magtax", ["alias", "taxonomy"])
    print(f"[stage] st_wu_s6_magtax rows: {len(out)}")

    bad = raw_tax.notna() & sanitized.isna()
    if bad.any():
        print(f"[warn] {int(bad.sum())} MAG taxonomy rows could not be sanitized to ltree; stored as NULL taxonomy")


def load_s7(conn, path: str):
    print(f"[stage] Loading Supp.7 (CRISPR): {path}")
    df = read_tabular_any(path)
    df = df.rename(columns=normalize_headers(df.columns.tolist()))

    for n in ("viralcontig", "bin"):
        if n not in df.columns:
            raise ValueError(f"Supp7: missing '{n}'")

    df["viral_contig_name"] = df["viralcontig"].astype(str)
    df["contig_token"] = df["viral_contig_name"].apply(contig_token)
    df["host_alias"] = df["bin"].astype(str).apply(normalize_bin_name)
    df["sample_ext"] = df["bin"].astype(str).str.extract(r'^\s*(\d{3})\s*PNNLbin_\d+\s*$', expand=False)
    df["sample_ext"] = df["sample_ext"].where(df["sample_ext"].isna(), "SM" + df["sample_ext"])

    _append_contig_sample_from_bins(conn, df["viral_contig_name"].tolist(), df["bin"])

    if "bitscore" in df.columns:
        sc = pd.to_numeric(df["bitscore"], errors="coerce")
    elif "pident" in df.columns:
        sc = pd.to_numeric(df["pident"], errors="coerce")
    else:
        sc = pd.Series([None] * len(df))
    df["score"] = sc

    df["row_json"] = df.apply(
        lambda r: json.dumps({k: (None if pd.isna(r[k]) else r[k]) for k in df.columns}, ensure_ascii=False),
        axis=1,
    )
    out = df[["sample_ext", "viral_contig_name", "contig_token", "host_alias", "score", "row_json"]]
    out = out.dropna(subset=["sample_ext", "viral_contig_name", "contig_token", "host_alias"])
    copy_dataframe(
        conn,
        out,
        "st_wu_s7_crispr",
        ["sample_ext", "viral_contig_name", "contig_token", "host_alias", "score", "row_json"],
    )
    print(f"[stage] st_wu_s7_crispr rows: {len(out)}")


def note_skipped_file(label: str, path: str, reason: str):
    print(f"[stage] Skipping {label}: {path}")
    print(f"[stage] {reason}")


# =========================================================
# Main
# =========================================================
def main():
    ap = argparse.ArgumentParser(
        description="Load Wu et al. Hi-C soil resource into the SQL schema (idempotent).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--dsn", required=True, help='psycopg2 DSN, e.g. "dbname=hvp user=me port=5432 gssencmode=disable"')
    ap.add_argument("--base-dir", default=os.path.join("build", "resource", "HiC_Wu"))
    ap.add_argument("--fna", default=None, help="Override path to viral_contigs.fna")
    ap.add_argument("--hic-tsv", default=None, help="Override path to viral_host_associations_HiC.tsv")
    ap.add_argument("--mags-dir", default=None, help="Override path to MAGs_dir/")
    ap.add_argument("--keep-staging", action="store_true", help="Keep staging tables (default: drop)")
    args = ap.parse_args()

    base = args.base_dir
    fna = args.fna or os.path.join(base, "viral_contigs.fna")
    tsv = args.hic_tsv or os.path.join(base, "viral_host_associations_HiC.tsv")
    mags_dir = args.mags_dir or os.path.join(base, "MAGs_dir")
    json_meta = os.path.join(base, "wu2023_hic_soil.json")

    s1 = find_file(base, "wu_hiC_supp_1")
    s2 = find_file(base, "wu_hiC_supp_2")
    s3 = find_file(base, "wu_hiC_supp_3")
    s4 = find_file(base, "wu_hiC_supp_4")
    s5 = find_file(base, "wu_hiC_supp_5")
    s6 = find_file(base, "wu_hiC_supp_6")
    s7 = find_file(base, "wu_hiC_supp_7")
    s8 = find_file(base, "wu_hiC_supp_8")
    s9 = find_file(base, "wu_hiC_supp_9")

    print("==> Loader: Wu Hi-C soil")
    print("    - base-dir:       ", base)
    print("    - fna:            ", fna)
    print("    - tsv:            ", tsv)
    print("    - mags-dir:       ", mags_dir)
    print("    - supp1:          ", s1)
    print("    - supp2:          ", s2)
    print("    - supp3:          ", s3)
    print("    - supp4:          ", s4)
    print("    - supp5:          ", s5)
    print("    - supp6:          ", s6)
    print("    - supp7:          ", s7)
    print("    - supp8:          ", s8)
    print("    - supp9:          ", s9)
    print("    - json:           ", json_meta if os.path.isfile(json_meta) else "(missing)")

    conn = psycopg2.connect(args.dsn)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            cur.execute(SQL_HELPERS)
            conn.commit()
            cur.execute(SQL_SCHEMA_COMPAT)
            conn.commit()
            cur.execute(SQL_STAGING)
            conn.commit()
        print("[ok] helper functions + schema compatibility + staging initialized")

        apply_json_metadata(conn, json_meta)

        s1_df = read_tabular_any(s1)
        study_name, doi, biop = parse_s1_meta(s1_df)
        print(f"[meta] study='{study_name}' doi='{doi}' bioproject='{biop}'")

        with conn.cursor() as cur:
            cur.execute(render_sql(SQL_ENSURE_STUDY_RESOURCE, study_name=study_name, doi=doi))
            conn.commit()
            cur.execute(SQL_INTERNAL_RESOURCE)
            conn.commit()
        print("[ok] study/resource rows ensured")

        with conn.cursor() as cur:
            cur.execute(render_sql(SQL_WU_METAGENOME, mg_name=MG_NAME))
            conn.commit()

        if not os.path.isfile(fna):
            raise FileNotFoundError(f"FASTA not found: {fna}")
        load_fna_to_staging(conn, fna)

        if not os.path.isfile(tsv):
            raise FileNotFoundError(f"Hi-C TSV not found: {tsv}")
        load_hic_tsv(conn, tsv)

        if os.path.isdir(mags_dir):
            load_mags_dir_aliases(conn, mags_dir, base)

        load_s2(conn, s2)
        note_skipped_file(
            "Supp.3",
            s3,
            "Supplementary Data 3 is per-sample viral coverage/breadth. It is not a contig catalog, host-link table, or taxonomy table, so it is not loaded into the current schema.",
        )
        load_s4(conn, s4)
        load_s5(conn, s5)
        load_s6(conn, s6)
        load_s7(conn, s7)
        note_skipped_file(
            "Supp.8",
            s8,
            "Supplementary Data 8 is microbial co-occurrence network node statistics. It does not map to the current HVP schema.",
        )
        note_skipped_file(
            "Supp.9",
            s9,
            "Supplementary Data 9 contains differential abundances in argS gene transcripts from metatranscriptomes. It is not a viral AVG gene catalog and should not be loaded into avg_gene.",
        )

        with conn.cursor() as cur:
            cur.execute(SQL_PER_SAMPLE_METAGENOMES)
            conn.commit()

        with conn.cursor() as cur:
            cur.execute(render_sql(SQL_LINK_SAMPLES_TO_STUDY, study_name=study_name, doi=doi))
            conn.commit()
        print("[ok] sample_study links ensured")

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM st_wu_contigs"); c_contigs = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM st_wu_s2_votu"); c_s2 = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM st_wu_s4_unfilt"); c_s4 = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM st_wu_s5_filtered"); c_s5 = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM st_wu_s6_magtax"); c_s6 = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM st_wu_s7_crispr"); c_s7 = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM st_wu_links"); c_tsv = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM st_wu_contig_sample"); c_map = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM st_wu_viral_taxonomy"); c_vtax = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM st_wu_mags"); c_mags = cur.fetchone()[0]

        print(
            f"[staging] contigs={c_contigs} supp2={c_s2} tsv_links={c_tsv} "
            f"s4_unfilt={c_s4} s5_filt={c_s5} s6_magtax={c_s6} s7_crispr={c_s7} "
            f"contig_sample_map={c_map} viral_taxonomy={c_vtax} mags={c_mags}"
        )

        with conn.cursor() as cur:
            cur.execute("SELECT get_sample_type_id('Soil');")
            cur.execute("SELECT get_organism_type_id('Bacteriophage');")
            conn.commit()

            print("[norm] contigs/sequences -> viral_contig / viral_contig_sequence")
            cur.execute("""
                SELECT count(*)
                FROM viral_contig vc
                JOIN metagenome mg ON mg.metagenome_id = vc.metagenome_id
                WHERE mg.external_link = 'internal://HiC_Wu'
            """)
            before_vc = cur.fetchone()[0]

            cur.execute("""
                SELECT count(*)
                FROM viral_contig_sequence vcs
                JOIN viral_contig vc ON vc.contig_id = vcs.contig_id
                JOIN metagenome mg ON mg.metagenome_id = vc.metagenome_id
                WHERE mg.external_link = 'internal://HiC_Wu'
            """)
            before_vcs = cur.fetchone()[0]

            cur.execute(render_sql(SQL_NORMALIZE_CONTIGS, mg_name=MG_NAME))
            conn.commit()

            cur.execute("""
                SELECT count(*)
                FROM viral_contig vc
                JOIN metagenome mg ON mg.metagenome_id = vc.metagenome_id
                WHERE mg.external_link = 'internal://HiC_Wu'
            """)
            after_vc = cur.fetchone()[0]

            cur.execute("""
                SELECT count(*)
                FROM viral_contig_sequence vcs
                JOIN viral_contig vc ON vc.contig_id = vcs.contig_id
                JOIN metagenome mg ON mg.metagenome_id = vc.metagenome_id
                WHERE mg.external_link = 'internal://HiC_Wu'
            """)
            after_vcs = cur.fetchone()[0]

            print(f"[norm] Wu viral_contig: {before_vc} -> {after_vc} | Wu viral_contig_sequence: {before_vcs} -> {after_vcs}")

            print("[norm] Wu viral taxonomy -> virus_taxon / viral_contig.taxon_id")
            cur.execute("""
                SELECT count(*)
                FROM viral_contig vc
                JOIN metagenome mg ON mg.metagenome_id = vc.metagenome_id
                WHERE mg.external_link = 'internal://HiC_Wu'
                  AND vc.taxon_id IS NOT NULL
            """)
            before_tax = cur.fetchone()[0]

            cur.execute(SQL_NORMALIZE_WU_TAXONOMY)
            conn.commit()

            cur.execute("""
                SELECT count(*)
                FROM viral_contig vc
                JOIN metagenome mg ON mg.metagenome_id = vc.metagenome_id
                WHERE mg.external_link = 'internal://HiC_Wu'
                  AND vc.taxon_id IS NOT NULL
            """)
            after_tax = cur.fetchone()[0]

            print(f"[norm] Wu viral_contig with taxon_id: {before_tax} -> {after_tax}")

            print("[norm] hosts/taxonomy/MAG paths (Supp.6 + MAGs_dir)")
            cur.execute("SELECT count(*) FROM host"); before_host = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM host_alias"); before_alias = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM host WHERE mag_file_path IS NOT NULL"); before_magpath = cur.fetchone()[0]

            cur.execute(SQL_NORMALIZE_MAGS)
            conn.commit()

            cur.execute("SELECT count(*) FROM host"); after_host = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM host_alias"); after_alias = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM host WHERE mag_file_path IS NOT NULL"); after_magpath = cur.fetchone()[0]

            print(
                f"[norm] host: {before_host} -> {after_host} | "
                f"host_alias: {before_alias} -> {after_alias} | "
                f"host.mag_file_path: {before_magpath} -> {after_magpath}"
            )

            print("[norm] vOTU clusters (Supp.2)")
            cur.execute("SELECT count(*) FROM contig_cluster_member"); before_ccm = cur.fetchone()[0]
            cur.execute(SQL_NORMALIZE_VOTU)
            conn.commit()
            cur.execute("SELECT count(*) FROM contig_cluster_member"); after_ccm = cur.fetchone()[0]
            print(f"[norm] contig_cluster_member: {before_ccm} -> {after_ccm}")

            print("[norm] links (TSV + Supp.4/5/7)")
            cur.execute("SELECT count(*) FROM viral_contig_host"); before_vch = cur.fetchone()[0]
            cur.execute(render_sql(SQL_NORMALIZE_LINKS, doi=doi))
            conn.commit()
            cur.execute("SELECT count(*) FROM viral_contig_host"); after_vch = cur.fetchone()[0]
            print(f"[norm] viral_contig_host: {before_vch} -> {after_vch}")

        with conn.cursor() as cur:
            cur.execute(SQL_SANITY)
            rows = cur.fetchall()
        for what, cnt in rows:
            print(f"{what:12s} {cnt}")

        if not args.keep_staging:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DROP TABLE IF EXISTS st_wu_contig_sample;
                    DROP TABLE IF EXISTS st_wu_viral_taxonomy;
                    DROP TABLE IF EXISTS st_wu_s7_crispr;
                    DROP TABLE IF EXISTS st_wu_s6_magtax;
                    DROP TABLE IF EXISTS st_wu_s5_filtered;
                    DROP TABLE IF EXISTS st_wu_s4_unfilt;
                    DROP TABLE IF EXISTS st_wu_s2_votu;
                    DROP TABLE IF EXISTS st_wu_links;
                    DROP TABLE IF EXISTS st_wu_links_legacy;
                    DROP TABLE IF EXISTS st_wu_mags;
                    DROP TABLE IF EXISTS st_wu_contigs;
                    """
                )
                conn.commit()
            print("[cleanup] staging tables dropped")

        print("✅ Done.")
    except Exception as e:
        conn.rollback()
        print("❌ Error during load. Rolled back.", file=sys.stderr)
        print(str(e), file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()