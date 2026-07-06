#!/usr/bin/env python3
# test_hvp_load.py

import argparse
import os
import sys
from typing import Optional, Sequence, List, Tuple

import psycopg2


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def default_dsn() -> str:
    parts = [
        f"dbname={os.environ.get('DB_NAME', 'hvp')}",
        f"user={os.environ.get('DB_USER', os.environ.get('PGUSER', os.environ.get('USER', 'postgres')))}",
        f"port={os.environ.get('DB_PORT', os.environ.get('PGPORT', '5432'))}",
        "gssencmode=disable",
    ]
    host = os.environ.get("DB_HOST", os.environ.get("PGHOST", ""))
    if host:
        parts.append(f"host={host}")
    return " ".join(parts)


def scalar(cur, query: str, params: Optional[Sequence] = None):
    if params is None:
        cur.execute(query)
    else:
        cur.execute(query, params)
    row = cur.fetchone()
    return None if row is None else row[0]


def table_exists(cur, table_name: str) -> bool:
    return bool(
        scalar(
            cur,
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.tables
              WHERE table_schema = current_schema()
                AND table_name = %s
            )
            """,
            (table_name,),
        )
    )


def column_exists(cur, table_name: str, column_name: str) -> bool:
    return bool(
        scalar(
            cur,
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema = current_schema()
                AND table_name = %s
                AND column_name = %s
            )
            """,
            (table_name, column_name),
        )
    )


def record(results: List[Tuple[str, str, str]], passed: bool, name: str, msg: str):
    status = "PASS" if passed else "FAIL"
    results.append((status, name, msg))
    print(f"{status:5s} {name:35s} {msg}")


def info(results: List[Tuple[str, str, str]], name: str, msg: str):
    results.append(("INFO", name, msg))
    print(f"{'INFO':5s} {name:35s} {msg}")


# ---------------------------------------------------------
# Expectations for current database layout
# ---------------------------------------------------------
EXPECTED = {
    "sample": 2960,
    "metagenome": 2960,
    "viral_contig": 51398,
    "viral_contig_sequence": 51398,
    "host": 1788,
    "host_alias": 338,
    "viral_contig_host": 1856,
    "avg_gene": 1432147,
    "virus_taxon": 93,
    "avg_sequence": 1432147,
}

EXPECTED_WU = {
    "samples": 6,
    "fallback_sample": 1,
    "fallback_metagenome": 1,
    "per_sample_metagenomes": 6,
    "contigs": 1749,
    "taxonomy_assigned": 987,
    "votu_clusters": 479,
    "votu_representatives": 479,
    "normalized_mag_names": 338,
    "mag_file_paths": 338,
    "avg_genes": 0,
}

EXPECTED_GSVA = {
    "metagenomes": 2953,
    "contigs": 49649,
    "taxonomy_assigned": 49312,
    "environment_paths": 2953,
}

WU_STUDY = "Wu et al. Hi-C Soil"
WU_RESOURCE_URL = "internal://HiC_Wu"
GSVA_RESOURCE_URL = "internal://GSVA"
WU_FALLBACK_SAMPLE = "Wu_HiC_Soil"
WU_FALLBACK_METAGENOME = "Wu Soil Hi-C"
WU_CANONICAL_PATH = "Viruses.Duplodnaviria.Heunggongvirae.Uroviricota.Caudoviricetes"


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Validate HVP database load.")
    ap.add_argument("--dsn", default=default_dsn(), help="psycopg2 DSN")
    args = ap.parse_args()

    results: List[Tuple[str, str, str]] = []

    try:
        conn = psycopg2.connect(args.dsn)
    except Exception as e:
        print(f"FAIL  connect                             could not connect to database: {e}")
        sys.exit(1)

    try:
        with conn, conn.cursor() as cur:
            # -------------------------------------------------
            # Core counts
            # -------------------------------------------------
            for table, expected in EXPECTED.items():
                n = scalar(cur, f"SELECT COUNT(*) FROM {table}")
                record(results, n == expected, f"core_count:{table}", f"{table} rows = {n}")

            # -------------------------------------------------
            # Resource / study presence
            # -------------------------------------------------
            n = scalar(cur, "SELECT COUNT(*) FROM resource WHERE url = %s", (WU_RESOURCE_URL,))
            record(results, n == 1, "resource:HiC_Wu", f"{WU_RESOURCE_URL} rows = {n}")

            n = scalar(cur, "SELECT COUNT(*) FROM resource WHERE url = %s", (GSVA_RESOURCE_URL,))
            record(results, n == 1, "resource:GSVA", f"{GSVA_RESOURCE_URL} rows = {n}")

            n = scalar(cur, "SELECT COUNT(*) FROM study WHERE name = %s", (WU_STUDY,))
            record(results, n == 1, "study:Wu", f"'{WU_STUDY}' rows = {n}")

            # -------------------------------------------------
            # Wu sample / metagenome checks
            # -------------------------------------------------
            n = scalar(cur, "SELECT COUNT(*) FROM sample WHERE external_id = %s", (WU_FALLBACK_SAMPLE,))
            record(results, n == EXPECTED_WU["fallback_sample"], "wu:fallback_sample", f"{WU_FALLBACK_SAMPLE} rows = {n}")

            n = scalar(cur, "SELECT COUNT(*) FROM metagenome WHERE name = %s", (WU_FALLBACK_METAGENOME,))
            record(results, n == EXPECTED_WU["fallback_metagenome"], "wu:fallback_metagenome", f"{WU_FALLBACK_METAGENOME} rows = {n}")

            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM sample_study ss
                JOIN sample s ON s.sample_id = ss.sample_id
                JOIN study st ON st.study_id = ss.study_id
                WHERE st.name = %s
                  AND s.external_id ~ '^SM(297|306|317|324|330|335)$'
                """,
                (WU_STUDY,),
            )
            record(results, n == EXPECTED_WU["samples"], "wu:sample_study_links", f"Wu SM### sample_study links = {n}")

            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM sample_study ss
                JOIN sample s ON s.sample_id = ss.sample_id
                JOIN study st ON st.study_id = ss.study_id
                WHERE st.name = %s
                  AND s.external_id = %s
                """,
                (WU_STUDY, WU_FALLBACK_SAMPLE),
            )
            record(results, n == 1, "wu:fallback_sample_study_link", f"fallback sample_study links = {n}")

            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM metagenome
                WHERE external_link = %s
                  AND name ~ '^SM(297|306|317|324|330|335)$'
                """,
                (WU_RESOURCE_URL,),
            )
            record(results, n == EXPECTED_WU["per_sample_metagenomes"], "wu:per_sample_metagenomes", f"Wu SM### metagenomes = {n}")

            # -------------------------------------------------
            # Wu contigs / taxonomy
            # -------------------------------------------------
            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM viral_contig vc
                JOIN metagenome mg ON mg.metagenome_id = vc.metagenome_id
                WHERE mg.external_link = %s
                """,
                (WU_RESOURCE_URL,),
            )
            record(results, n == EXPECTED_WU["contigs"], "wu:contigs_loaded", f"Wu contigs = {n}")

            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM viral_contig vc
                JOIN metagenome mg ON mg.metagenome_id = vc.metagenome_id
                WHERE mg.external_link = %s
                  AND vc.taxon_id IS NOT NULL
                """,
                (WU_RESOURCE_URL,),
            )
            record(results, n == EXPECTED_WU["taxonomy_assigned"], "wu:taxonomy_assigned", f"Wu contigs with taxon_id = {n}")

            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM viral_contig vc
                JOIN metagenome mg ON mg.metagenome_id = vc.metagenome_id
                JOIN virus_taxon vt ON vt.taxon_id = vc.taxon_id
                WHERE mg.external_link = %s
                  AND vc.taxon_id IS NOT NULL
                  AND vt.path::text <> %s
                """,
                (WU_RESOURCE_URL, WU_CANONICAL_PATH),
            )
            record(results, n == 0, "wu:taxonomy_canonical_only", f"Wu contigs with non-canonical assigned taxonomy = {n}")

            # -------------------------------------------------
            # Wu vOTU checks
            # -------------------------------------------------
            n = scalar(
                cur,
                """
                SELECT COUNT(DISTINCT cc.cluster_id)
                FROM contig_cluster cc
                JOIN contig_cluster_set ccs ON ccs.cluster_set_id = cc.cluster_set_id
                JOIN contig_cluster_member ccm ON ccm.cluster_id = cc.cluster_id
                JOIN viral_contig vc ON vc.contig_id = ccm.contig_id
                JOIN metagenome mg ON mg.metagenome_id = vc.metagenome_id
                WHERE ccs.name = 'vOTU'
                  AND mg.external_link = %s
                """,
                (WU_RESOURCE_URL,),
            )
            record(results, n == EXPECTED_WU["votu_clusters"], "wu:votu_clusters_present", f"Wu vOTU clusters = {n}")

            n = scalar(
                cur,
                """
                SELECT COUNT(DISTINCT cc.cluster_id)
                FROM contig_cluster cc
                JOIN contig_cluster_set ccs ON ccs.cluster_set_id = cc.cluster_set_id
                JOIN viral_contig rep ON rep.contig_id = cc.representative_contig_id
                JOIN metagenome mg ON mg.metagenome_id = rep.metagenome_id
                WHERE ccs.name = 'vOTU'
                  AND mg.external_link = %s
                  AND cc.representative_contig_id IS NOT NULL
                """,
                (WU_RESOURCE_URL,),
            )
            record(results, n == EXPECTED_WU["votu_representatives"], "wu:votu_representatives_present", f"Wu vOTU clusters with representative = {n}")

            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM contig_cluster cc
                JOIN contig_cluster_set ccs ON ccs.cluster_set_id = cc.cluster_set_id
                JOIN viral_contig rep ON rep.contig_id = cc.representative_contig_id
                JOIN metagenome mg ON mg.metagenome_id = rep.metagenome_id
                WHERE ccs.name = 'vOTU'
                  AND mg.external_link = %s
                  AND cc.representative_contig_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1
                    FROM contig_cluster_member ccm
                    WHERE ccm.cluster_id = cc.cluster_id
                      AND ccm.contig_id = cc.representative_contig_id
                  )
                """,
                (WU_RESOURCE_URL,),
            )
            record(results, n == 0, "wu:votu_representative_is_member", f"Wu vOTU representative contigs not present as members = {n}")

            # -------------------------------------------------
            # Wu MAG / host checks
            # -------------------------------------------------
            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM host
                WHERE species ~ '\\.fsa$'
                """,
            )
            record(results, n == 0, "wu:mag_alias_no_fsa_suffix", f"host rows still ending in .fsa = {n}")

            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM host
                WHERE species ~ '^[0-9]{3}PNNLbin_[0-9]+$'
                """,
            )
            record(results, n == 0, "wu:supp7_old_bin_names_absent", f"old raw Supp.7 bin names still present in host.species = {n}")

            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM host
                WHERE species ~ '^PNNL_SM(297|306|317|324|330|335)_bin_[0-9]+$'
                """,
            )
            record(results, n == EXPECTED_WU["normalized_mag_names"], "wu:supp7_normalized_bin_names_present", f"normalized Supp.7 / MAG names in host.species = {n}")

            if column_exists(cur, "host", "mag_file_path"):
                n = scalar(
                    cur,
                    """
                    SELECT COUNT(*)
                    FROM host
                    WHERE species ~ '^PNNL_SM(297|306|317|324|330|335)_bin_[0-9]+$'
                      AND mag_file_path IS NOT NULL
                      AND mag_file_path LIKE '%/MAGs_dir/%'
                    """
                )
                record(results, n == EXPECTED_WU["mag_file_paths"], "wu:mag_file_paths_present", f"Wu MAG hosts with MAGs_dir paths = {n}")
            else:
                record(results, False, "wu:mag_file_paths_present", "host.mag_file_path column is missing")

            # -------------------------------------------------
            # GSVA checks
            #
            # Current loader does not rely on
            # metagenome.external_link='internal://GSVA'.
            # Define GSVA here as the non-Wu portion of the DB.
            # -------------------------------------------------
            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM metagenome mg
                WHERE mg.external_link IS DISTINCT FROM %s
                """,
                (WU_RESOURCE_URL,),
            )
            record(results, n == EXPECTED_GSVA["metagenomes"], "gsva:resource_metagenomes", f"GSVA-like metagenomes (non-Wu) = {n}")

            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM viral_contig vc
                JOIN metagenome mg ON mg.metagenome_id = vc.metagenome_id
                WHERE mg.external_link IS DISTINCT FROM %s
                """,
                (WU_RESOURCE_URL,),
            )
            record(results, n == EXPECTED_GSVA["contigs"], "gsva:contigs_loaded", f"GSVA-like contigs (non-Wu) = {n}")

            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM viral_contig vc
                JOIN metagenome mg ON mg.metagenome_id = vc.metagenome_id
                WHERE mg.external_link IS DISTINCT FROM %s
                  AND vc.taxon_id IS NOT NULL
                """,
                (WU_RESOURCE_URL,),
            )
            record(results, n == EXPECTED_GSVA["taxonomy_assigned"], "gsva:taxonomy_assigned", f"GSVA-like contigs with taxon_id = {n}")

            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM viral_contig vc
                JOIN metagenome mg ON mg.metagenome_id = vc.metagenome_id
                JOIN virus_taxon vt ON vt.taxon_id = vc.taxon_id
                WHERE mg.external_link IS DISTINCT FROM %s
                  AND vc.taxon_id IS NOT NULL
                  AND vt.path IS NULL
                """,
                (WU_RESOURCE_URL,),
            )
            record(results, n == 0, "gsva:taxonomy_paths_present", f"GSVA-like contigs with taxon_id but NULL virus_taxon.path = {n}")

            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM sample s
                JOIN metagenome mg ON mg.sample_id = s.sample_id
                WHERE mg.external_link IS DISTINCT FROM %s
                  AND s.environment_path IS NOT NULL
                """,
                (WU_RESOURCE_URL,),
            )
            record(results, n == EXPECTED_GSVA["environment_paths"], "gsva:sample_environment_paths", f"GSVA-like samples with environment_path = {n}")

            # -------------------------------------------------
            # Wu avg_gene checks
            # Supp.9 is argS transcript abundance, not AVG catalog.
            # So Wu avg_gene rows should currently be zero.
            # -------------------------------------------------
            n = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM avg_gene ag
                JOIN viral_contig vc ON vc.contig_id = ag.contig_id
                JOIN metagenome mg ON mg.metagenome_id = vc.metagenome_id
                WHERE mg.external_link = %s
                """,
                (WU_RESOURCE_URL,),
            )
            record(results, n == EXPECTED_WU["avg_genes"], "wu:avg_genes_not_loaded", f"Wu avg_gene rows on Wu contigs = {n}")

            # -------------------------------------------------
            # avg_host / avg_abundance informational checks
            # -------------------------------------------------
            if table_exists(cur, "avg_host"):
                n = scalar(cur, "SELECT COUNT(*) FROM avg_host")
                info(results, "avg_host", f"avg_host has {n} rows")
            else:
                info(results, "avg_host", "table avg_host does not exist")

            if table_exists(cur, "avg_abundance"):
                n = scalar(cur, "SELECT COUNT(*) FROM avg_abundance")
                info(results, "avg_abundance", f"avg_abundance has {n} rows")
            else:
                info(results, "avg_abundance", "table avg_abundance does not exist")

    finally:
        conn.close()

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------
    n_pass = sum(1 for s, _, _ in results if s == "PASS")
    n_info = sum(1 for s, _, _ in results if s == "INFO")
    n_fail = sum(1 for s, _, _ in results if s == "FAIL")

    print()
    print(f"Summary: PASS={n_pass} INFO={n_info} FAIL={n_fail}")

    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()