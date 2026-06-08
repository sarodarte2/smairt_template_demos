-- views.sql
BEGIN;
SET search_path = public, pg_catalog;

-- Clean up / drop old stuff
DROP VIEW IF EXISTS
  v_metagenome_overview,
  v_contig_taxonomy,
  v_avg_gene_overview,
  v_avg_host_links,
  v_contig_host_links,
  v_avg_evidence_summary,
  v_resource_usage,
  v_method_scopes,
  v_function_catalog
CASCADE;

-- 1) SAMPLE VIEW
CREATE OR REPLACE VIEW v_sample_overview AS
SELECT
  s.sample_id,
  s.external_id,
  s.collection_date,
  st.name  AS sample_type,
  ot.name  AS organism_type,
  asite.name AS anatomical_site,
  l.name   AS location_name,
  l.latitude,
  l.longitude,
  s.elevation_m,
  es.name  AS environment_scheme,
  s.environment_path::text AS environment_path_text,
  CASE WHEN s.environment_path IS NULL THEN NULL
       ELSE subpath(s.environment_path, nlevel(s.environment_path)-1, 1)::text
  END      AS environment_leaf,
  s.environment_text,
  s.environment_details,
  -- convenience counts
  (SELECT COUNT(*) FROM metagenome m WHERE m.sample_id = s.sample_id) AS n_metagenomes,
  (SELECT COUNT(*)
     FROM metagenome m
     JOIN viral_contig vc ON vc.metagenome_id = m.metagenome_id
    WHERE m.sample_id = s.sample_id) AS n_contigs,
  (SELECT COUNT(*)
     FROM metagenome m
     JOIN viral_contig vc ON vc.metagenome_id = m.metagenome_id
     JOIN avg_gene g      ON g.contig_id = vc.contig_id
    WHERE m.sample_id = s.sample_id) AS n_avg_genes
FROM sample s
LEFT JOIN sample_type      st    ON st.sample_type_id         = s.sample_type_id
LEFT JOIN organism_type    ot    ON ot.organism_type_id       = s.organism_type_id
LEFT JOIN anatomical_site  asite ON asite.anatomical_site_id  = s.anatomical_site_id
LEFT JOIN location         l     ON l.location_id             = s.location_id
LEFT JOIN environment_scheme es  ON es.scheme_id              = s.environment_scheme_id;

-- 2) CONTIG VIEW
CREATE OR REPLACE VIEW v_contig_overview AS
SELECT
  vc.contig_id,
  vc.name                AS contig_name,
  vc.metagenome_id,
  m.name                 AS metagenome_name,
  s.sample_id,
  s.external_id          AS sample_external_id,
  vc.contig_length,
  vc.n_genes,
  vc.img_oid,
  vc.assembly_tag,
  vc.contig_label,
  ot.name                AS organism_type,
  t.taxon_id,
  t.name                 AS taxon_name,
  t.rank                 AS taxon_rank,
  t.parent_id,
  t.path::text           AS taxon_path_text,
  CASE WHEN t.path IS NULL THEN NULL
       ELSE subpath(t.path, nlevel(t.path)-1, 1)::text
  END                    AS taxon_leaf,
  EXISTS (SELECT 1 FROM viral_contig_sequence vcs WHERE vcs.contig_id = vc.contig_id) AS has_nt_sequence,
  (SELECT COUNT(*) FROM avg_gene g WHERE g.contig_id = vc.contig_id) AS n_avg_genes,
  (SELECT COUNT(*) FROM viral_contig_host vch WHERE vch.contig_id = vc.contig_id) AS n_host_links,
  -- cluster summaries per set
  (SELECT string_agg(DISTINCT cc.name, '; ' ORDER BY cc.name)
     FROM contig_cluster_member ccm
     JOIN contig_cluster cc      ON cc.cluster_id = ccm.cluster_id
     JOIN contig_cluster_set ccs ON ccs.cluster_set_id = cc.cluster_set_id
    WHERE ccm.contig_id = vc.contig_id AND ccs.name = 'vOTU')          AS votu_clusters,
  (SELECT string_agg(DISTINCT cc.name, '; ' ORDER BY cc.name)
     FROM contig_cluster_member ccm
     JOIN contig_cluster cc      ON cc.cluster_id = ccm.cluster_id
     JOIN contig_cluster_set ccs ON ccs.cluster_set_id = cc.cluster_set_id
    WHERE ccm.contig_id = vc.contig_id AND ccs.name = 'genus_cluster')  AS genus_clusters,
  (SELECT string_agg(DISTINCT cc.name, '; ' ORDER BY cc.name)
     FROM contig_cluster_member ccm
     JOIN contig_cluster cc      ON cc.cluster_id = ccm.cluster_id
     JOIN contig_cluster_set ccs ON ccs.cluster_set_id = cc.cluster_set_id
    WHERE ccm.contig_id = vc.contig_id AND ccs.name = 'family_cluster') AS family_clusters
FROM viral_contig vc
JOIN metagenome m         ON m.metagenome_id        = vc.metagenome_id
LEFT JOIN sample s        ON s.sample_id            = m.sample_id
LEFT JOIN organism_type ot ON ot.organism_type_id   = vc.organism_type_id
LEFT JOIN virus_taxon t    ON t.taxon_id            = vc.taxon_id;

-- 3) AVG  VIEW
CREATE OR REPLACE VIEW v_avg_overview AS
SELECT
  g.avg_id,
  g.name                 AS avg_name,
  g.gene_index,
  g.start_nt,
  g.end_nt,
  g.strand,
  g.strand_num,
  g.length_nt,
  vc.contig_id,
  vc.name                AS contig_name,
  vc.metagenome_id,
  m.name                 AS metagenome_name,
  s.sample_id,
  s.external_id          AS sample_external_id,
  l.name                 AS location_name,
  t.taxon_id             AS contig_taxon_id,
  t.name                 AS contig_taxon_name,
  t.path::text           AS contig_taxon_path_text,
  seq.length             AS protein_length,
  (seq.avg_id IS NOT NULL) AS has_protein_sequence,
  -- quick per-AVG counts
  (SELECT COUNT(*) FROM avg_function af WHERE af.avg_id = g.avg_id)  AS n_functions,
  (SELECT COUNT(*) FROM avg_evidence ae WHERE ae.avg_id = g.avg_id)  AS n_evidence,
  (SELECT COUNT(*) FROM avg_host ah    WHERE ah.avg_id = g.avg_id)   AS n_avg_host_links
FROM avg_gene g
JOIN viral_contig vc    ON vc.contig_id      = g.contig_id
JOIN metagenome  m      ON m.metagenome_id   = vc.metagenome_id
LEFT JOIN sample  s     ON s.sample_id       = m.sample_id
LEFT JOIN location l    ON l.location_id     = s.location_id
LEFT JOIN virus_taxon t ON t.taxon_id        = vc.taxon_id
LEFT JOIN avg_sequence seq ON seq.avg_id     = g.avg_id AND seq.seq_type = 'Protein';

-- 4) AVG FUNCTION ANNOTATIONS VIEW
CREATE OR REPLACE VIEW v_avg_function_annotations AS
SELECT
  af.avg_id,
  g.name                AS avg_name,
  vc.contig_id,
  vc.name               AS contig_name,
  m.metagenome_id,
  m.name                AS metagenome_name,
  s.sample_id,
  s.external_id         AS sample_external_id,
  ft.function_id,
  ft.name               AS function_name,
  ft.ontology_id,
  em.method_id,
  em.method_name,
  em.evidence_type,
  af.confidence_score,
  r.resource_id,
  COALESCE(r.doi::text, r.url) AS citation_key,
  r.title
FROM avg_function af
JOIN avg_gene g           ON g.avg_id        = af.avg_id
JOIN viral_contig vc      ON vc.contig_id    = g.contig_id
JOIN metagenome m         ON m.metagenome_id = vc.metagenome_id
LEFT JOIN sample s        ON s.sample_id     = m.sample_id
JOIN function_term ft     ON ft.function_id  = af.function_id
LEFT JOIN evidence_method em ON em.method_id = af.method_id
LEFT JOIN resource r         ON r.resource_id= af.resource_id;

-- 5) CLUSTER VIEW
CREATE OR REPLACE VIEW v_contig_cluster_members AS
SELECT
  ccs.cluster_set_id,
  ccs.name                 AS cluster_set_name,
  ccs.method               AS cluster_set_method,
  ccs.version              AS cluster_set_version,
  cc.cluster_id,
  cc.name                  AS cluster_name,
  -- cluster size and representative
  (SELECT COUNT(*) FROM contig_cluster_member ccm2 WHERE ccm2.cluster_id = cc.cluster_id) AS cluster_size,
  cc.representative_contig_id,
  repvc.name              AS representative_contig_name,
  -- membership
  vc.contig_id,
  vc.name                 AS contig_name,
  m.metagenome_id,
  m.name                  AS metagenome_name,
  (cc.representative_contig_id = vc.contig_id) AS is_representative
FROM contig_cluster_member ccm
JOIN contig_cluster      cc   ON cc.cluster_id       = ccm.cluster_id
JOIN contig_cluster_set  ccs  ON ccs.cluster_set_id  = cc.cluster_set_id
JOIN viral_contig        vc   ON vc.contig_id        = ccm.contig_id
JOIN metagenome          m    ON m.metagenome_id     = vc.metagenome_id
LEFT JOIN viral_contig   repvc ON repvc.contig_id    = cc.representative_contig_id;

COMMIT;
