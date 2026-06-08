PRAGMA foreign_keys = ON;

-- helper: case-insensitive uniqueness via generated lower() indexes
-- (SQLite UNIQUE does not respect collations for case-insensitive uniqueness)
-- We'll add UNIQUE indexes on lower() after table creation.

-- Basic lookups --------------------------------------------------------------
CREATE TABLE resource (
  resource_id INTEGER PRIMARY KEY,
  doi         TEXT,          -- case-insensitive unique via index
  title       TEXT,
  url         TEXT,
  -- emulate the CHECK (doi IS NOT NULL OR url IS NOT NULL)
  -- (SQLite supports CHECK)
  CHECK (doi IS NOT NULL OR url IS NOT NULL)
);

CREATE TABLE sample_type (
  sample_type_id INTEGER PRIMARY KEY,
  name           TEXT NOT NULL
);

CREATE TABLE organism_type (
  organism_type_id INTEGER PRIMARY KEY,
  name             TEXT NOT NULL
);

CREATE TABLE environment_type (
  environment_type_id INTEGER PRIMARY KEY,
  name                TEXT NOT NULL
);

CREATE TABLE anatomical_site (
  anatomical_site_id INTEGER PRIMARY KEY,
  name               TEXT
);

CREATE TABLE location (
  location_id INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  latitude    REAL,
  longitude   REAL
);

-- Samples -------------------------------------------------------------------
CREATE TABLE sample (
  sample_id          INTEGER PRIMARY KEY,
  sample_type_id     INTEGER REFERENCES sample_type(sample_type_id),
  organism_type_id   INTEGER REFERENCES organism_type(organism_type_id),
  anatomical_site_id INTEGER REFERENCES anatomical_site(anatomical_site_id),
  location_id        INTEGER REFERENCES location(location_id),
  external_id        TEXT UNIQUE,
  collection_date    TEXT   -- store as ISO 'YYYY-MM-DD'
);

CREATE TABLE resource_sample (
  resource_id INTEGER REFERENCES resource(resource_id) ON DELETE CASCADE,
  sample_id   INTEGER REFERENCES sample(sample_id)     ON DELETE CASCADE,
  PRIMARY KEY (resource_id, sample_id)
);

CREATE TABLE sample_environment (
  sample_id           INTEGER REFERENCES sample(sample_id) ON DELETE CASCADE,
  environment_type_id INTEGER REFERENCES environment_type(environment_type_id),
  PRIMARY KEY (sample_id, environment_type_id)
);

-- Assemblies / taxonomy ------------------------------------------------------
CREATE TABLE virus_taxon (
  taxon_id  INTEGER PRIMARY KEY,
  name      TEXT,
  rank      TEXT,
  parent_id INTEGER REFERENCES virus_taxon(taxon_id),
  path      TEXT,  -- store dot-separated path e.g. 'Viruses.Caudovirales...'
  CHECK (parent_id IS NULL OR parent_id <> taxon_id)
);
-- emulate sibling uniqueness (parent_id, name)
CREATE UNIQUE INDEX uq_taxon_sibling ON virus_taxon(parent_id, name);

CREATE TABLE metagenome (
  metagenome_id INTEGER PRIMARY KEY,
  sample_id     INTEGER REFERENCES sample(sample_id),
  name          TEXT NOT NULL,
  external_link TEXT
);

CREATE TABLE resource_metagenome (
  resource_id   INTEGER REFERENCES resource(resource_id)     ON DELETE CASCADE,
  metagenome_id INTEGER REFERENCES metagenome(metagenome_id) ON DELETE CASCADE,
  PRIMARY KEY (resource_id, metagenome_id)
);

CREATE TABLE viral_contig (
  contig_id     INTEGER PRIMARY KEY,
  metagenome_id INTEGER REFERENCES metagenome(metagenome_id),
  name          TEXT NOT NULL,
  taxon_id      INTEGER REFERENCES virus_taxon(taxon_id),
  UNIQUE (metagenome_id, name)
);

-- AVGs -----------------------------------------------------------------------
CREATE TABLE avg_gene (
  avg_id     INTEGER PRIMARY KEY,
  contig_id  INTEGER REFERENCES viral_contig(contig_id),
  name       TEXT,
  start_nt   INTEGER,
  end_nt     INTEGER,
  strand     INTEGER,  -- -1, 1, or NULL
  strand_num INTEGER,  -- 1, 2, or NULL
  length_nt  INTEGER,
  CHECK (start_nt IS NULL OR end_nt IS NULL OR (start_nt >= 1 AND end_nt >= start_nt)),
  CHECK (strand IN (-1, 1) OR strand IS NULL),
  CHECK (strand_num IN (1, 2) OR strand_num IS NULL)
);

CREATE TABLE avg_sequence (
  avg_id      INTEGER PRIMARY KEY REFERENCES avg_gene(avg_id) ON DELETE CASCADE,
  sequence_nt TEXT NOT NULL,
  length_nt   INTEGER
  -- regex CHECK omitted (SQLite regexp needs a user function). Trust data here.
);

-- Evidence catalog & assertions ---------------------------------------------
-- evidence_kind enum -> TEXT with CHECK
CREATE TABLE evidence_method (
  method_id     INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,   -- unique via index
  evidence_type TEXT NOT NULL CHECK (evidence_type IN ('Computational','Experimental')),
  version       TEXT,
  parameters    TEXT             -- keep as JSON text (JSON1 optional)
);

CREATE UNIQUE INDEX uq_evidence_method_name ON evidence_method(name);

CREATE TABLE applies_to (
  code        TEXT PRIMARY KEY,  -- 'avg','avg_function', 'avg_host', ...
  description TEXT
);

CREATE TABLE method_scope (
  method_id  INTEGER REFERENCES evidence_method(method_id) ON DELETE CASCADE,
  applies_to TEXT   REFERENCES applies_to(code)            ON DELETE CASCADE,
  PRIMARY KEY (method_id, applies_to)
);

CREATE TABLE avg_evidence (
  avg_id      INTEGER REFERENCES avg_gene(avg_id)          ON DELETE CASCADE,
  method_id   INTEGER REFERENCES evidence_method(method_id),
  resource_id INTEGER REFERENCES resource(resource_id),
  details     TEXT,
  score       REAL,
  PRIMARY KEY (avg_id, method_id, resource_id)
);

-- Clustering -----------------------------------------------------------------
CREATE TABLE cluster_set (
  cluster_set_id INTEGER PRIMARY KEY,
  name           TEXT NOT NULL,
  method         TEXT,
  version        TEXT,
  parameters     TEXT  -- JSON text
);

CREATE TABLE avg_cluster (
  cluster_id     INTEGER PRIMARY KEY,
  cluster_set_id INTEGER REFERENCES cluster_set(cluster_set_id),
  name           TEXT NOT NULL,
  UNIQUE (cluster_set_id, name)
);

CREATE TABLE avg_cluster_member (
  avg_id     INTEGER REFERENCES avg_gene(avg_id)       ON DELETE CASCADE,
  cluster_id INTEGER REFERENCES avg_cluster(cluster_id) ON DELETE CASCADE,
  PRIMARY KEY (avg_id, cluster_id)
);

-- Functions ------------------------------------------------------------------
CREATE TABLE function_term (
  function_id INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  ontology_id TEXT
);
CREATE UNIQUE INDEX uq_function_term_name ON function_term(name);

CREATE TABLE avg_function (
  avg_id           INTEGER REFERENCES avg_gene(avg_id)           ON DELETE CASCADE,
  function_id      INTEGER REFERENCES function_term(function_id),
  resource_id      INTEGER REFERENCES resource(resource_id),
  method_id        INTEGER REFERENCES evidence_method(method_id),
  confidence_score REAL,
  PRIMARY KEY (avg_id, function_id, resource_id, method_id)
);

-- Hosts ----------------------------------------------------------------------
CREATE TABLE host (
  host_id      INTEGER PRIMARY KEY,
  species      TEXT NOT NULL,
  taxonomy     TEXT,     -- stored as dot path (no ltree)
  ncbi_taxon_id INTEGER,
  strain       TEXT
);

CREATE TABLE host_alias (
  host_id INTEGER REFERENCES host(host_id) ON DELETE CASCADE,
  alias  TEXT NOT NULL,
  PRIMARY KEY (host_id, alias)
);

CREATE TABLE avg_host (
  avg_id      INTEGER REFERENCES avg_gene(avg_id)   ON DELETE CASCADE,
  host_id     INTEGER REFERENCES host(host_id),
  method_id   INTEGER REFERENCES evidence_method(method_id),
  resource_id INTEGER REFERENCES resource(resource_id),
  PRIMARY KEY (avg_id, host_id, resource_id, method_id)
);

-- Chromatin-linked host genes ------------------------------------------------
CREATE TABLE host_gene (
  host_gene_id INTEGER PRIMARY KEY,
  symbol       TEXT NOT NULL,
  function     TEXT
);

CREATE TABLE avg_linked_host_gene (
  avg_id       INTEGER REFERENCES avg_gene(avg_id)       ON DELETE CASCADE,
  host_gene_id INTEGER REFERENCES host_gene(host_gene_id),
  method_id    INTEGER REFERENCES evidence_method(method_id),
  distance_bp  INTEGER,
  resource_id  INTEGER REFERENCES resource(resource_id),
  PRIMARY KEY (avg_id, host_gene_id, resource_id, method_id)
);

-- Case-insensitive unique equivalents
CREATE UNIQUE INDEX uq_resource_doi_nocase      ON resource(LOWER(doi));
CREATE UNIQUE INDEX uq_sample_type_name_nocase  ON sample_type(LOWER(name));
CREATE UNIQUE INDEX uq_organism_type_name_nc    ON organism_type(LOWER(name));
CREATE UNIQUE INDEX uq_env_type_name_nocase     ON environment_type(LOWER(name));
CREATE UNIQUE INDEX uq_anat_site_name_nocase    ON anatomical_site(LOWER(name));
CREATE UNIQUE INDEX uq_location_name_nocase     ON location(LOWER(name));
