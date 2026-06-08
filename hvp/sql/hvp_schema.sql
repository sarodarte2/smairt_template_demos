-- hvp_schema.sql

-- ================================
-- Extensions / types
-- ================================
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS ltree;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Evidence type
DO $$ BEGIN
  CREATE TYPE evidence_kind AS ENUM ('Computational','Experimental');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Generic sequence kind (used by avg_sequence and contig sequences)
DO $$ BEGIN
  CREATE TYPE sequence_kind AS ENUM ('Protein','Nucleotide');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ================================
-- Utility functions
-- ================================
-- Normalize a semicolon-separated taxonomy string into LTREE
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

-- Extract IMG OID digits from various strings
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

-- Parse contig full name into (img_oid, assembly_tag, contig_label)
CREATE OR REPLACE FUNCTION parse_contig_name(
  _name text,
  OUT img_oid text,
  OUT assembly_tag text,
  OUT contig_label text
) RETURNS record AS $$
DECLARE m text[];
BEGIN
  img_oid := NULL; assembly_tag := NULL; contig_label := NULL;
  IF _name IS NULL THEN RETURN; END IF;

  -- pattern: 2124908027.a:MRS2a_Contig_939
  m := regexp_match(_name, '^([0-9]{6,})(?:\.([A-Za-z0-9]+))?:(.+)$');
  IF m IS NOT NULL THEN
    img_oid := m[1];
    assembly_tag := m[2];
    contig_label := m[3];
  ELSE
    IF position(':' in _name) > 0 THEN
      contig_label := split_part(_name, ':', 2);
    ELSE
      contig_label := _name;
    END IF;
  END IF;
END$$ LANGUAGE plpgsql IMMUTABLE;

-- Parse trailing numeric index from a gene id (e.g., *_12 -> 12)
CREATE OR REPLACE FUNCTION parse_gene_index(_name text) RETURNS integer AS $$
DECLARE m text[];
BEGIN
  IF _name IS NULL THEN RETURN NULL; END IF;
  m := regexp_match(_name, '_(\d+)$');
  IF m IS NULL THEN RETURN NULL; END IF;
  RETURN m[1]::integer;
END$$ LANGUAGE plpgsql IMMUTABLE;

-- ================================
-- Lookups
-- ================================
CREATE TABLE IF NOT EXISTS resource (
  resource_id  BIGSERIAL PRIMARY KEY,
  doi          CITEXT UNIQUE,
  title        TEXT,
  url          TEXT,
  CONSTRAINT ck_resource_has_identifier CHECK (doi IS NOT NULL OR url IS NOT NULL),
  CONSTRAINT uq_resource_url UNIQUE (url)  -- NEW: required for ON CONFLICT (url)
);

CREATE TABLE IF NOT EXISTS sample_type (
  sample_type_id SMALLSERIAL PRIMARY KEY,
  name           TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS organism_type (
  organism_type_id SMALLSERIAL PRIMARY KEY,
  name             TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS environment_type (
  environment_type_id SMALLSERIAL PRIMARY KEY,
  name                TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS anatomical_site (
  anatomical_site_id SMALLSERIAL PRIMARY KEY,
  name               TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS location (
  location_id  BIGSERIAL PRIMARY KEY,
  name         TEXT NOT NULL,
  latitude     DOUBLE PRECISION,
  longitude    DOUBLE PRECISION,
  CONSTRAINT ck_lat_range CHECK (latitude  IS NULL OR (latitude  BETWEEN -90  AND 90)),
  CONSTRAINT ck_lon_range CHECK (longitude IS NULL OR (longitude BETWEEN -180 AND 180))
);

-- Environment classification schemes (e.g., GOLD, ENVO)
CREATE TABLE IF NOT EXISTS environment_scheme (
  scheme_id        SMALLSERIAL PRIMARY KEY,
  name             CITEXT UNIQUE NOT NULL,
  description      TEXT,
  is_hierarchical  BOOLEAN NOT NULL DEFAULT true
);

-- ================================
-- Study
-- ================================
CREATE TABLE IF NOT EXISTS study (
  study_id    BIGSERIAL PRIMARY KEY,
  name        CITEXT UNIQUE NOT NULL,
  description TEXT
);

CREATE TABLE IF NOT EXISTS resource_study (
  resource_id BIGINT REFERENCES resource(resource_id) ON DELETE CASCADE,
  study_id    BIGINT REFERENCES study(study_id)       ON DELETE CASCADE,
  PRIMARY KEY (resource_id, study_id)
);

-- ================================
-- Sample
-- ================================
CREATE TABLE IF NOT EXISTS sample (
  sample_id             BIGSERIAL PRIMARY KEY,
  sample_type_id        SMALLINT REFERENCES sample_type(sample_type_id),
  organism_type_id      SMALLINT REFERENCES organism_type(organism_type_id),
  anatomical_site_id    SMALLINT REFERENCES anatomical_site(anatomical_site_id),
  location_id           BIGINT   REFERENCES location(location_id),
  external_id           TEXT,
  collection_date       DATE,

  -- elevation in meters (harmonized from Elevation/Altitude)
  elevation_m           DOUBLE PRECISION,

  -- environment classification & values
  environment_scheme_id SMALLINT REFERENCES environment_scheme(scheme_id),
  environment_path      LTREE,   -- hierarchical schemes (e.g., GOLD)
  environment_text      TEXT,    -- non-hierarchical schemes
  environment_details   TEXT,    -- free text (e.g., GSVA “Habitat”)

  UNIQUE (external_id),

  CONSTRAINT ck_sample_env_oneof CHECK (
    (CASE WHEN environment_path IS NOT NULL THEN 1 ELSE 0 END) +
    (CASE WHEN environment_text IS NOT NULL AND btrim(environment_text) <> '' THEN 1 ELSE 0 END)
    IN (0,1)
  )
);

-- Optional: link samples ↔ studies (many-to-many)
CREATE TABLE IF NOT EXISTS sample_study (
  sample_id BIGINT REFERENCES sample(sample_id) ON DELETE CASCADE,
  study_id  BIGINT REFERENCES study(study_id)   ON DELETE CASCADE,
  PRIMARY KEY (sample_id, study_id)
);

CREATE TABLE IF NOT EXISTS resource_sample (
  resource_id BIGINT REFERENCES resource(resource_id) ON DELETE CASCADE,
  sample_id   BIGINT REFERENCES sample(sample_id)     ON DELETE CASCADE,
  PRIMARY KEY (resource_id, sample_id)
);

-- Legacy/aux environment tags (optional)
CREATE TABLE IF NOT EXISTS sample_environment (
  sample_id            BIGINT REFERENCES sample(sample_id) ON DELETE CASCADE,
  environment_type_id  SMALLINT REFERENCES environment_type(environment_type_id),
  PRIMARY KEY (sample_id, environment_type_id)
);

-- ================================
-- Assemblies / contigs / taxonomy
-- ================================
CREATE TABLE IF NOT EXISTS metagenome (
  metagenome_id     BIGSERIAL PRIMARY KEY,
  sample_id         BIGINT REFERENCES sample(sample_id),
  name              TEXT NOT NULL,
  external_link     TEXT,
  organism_type_id  SMALLINT REFERENCES organism_type(organism_type_id)  -- leaf of taxonomy for the metagenome (optional)
);

CREATE TABLE IF NOT EXISTS resource_metagenome (
  resource_id   BIGINT REFERENCES resource(resource_id)     ON DELETE CASCADE,
  metagenome_id BIGINT REFERENCES metagenome(metagenome_id) ON DELETE CASCADE,
  PRIMARY KEY (resource_id, metagenome_id)
);

CREATE TABLE IF NOT EXISTS virus_taxon (
  taxon_id   BIGSERIAL PRIMARY KEY,
  name       TEXT,
  rank       TEXT,
  parent_id  BIGINT REFERENCES virus_taxon(taxon_id),
  path       LTREE
);
CREATE INDEX IF NOT EXISTS virus_taxon_path_idx ON virus_taxon USING GIST (path);
ALTER TABLE virus_taxon
  ADD CONSTRAINT uq_taxon_sibling UNIQUE (parent_id, name);
ALTER TABLE virus_taxon
  ADD CONSTRAINT ck_taxon_not_own_parent CHECK (parent_id IS NULL OR parent_id <> taxon_id);

-- Viral contigs (parsed fields are auto-filled by trigger)
CREATE TABLE IF NOT EXISTS viral_contig (
  contig_id        BIGSERIAL PRIMARY KEY,
  metagenome_id    BIGINT REFERENCES metagenome(metagenome_id),
  name             TEXT NOT NULL,                        -- full contig id (e.g., 2124908027.a:MRS2a_Contig_939)
  taxon_id         BIGINT REFERENCES virus_taxon(taxon_id),
  organism_type_id SMALLINT REFERENCES organism_type(organism_type_id), -- taxon leaf as organism_type (optional)

  -- parsed (optional)
  img_oid          TEXT,         -- digits-only; may be NULL if not present
  assembly_tag     TEXT,         -- optional tag after dot; may be NULL
  contig_label     TEXT,         -- right-of-colon part; fallback = name

  -- optionally store metadata from genome table
  contig_length    INTEGER,
  n_genes          INTEGER,

  CONSTRAINT uq_contig_per_metagenome UNIQUE (metagenome_id, name)
);

-- Nucleotide sequence for contigs (only when available/desired)
CREATE TABLE IF NOT EXISTS viral_contig_sequence (
  contig_id BIGINT PRIMARY KEY REFERENCES viral_contig(contig_id) ON DELETE CASCADE,
  sequence  TEXT NOT NULL,
  length    INTEGER,
  seq_type  sequence_kind NOT NULL DEFAULT 'Nucleotide',
  CONSTRAINT ck_contig_seq_alphabet CHECK (
    (seq_type = 'Nucleotide' AND sequence ~* '^[ACGTRYSWKMBDHVNU\\.\\-]+$')
    OR (seq_type = 'Protein' AND sequence ~* '^[ACDEFGHIKLMNPQRSTVWYBXZ\\*\\-]+$') -- rarely used
  )
);

-- ================================
-- Auxiliary viral genes
-- ================================
CREATE TABLE IF NOT EXISTS avg_gene (
  avg_id        BIGSERIAL PRIMARY KEY,
  contig_id     BIGINT REFERENCES viral_contig(contig_id),
  name          TEXT,
  start_nt      INTEGER,
  end_nt        INTEGER,
  strand        SMALLINT,     -- 1 forward, -1 reverse, NULL unknown
  strand_num    SMALLINT,     -- 1 single, 2 double, NULL unknown
  length_nt     INTEGER,
  gene_index    INTEGER,      -- parsed trailing index (e.g., 12), NULL if absent
  CONSTRAINT ck_avg_coords CHECK (
    start_nt IS NULL OR end_nt IS NULL OR (start_nt >= 1 AND end_nt >= start_nt)
  ),
  CONSTRAINT ck_avg_strand CHECK (strand IN (-1, 1) OR strand IS NULL),
  CONSTRAINT ck_avg_strandedness CHECK (strand_num IN (1, 2) OR strand_num IS NULL),
  CONSTRAINT uq_avg_per_contig_name UNIQUE (contig_id, name)  -- NEW: prevent duplicates
);

-- Per-AVG sequences (protein or nucleotide; proteins for GSVA)
CREATE TABLE IF NOT EXISTS avg_sequence (
  avg_id    BIGINT PRIMARY KEY REFERENCES avg_gene(avg_id) ON DELETE CASCADE,
  sequence  TEXT NOT NULL,
  length    INTEGER,
  seq_type  sequence_kind NOT NULL DEFAULT 'Protein',
  CONSTRAINT ck_avg_seq_alphabet CHECK (
    (seq_type = 'Protein' AND sequence ~* '^[ACDEFGHIKLMNPQRSTVWYBXZ\\*\\-]+$')
    OR
    (seq_type = 'Nucleotide' AND sequence ~* '^[ACGTRYSWKMBDHVNU\\.\\-]+$')
  )
);

-- ================================
-- Contig-level clustering (vOTU/genus/family)
-- ================================
CREATE TABLE IF NOT EXISTS contig_cluster_set (
  cluster_set_id BIGSERIAL PRIMARY KEY,
  name           TEXT NOT NULL,  -- e.g., 'vOTU', 'genus_cluster', 'family_cluster'
  method         TEXT,
  version        TEXT,
  parameters     JSONB,
  CONSTRAINT uq_cluster_set UNIQUE (name, method, version)  -- NEW: supports ON CONFLICT in loader
);

CREATE TABLE IF NOT EXISTS contig_cluster (
  cluster_id     BIGSERIAL PRIMARY KEY,
  cluster_set_id BIGINT REFERENCES contig_cluster_set(cluster_set_id),
  name           TEXT NOT NULL,       -- e.g., 'vOTU_000144', 'gc_000402', 'fc_000560'
  representative_contig_id BIGINT REFERENCES viral_contig(contig_id),
  CONSTRAINT uq_contig_cluster_name_per_set UNIQUE (cluster_set_id, name)
);

CREATE TABLE IF NOT EXISTS contig_cluster_member (
  contig_id  BIGINT REFERENCES viral_contig(contig_id)       ON DELETE CASCADE,
  cluster_id BIGINT REFERENCES contig_cluster(cluster_id)    ON DELETE CASCADE,
  PRIMARY KEY (contig_id, cluster_id)
);

-- ================================
-- Evidence catalog & assertions
-- ================================
CREATE TABLE IF NOT EXISTS evidence_method (
  method_id     BIGSERIAL PRIMARY KEY,
  method_name   TEXT UNIQUE NOT NULL,
  evidence_type evidence_kind NOT NULL,
  version       TEXT,
  parameters    JSONB
);

CREATE TABLE IF NOT EXISTS applies_to (
  code         TEXT PRIMARY KEY,
  description  TEXT
);

CREATE TABLE IF NOT EXISTS method_scope (
  method_id   BIGINT REFERENCES evidence_method(method_id) ON DELETE CASCADE,
  applies_to  TEXT   REFERENCES applies_to(code)           ON DELETE CASCADE,
  PRIMARY KEY (method_id, applies_to)
);

-- Evidence about AVGs
CREATE TABLE IF NOT EXISTS avg_evidence (
  avg_id      BIGINT REFERENCES avg_gene(avg_id)             ON DELETE CASCADE,
  method_id   BIGINT REFERENCES evidence_method(method_id),
  resource_id BIGINT REFERENCES resource(resource_id),
  details     TEXT,
  score       REAL,
  PRIMARY KEY (avg_id, method_id, resource_id)
);

-- Functional annotation
CREATE TABLE IF NOT EXISTS function_term (
  function_id  BIGSERIAL PRIMARY KEY,
  name         TEXT UNIQUE NOT NULL,
  ontology_id  TEXT
);

CREATE TABLE IF NOT EXISTS avg_function (
  avg_id           BIGINT REFERENCES avg_gene(avg_id)          ON DELETE CASCADE,
  function_id      BIGINT REFERENCES function_term(function_id),
  resource_id      BIGINT REFERENCES resource(resource_id),
  method_id        BIGINT REFERENCES evidence_method(method_id),
  confidence_score REAL,
  PRIMARY KEY (avg_id, function_id, resource_id, method_id)
);

-- ================================
-- Bacterial/archaeal hosts & links
-- ================================
CREATE TABLE IF NOT EXISTS host (
  host_id       BIGSERIAL PRIMARY KEY,
  species       TEXT NOT NULL,
  taxonomy      LTREE,
  ncbi_taxon_id INTEGER,
  strain        TEXT
);

CREATE TABLE IF NOT EXISTS host_alias (
  host_id BIGINT REFERENCES host(host_id) ON DELETE CASCADE,
  alias  CITEXT NOT NULL,
  PRIMARY KEY (host_id, alias)
);

-- Gene-level (AVG) host evidence (kept for completeness)
CREATE TABLE IF NOT EXISTS avg_host (
  avg_id      BIGINT REFERENCES avg_gene(avg_id)            ON DELETE CASCADE,
  host_id     BIGINT REFERENCES host(host_id),
  method_id   BIGINT REFERENCES evidence_method(method_id),
  resource_id BIGINT REFERENCES resource(resource_id),
  PRIMARY KEY (avg_id, host_id, resource_id, method_id)
);

-- Contig-level host evidence (e.g., CRISPR spacers)
CREATE TABLE IF NOT EXISTS viral_contig_host (
  contig_id   BIGINT REFERENCES viral_contig(contig_id)     ON DELETE CASCADE,
  host_id     BIGINT REFERENCES host(host_id),
  method_id   BIGINT REFERENCES evidence_method(method_id),
  resource_id BIGINT REFERENCES resource(resource_id),
  score       REAL,     -- e.g., fraction of spacers supporting this host, if available
  details     TEXT,     -- JSON or free text with hit details
  PRIMARY KEY (contig_id, host_id, resource_id, method_id)
);

-- ================================
-- Chromatin-linked host genes (optional)
-- ================================
CREATE TABLE IF NOT EXISTS host_gene (
  host_gene_id BIGSERIAL PRIMARY KEY,
  symbol       TEXT NOT NULL,
  function     TEXT
);

CREATE TABLE IF NOT EXISTS avg_linked_host_gene (
  avg_id        BIGINT REFERENCES avg_gene(avg_id)           ON DELETE CASCADE,
  host_gene_id  BIGINT REFERENCES host_gene(host_gene_id),
  method_id     BIGINT REFERENCES evidence_method(method_id),
  distance_bp   INTEGER,
  resource_id   BIGINT REFERENCES resource(resource_id),
  PRIMARY KEY (avg_id, host_gene_id, resource_id, method_id)
);

-- ================================
-- Seeds: methods, scopes, schemes
-- ================================
INSERT INTO applies_to (code, description) VALUES
  ('avg',              'generic evidence about the AVG'),
  ('avg_function',     'function assignment for AVG'),
  ('avg_host',         'host assignment for AVG'),
  ('avg_linked_gene',  'chromatin/Hi-C linked host gene'),
  ('contig',           'contig-level calls'),
  ('taxon',            'taxonomy assignment'),
  ('cluster',          'clustering runs')
ON CONFLICT (code) DO NOTHING;

INSERT INTO evidence_method (method_id, method_name, evidence_type, version, parameters) VALUES
  (100, 'VirSorter2', 'Computational', NULL, NULL),
  (110, 'CRISPR-spacer', 'Experimental', NULL, NULL),
  (120, 'Hi-C', 'Experimental', NULL, NULL),
  (130, 'qPCR', 'Experimental', NULL, NULL)
ON CONFLICT (method_name) DO NOTHING;

SELECT setval(pg_get_serial_sequence('evidence_method','method_id'),
              GREATEST((SELECT COALESCE(MAX(method_id),0) FROM evidence_method), 130)+1,
              true);

-- Method scopes
INSERT INTO method_scope (method_id, applies_to) VALUES
  (100, 'avg'),
  (100, 'contig'),
  (100, 'cluster'),
  (120, 'avg_linked_gene'),
  (120, 'avg_host'),
  (110, 'avg_host'),
  (110, 'contig'),
  (130, 'avg_function')
ON CONFLICT (method_id, applies_to) DO NOTHING;

-- Seed GOLD as an environment scheme
INSERT INTO environment_scheme(name, description, is_hierarchical)
VALUES ('GOLD', 'DOE-JGI GOLD ecosystem classification', true)
ON CONFLICT (name) DO NOTHING;

-- ================================
-- Indexes
-- ================================
CREATE INDEX IF NOT EXISTS metagenome_sample_idx          ON metagenome(sample_id);
CREATE INDEX IF NOT EXISTS metagenome_orgtype_idx         ON metagenome(organism_type_id);

CREATE INDEX IF NOT EXISTS viral_contig_metagenome_idx    ON viral_contig(metagenome_id);
CREATE INDEX IF NOT EXISTS viral_contig_taxon_idx         ON viral_contig(taxon_id);
CREATE INDEX IF NOT EXISTS viral_contig_orgtype_idx       ON viral_contig(organism_type_id);
CREATE INDEX IF NOT EXISTS viral_contig_name_idx          ON viral_contig(name);  -- NEW: loader joins by name

CREATE INDEX IF NOT EXISTS avg_gene_contig_idx            ON avg_gene(contig_id);
CREATE INDEX IF NOT EXISTS avg_gene_name_idx              ON avg_gene(name);      -- NEW: loader joins by name
CREATE INDEX IF NOT EXISTS avg_sequence_avg_idx           ON avg_sequence(avg_id);

CREATE INDEX IF NOT EXISTS contig_cluster_member_contig_idx  ON contig_cluster_member(contig_id);
CREATE INDEX IF NOT EXISTS contig_cluster_member_cluster_idx ON contig_cluster_member(cluster_id);

CREATE INDEX IF NOT EXISTS avg_function_avg_idx           ON avg_function(avg_id);
CREATE INDEX IF NOT EXISTS avg_function_function_idx      ON avg_function(function_id);
CREATE INDEX IF NOT EXISTS avg_function_method_idx        ON avg_function(method_id);
CREATE INDEX IF NOT EXISTS avg_function_resource_idx      ON avg_function(resource_id);

CREATE INDEX IF NOT EXISTS avg_evidence_avg_idx           ON avg_evidence(avg_id);
CREATE INDEX IF NOT EXISTS avg_evidence_method_idx        ON avg_evidence(method_id);
CREATE INDEX IF NOT EXISTS avg_evidence_resource_idx      ON avg_evidence(resource_id);

CREATE INDEX IF NOT EXISTS sample_location_idx            ON sample(location_id);
CREATE INDEX IF NOT EXISTS sample_type_idx                ON sample(sample_type_id);
CREATE INDEX IF NOT EXISTS sample_organism_type_idx       ON sample(organism_type_id);
CREATE INDEX IF NOT EXISTS sample_anatomical_site_idx     ON sample(anatomical_site_id);

CREATE INDEX IF NOT EXISTS sample_env_scheme_idx          ON sample(environment_scheme_id);
CREATE INDEX IF NOT EXISTS sample_env_path_gist           ON sample USING GIST (environment_path);

CREATE INDEX IF NOT EXISTS sample_study_sample_idx        ON sample_study(sample_id);
CREATE INDEX IF NOT EXISTS sample_study_study_idx         ON sample_study(study_id);
CREATE INDEX IF NOT EXISTS resource_study_resource_idx    ON resource_study(resource_id);
CREATE INDEX IF NOT EXISTS resource_study_study_idx       ON resource_study(study_id);

CREATE INDEX IF NOT EXISTS host_alias_trgm_idx            ON host_alias USING GIN (alias gin_trgm_ops);
CREATE INDEX IF NOT EXISTS host_taxonomy_gist             ON host USING GIST (taxonomy);
CREATE INDEX IF NOT EXISTS host_species_taxon_idx         ON host(species, ncbi_taxon_id); -- NEW: aids joins

-- Helpful indexes for parsed fields
CREATE INDEX IF NOT EXISTS viral_contig_img_oid_idx       ON viral_contig (img_oid);
CREATE INDEX IF NOT EXISTS viral_contig_contig_label_idx  ON viral_contig (contig_label);
CREATE INDEX IF NOT EXISTS viral_contig_contig_label_trgm_idx
  ON viral_contig USING GIN (contig_label gin_trgm_ops);
CREATE INDEX IF NOT EXISTS avg_gene_contig_geneindex_idx  ON avg_gene (contig_id, gene_index);

-- ================================
-- Triggers: auto-fill parsed fields
-- ================================
CREATE OR REPLACE FUNCTION trg_vc_parse_name() RETURNS trigger AS $$
DECLARE p record;
BEGIN
  p := parse_contig_name(NEW.name);
  IF NEW.img_oid IS NULL THEN NEW.img_oid := p.img_oid; END IF;
  IF NEW.assembly_tag IS NULL THEN NEW.assembly_tag := p.assembly_tag; END IF;
  IF NEW.contig_label IS NULL THEN NEW.contig_label := COALESCE(p.contig_label, NEW.name); END IF;
  RETURN NEW;
END$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS t_vc_parse_name_biur ON viral_contig;
CREATE TRIGGER t_vc_parse_name_biur
BEFORE INSERT OR UPDATE ON viral_contig
FOR EACH ROW
EXECUTE FUNCTION trg_vc_parse_name();

CREATE OR REPLACE FUNCTION trg_ag_parse_name() RETURNS trigger AS $$
BEGIN
  IF NEW.gene_index IS NULL THEN
    NEW.gene_index := parse_gene_index(NEW.name);
  END IF;
  RETURN NEW;
END$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS t_ag_parse_name_biur ON avg_gene;
CREATE TRIGGER t_ag_parse_name_biur
BEFORE INSERT OR UPDATE ON avg_gene
FOR EACH ROW
EXECUTE FUNCTION trg_ag_parse_name();

-- ================================
-- One-time backfill for existing rows (parsed cols)
-- ================================
-- Use OUT-parameter field access; no FROM/LATERAL needed.
UPDATE viral_contig
SET
  img_oid      = COALESCE(img_oid,      (parse_contig_name(name)).img_oid),
  assembly_tag = COALESCE(assembly_tag, (parse_contig_name(name)).assembly_tag),
  contig_label = COALESCE(contig_label, COALESCE((parse_contig_name(name)).contig_label, name))
WHERE img_oid IS NULL
   OR assembly_tag IS NULL
   OR contig_label IS NULL;

-- Backfill gene_index from trailing suffix
UPDATE avg_gene
SET gene_index = parse_gene_index(name)
WHERE gene_index IS NULL;
