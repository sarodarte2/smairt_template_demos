#!/usr/bin/env bash
# build_sql_database.sh
# End-to-end setup for the PostgreSQL database and data loads.
# - Drops & recreates DB by default (wipe)
# - Applies schema.sql
# - Applies views.sql
# - Runs load_hic_wu.py to ingest Wu et al. Hi-C data (RUNS FIRST for faster iteration)
# - Runs load_gsva.py to ingest GSVA data
#
# Disable wiping with: --no-recreate
# Skip any loader with: --no-load (both) or --no-hic (just Hi-C)

set -Eeuo pipefail

# ------------------------------
# Defaults
# ------------------------------
DB_NAME="${DB_NAME:-hvp}"
DB_USER="${DB_USER:-${PGUSER:-$USER}}"
DB_HOST="${DB_HOST:-${PGHOST:-}}"
DB_PORT="${DB_PORT:-${PGPORT:-5432}}"
ADMIN_DB="${ADMIN_DB:-postgres}"  # used to run DROP DATABASE, terminate connections

SCHEMA_SQL="./sql/hvp_schema.sql"
VIEWS_SQL="./sql/views.sql"

# === GSVA defaults ===
SAMPLES="./build/resource/GSVA/GSVA_sample_metadata_5.csv"
CONTIGS="./build/resource/GSVA/GSVA_soil_viruses_genome_metadata_2.tsv"
GENES="./build/resource/GSVA/GSVA_soil_viruses_gene_metadata_4.tsv"
PROTEINS=("./build/resource/GSVA/GSVA_soil_viruses_3.faa")          # repeat --protein to add multiple
CONTIG_FASTA=("./build/resource/GSVA/GSVA_all_soil_viruses_1.fna")  # repeat --contig-fasta to add multiple
AMG="./build/resource/GSVA/AMG_withCAT_new.txt"                     # optional

# === Hi-C / Wu defaults ===
HIC_BASE="./build/resource/HiC_Wu"
HIC_FNA="${HIC_BASE}/viral_contigs.fna"
HIC_TSV="${HIC_BASE}/viral_host_associations_HiC.tsv"
HIC_MAGS="${HIC_BASE}/MAGs_dir"

RECREATE_DB=1     # wipe by default
APPLY_VIEWS=1
RUN_LOAD=1
RUN_HIC=1         # run Hi-C loader by default
KEEP_STAGING=0

# ------------------------------
# Helpers
# ------------------------------
usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Database:
  --db-name NAME             Database name (default: ${DB_NAME})
  --db-user USER             Database user (default: ${DB_USER})
  --db-host HOST             Database host (default: ${DB_HOST:-<socket>})
  --db-port PORT             Database port (default: ${DB_PORT})
  --admin-db NAME            DB to connect to for admin ops (drop/terminate), default: ${ADMIN_DB}
  --no-recreate              Do not drop & recreate DB (default wipes on each run)

SQL files:
  --schema PATH              Path to schema.sql (default: ${SCHEMA_SQL})
  --views PATH               Path to views.sql (default: ${VIEWS_SQL})
  --no-views                 Skip applying views.sql

GSVA data (runs after Hi-C unless --no-load):
  --samples PATH             GSVA_sample_metadata_5.csv
  --contigs PATH             GSVA_soil_viruses_genome_metadata_2.tsv
  --genes PATH               GSVA_soil_viruses_gene_metadata_4.tsv
  --protein PATH             Protein FASTA (.faa). Repeat for multiple files.
  --contig-fasta PATH        Contig nucleotide FASTA (.fna). Repeat for multiple files.
  --amg PATH                 AMG_withCAT_new.txt

Hi-C / Wu data (runs first unless --no-hic or --no-load):
  --hic-base PATH            Base directory (default: ${HIC_BASE})
  --hic-fna PATH             viral_contigs.fna (default: from --hic-base)
  --hic-tsv PATH             viral_host_associations_HiC.tsv (default: from --hic-base)
  --hic-mags PATH            MAGs_dir (optional; default: from --hic-base)
  --no-hic                   Skip running the Hi-C loader

Control:
  --no-load                  Skip running loaders (Hi-C + GSVA)
  --keep-staging             Keep staging tables after load (default: drop)

Other:
  -h | --help                Show help

Env: PGPASSWORD/PGUSER/PGHOST/PGPORT honored by psql/createdb.
EOF
}

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: '$1' not found" >&2; exit 1; }; }

# ------------------------------
# Parse args
# ------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    # DB
    --db-name)      DB_NAME="$2"; shift 2 ;;
    --db-user)      DB_USER="$2"; shift 2 ;;
    --db-host)      DB_HOST="$2"; shift 2 ;;
    --db-port)      DB_PORT="$2"; shift 2 ;;
    --admin-db)     ADMIN_DB="$2"; shift 2 ;;
    --no-recreate)  RECREATE_DB=0; shift ;;

    # SQL
    --schema)       SCHEMA_SQL="$2"; shift 2 ;;
    --views)        VIEWS_SQL="$2"; shift 2 ;;
    --no-views)     APPLY_VIEWS=0; shift ;;

    # GSVA
    --samples)      SAMPLES="$2"; shift 2 ;;
    --contigs)      CONTIGS="$2"; shift 2 ;;
    --genes)        GENES="$2"; shift 2 ;;
    --protein)      PROTEINS+=("$2"); shift 2 ;;
    --contig-fasta) CONTIG_FASTA+=("$2"); shift 2 ;;
    --amg)          AMG="$2"; shift 2 ;;

    # Hi-C / Wu
    --hic-base)     HIC_BASE="$2"; HIC_FNA="${HIC_BASE}/viral_contigs.fna"; HIC_TSV="${HIC_BASE}/viral_host_associations_HiC.tsv"; HIC_MAGS="${HIC_BASE}/MAGs_dir"; shift 2 ;;
    --hic-fna)      HIC_FNA="$2"; shift 2 ;;
    --hic-tsv)      HIC_TSV="$2"; shift 2 ;;
    --hic-mags)     HIC_MAGS="$2"; shift 2 ;;
    --no-hic)       RUN_HIC=0; shift ;;

    # Control
    --no-load)      RUN_LOAD=0; shift ;;
    --keep-staging) KEEP_STAGING=1; shift ;;

    -h|--help)      usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

# ------------------------------
# Validate tools
# ------------------------------
need psql
need createdb
need python3

if ! python3 - <<'PY' >/dev/null 2>&1
import pandas, psycopg2  # noqa
PY
then
  echo "ERROR: Missing python deps. Install: pip install pandas psycopg2-binary" >&2
  exit 1
fi

# Loader scripts
LOADER_GSVA="./load_gsva.py"
[[ -f "$LOADER_GSVA" ]] || { echo "ERROR: loader not found at $LOADER_GSVA" >&2; exit 1; }
chmod +x "$LOADER_GSVA" || true

LOADER_HIC="./load_hic_wu.py"
if (( RUN_HIC )) && (( RUN_LOAD )); then
  [[ -f "$LOADER_HIC" ]] || { echo "ERROR: Hi-C loader not found at $LOADER_HIC" >&2; exit 1; }
  chmod +x "$LOADER_HIC" || true
fi

# ------------------------------
# DSN
# ------------------------------
DSN="dbname=${DB_NAME} user=${DB_USER}"
[[ -n "${DB_HOST}" ]] && DSN="${DSN} host=${DB_HOST}"
[[ -n "${DB_PORT}" ]] && DSN="${DSN} port=${DB_PORT}"
DSN="${DSN} gssencmode=disable"

echo "==> Using DSN: ${DSN}"

# Convenience arg bundles for psql/createdb (allow empty -h -> local socket)
PSQL_ADMIN_ARGS=(-h "${DB_HOST:-$DB_HOST}" -U "${DB_USER}" -p "${DB_PORT}" -d "${ADMIN_DB}")
PSQL_DB_ARGS=(-h "${DB_HOST:-$DB_HOST}" -U "${DB_USER}" -p "${DB_PORT}" -d "${DB_NAME}")

# ------------------------------
# (Re)create DB
# ------------------------------
if (( RECREATE_DB )); then
  echo "==> Recreating database '${DB_NAME}' (terminate connections, drop, create)"
  # terminate connections (ok if DB doesn't exist)
  psql -v ON_ERROR_STOP=0 "${PSQL_ADMIN_ARGS[@]}" -c \
    "SELECT pg_terminate_backend(pid)
     FROM pg_stat_activity
     WHERE datname='${DB_NAME}' AND pid <> pg_backend_pid();"
  # drop & create
  psql -v ON_ERROR_STOP=1 "${PSQL_ADMIN_ARGS[@]}" -c "DROP DATABASE IF EXISTS ${DB_NAME};"
  createdb -h "${DB_HOST:-$DB_HOST}" -U "${DB_USER}" -p "${DB_PORT}" "${DB_NAME}"
else
  echo "==> (no-recreate) Ensuring database '${DB_NAME}' exists"
  if ! psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "${DB_NAME}"; then
    createdb -h "${DB_HOST:-$DB_HOST}" -U "${DB_USER}" -p "${DB_PORT}" "${DB_NAME}"
  fi
fi

# ------------------------------
# Apply schema
# ------------------------------
echo "==> Applying schema: ${SCHEMA_SQL}"
psql -v ON_ERROR_STOP=1 "${PSQL_DB_ARGS[@]}" -f "${SCHEMA_SQL}"

echo "==> Ensuring required extensions (ltree)"
psql -v ON_ERROR_STOP=1 "${PSQL_DB_ARGS[@]}" -c "CREATE EXTENSION IF NOT EXISTS ltree;"

# ------------------------------
# Apply views
# ------------------------------
if (( APPLY_VIEWS )); then
  echo "==> Applying views: ${VIEWS_SQL}"
  psql -v ON_ERROR_STOP=1 "${PSQL_DB_ARGS[@]}" -f "${VIEWS_SQL}"
fi

# ==================================================
# Run Hi-C / Wu loader FIRST (for faster iteration)
# ==================================================
if (( RUN_LOAD )) && (( RUN_HIC )); then
  # Validate Hi-C inputs now
  [[ -f "$HIC_FNA" ]] || { echo "ERROR: Hi-C FASTA not found: $HIC_FNA" >&2; exit 1; }
  [[ -f "$HIC_TSV" ]] || { echo "ERROR: Hi-C TSV not found: $HIC_TSV" >&2; exit 1; }
  [[ -d "$HIC_MAGS" ]] || echo "WARN: Hi-C MAGs dir not found (optional): $HIC_MAGS" >&2

  echo "==> Running loader (load_hic_wu.py)"
  HIC_ARGS=( --dsn "$DSN" --base-dir "$HIC_BASE" )
  [[ -n "${HIC_FNA:-}"  ]] && HIC_ARGS+=( --fna "$HIC_FNA" )
  [[ -n "${HIC_TSV:-}"  ]] && HIC_ARGS+=( --hic-tsv "$HIC_TSV" )
  [[ -n "${HIC_MAGS:-}" ]] && [[ -d "$HIC_MAGS" ]] && HIC_ARGS+=( --mags-dir "$HIC_MAGS" )
  (( KEEP_STAGING )) && HIC_ARGS+=( --keep-staging )

  echo "    - base-dir:      $HIC_BASE"
  echo "    - fna:           $HIC_FNA"
  echo "    - tsv:           $HIC_TSV"
  [[ -d "$HIC_MAGS" ]] && echo "    - mags-dir:      $HIC_MAGS" || true
  (( KEEP_STAGING )) && echo "    - keep-staging:  yes"

  python3 "$LOADER_HIC" "${HIC_ARGS[@]}"
fi

# ------------------------------
# Run GSVA loader (after Hi-C)
# ------------------------------
if (( RUN_LOAD )); then
  # Validate GSVA inputs now (lazy validation to allow quick Hi-C-only runs)
  [[ -n "$SAMPLES" && -f "$SAMPLES" ]] || { echo "ERROR: --samples required (file not found: $SAMPLES)" >&2; exit 1; }
  [[ -n "$CONTIGS" && -f "$CONTIGS" ]] || { echo "ERROR: --contigs required (file not found: $CONTIGS)" >&2; exit 1; }
  [[ -n "$GENES"   && -f "$GENES"   ]] || { echo "ERROR: --genes required (file not found: $GENES)" >&2; exit 1; }

  echo "==> Running loader (load_gsva.py)"
  PY_ARGS=( --dsn "$DSN" --samples "$SAMPLES" --contigs "$CONTIGS" --genes "$GENES" )
  for f in "${PROTEINS[@]:-}"; do [[ -n "$f" ]] && PY_ARGS+=( --proteins "$f" ); done
  for f in "${CONTIG_FASTA[@]:-}"; do [[ -n "$f" ]] && PY_ARGS+=( --contig-fasta "$f" ); done
  [[ -n "${AMG:-}" ]] && [[ -f "$AMG" ]] && PY_ARGS+=( --amg "$AMG" )
  (( KEEP_STAGING )) && PY_ARGS+=( --keep-staging )

  echo "    - samples:       $SAMPLES"
  echo "    - contigs:       $CONTIGS"
  echo "    - genes:         $GENES"
  ((${#PROTEINS[@]})) && printf "    - proteins:      %s\n" "${PROTEINS[@]}"
  ((${#CONTIG_FASTA[@]})) && printf "    - contig-fasta:  %s\n" "${CONTIG_FASTA[@]}"
  [[ -n "${AMG:-}" ]] && [[ -f "$AMG" ]] && echo "    - amg:           $AMG"
  (( KEEP_STAGING )) && echo "    - keep-staging:  yes"

  python3 "$LOADER_GSVA" "${PY_ARGS[@]}"
fi

# ------------------------------
# Post-load: propagate contig→host to avg_host
# (runs AFTER both loaders so all genes + host links exist)
# # ------------------------------
# if (( RUN_LOAD )); then
#   echo "==> Propagating contig→host links to avg_host (cross-resource)"
#   psql -v ON_ERROR_STOP=1 "${PSQL_DB_ARGS[@]}" -c "
#     INSERT INTO avg_host (avg_id, host_id, method_id, resource_id)
#     SELECT g.avg_id, vch.host_id, vch.method_id, vch.resource_id
#     FROM viral_contig_host vch
#     JOIN avg_gene g ON g.contig_id = vch.contig_id
#     ON CONFLICT (avg_id, host_id, resource_id, method_id) DO NOTHING;
#   "
# fi

# ------------------------------
# Post-load summary
# ------------------------------
echo "==> Brief counts:"
psql "${PSQL_DB_ARGS[@]}" -v ON_ERROR_STOP=0 -c "
  SELECT 'sample' tbl, count(*) FROM sample
  UNION ALL SELECT 'metagenome', count(*) FROM metagenome
  UNION ALL SELECT 'viral_contig', count(*) FROM viral_contig
  UNION ALL SELECT 'viral_contig_sequence', count(*) FROM viral_contig_sequence
  UNION ALL SELECT 'avg_gene', count(*) FROM avg_gene
  UNION ALL SELECT 'avg_sequence', count(*) FROM avg_sequence
  UNION ALL SELECT 'avg_function', count(*) FROM avg_function
  UNION ALL SELECT 'avg_evidence', count(*) FROM avg_evidence
  UNION ALL SELECT 'virus_taxon', count(*) FROM virus_taxon
  UNION ALL SELECT 'viral_contig_host', count(*) FROM viral_contig_host
  UNION ALL SELECT 'avg_host', count(*) FROM avg_host;
" || true

echo '==> Done.'