#!/usr/bin/env bash
#export_to_sqlite_from_active.sh
set -euo pipefail

# -------- Config --------
PGDB="${PGDB:-hvp}"
PGSCHEMA="${PGSCHEMA:-public}"
OUTDIR="${OUTDIR:-out_csv}"      # where CSVs go
SQLITEDB="${SQLITEDB:-out.sqlite}"

# Ensure Kerberos/GSS doesn't interfere (macOS/Homebrew default)
export PGGSSENCMODE=disable

mkdir -p "$OUTDIR"

#Add colored text for status messages
red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }

mismatch_count=0
mismatches=()

record_mismatch () {
  mismatch_count=$((mismatch_count+1))
  mismatches+=("$1")
  red "    MISMATCH: $1"
}

# -------- Helper: CREATE TABLE from CSV header (robust via Python) --------
create_table_from_csv_header() {
  # $1 = sqlite db path, $2 = table name, $3 = csv path
  python3 - "$SQLITEDB" "$1" "$2" "$3" <<'PY'
import csv, re, sqlite3, sys
_, dbpath, _dup_dbpath, tname, csvpath = sys.argv
con = sqlite3.connect(dbpath)
with open(csvpath, 'r', newline='', encoding='utf-8', errors='ignore') as f:
    reader = csv.reader(f)
    header = next(reader, None)
if header is None:
    print(f"[WARN] Empty CSV? {csvpath}", file=sys.stderr)
    sys.exit(0)

def sanitize(col):
    col = col.strip()
    col = re.sub(r'[^0-9A-Za-z_]', '_', col)
    if col == '':
        col = 'col'
    if col[0].isdigit():
        col = '_' + col
    return col

seen = {}
cols_unique = []
for c in header:
    base = sanitize(c)
    name = base
    i = 2
    while name in seen:
        name = f"{base}_{i}"
        i += 1
    seen[name] = True
    cols_unique.append(name)

cols_sql = ", ".join([f'"{c}" TEXT' for c in cols_unique])
sql = f'CREATE TABLE IF NOT EXISTS "{tname}" ({cols_sql});'
con.execute(sql)
con.commit()
con.close()
PY
}

# --- Counting helpers ---
pg_count_table () { psql -d "$PGDB" -Atc "SELECT COUNT(*) FROM ${PGSCHEMA}.\"$1\";"; }
pg_count_view  () { psql -d "$PGDB" -Atc "SELECT COUNT(*) FROM ${PGSCHEMA}.\"$1\";"; }
csv_count      () { local f="$1"; [[ -s "$f" ]] && echo $(( $(wc -l < "$f") - 1 )) || echo 0; }
sqlite_count   () { sqlite3 "$SQLITEDB" "SELECT COUNT(*) FROM \"$1\";" 2>/dev/null || echo "ERR"; }

# -------- 1) Get table & view lists --------
echo "==> Gathering tables and views from $PGDB.$PGSCHEMA"
tables=$(psql -d "$PGDB" -Atc "SELECT tablename FROM pg_tables WHERE schemaname='${PGSCHEMA}' ORDER BY tablename;")
views=$(psql -d "$PGDB" -Atc "SELECT viewname FROM pg_views  WHERE schemaname='${PGSCHEMA}' ORDER BY viewname;")

# -------- 2) Export TABLES to CSV (with counts) --------
echo "==> Exporting tables to $OUTDIR/ (and checking counts)"
for t in $tables; do
  out="${OUTDIR}/${t}.csv"
  echo "  - $t -> $out"
  psql -d "$PGDB" -v ON_ERROR_STOP=1 -c "\COPY ${PGSCHEMA}.${t} TO '${out}' WITH (FORMAT csv, HEADER true)"
  pgc=$(pg_count_table "$t")
  csc=$(csv_count "$out")
  printf "     %-22s PG:%-10s CSV:%-10s " "rows"
  if [[ "$pgc" == "$csc" ]]; then green "OK"; else record_mismatch "table $t export rows PG=$pgc vs CSV=$csc"; fi
done

# -------- 3) Export VIEW DATA (snapshots) to CSV (with counts) --------
echo "==> Exporting view snapshots to $OUTDIR/ (and checking counts)"
for v in $views; do
  out="${OUTDIR}/view_${v}.csv"
  echo "  - $v -> $out"
  psql -d "$PGDB" -v ON_ERROR_STOP=1 -c "\COPY (SELECT * FROM ${PGSCHEMA}.${v}) TO '${out}' WITH (FORMAT csv, HEADER true)"
  pgc=$(pg_count_view "$v")
  csc=$(csv_count "$out")
  printf "     %-22s PG:%-10s CSV:%-10s " "rows"
  if [[ "$pgc" == "$csc" ]]; then green "OK"; else record_mismatch "view $v export rows PG=$pgc vs CSV=$csc"; fi
done

# -------- 4) Build SQLite DB --------
echo "==> Building SQLite: $SQLITEDB"
rm -f "$SQLITEDB"
sqlite3 "$SQLITEDB" "PRAGMA journal_mode=WAL;"

# 4a) Import TABLES and verify vs PG
for t in $tables; do
  f="${OUTDIR}/${t}.csv"
  echo "  [sqlite] creating & importing table $t"
  create_table_from_csv_header "$SQLITEDB" "$t" "$f"
  sqlite3 "$SQLITEDB" <<SQL
.mode csv
.import --skip 1 "$f" "$t"
SQL
  pgc=$(pg_count_table "$t")
  slc=$(sqlite_count "$t")
  csc=$(csv_count "$f")
  printf "     %-22s PG:%-10s CSV:%-10s SQLITE:%-10s " "rows"
  if [[ "$pgc" == "$slc" && "$csc" == "$slc" ]]; then
    green "OK"
  else
    record_mismatch "table $t import rows PG=$pgc CSV=$csc SQLITE=$slc"
  fi
done

# 4b) Import VIEW snapshots as <view>_data and verify vs PG view
for v in $views; do
  f="${OUTDIR}/view_${v}.csv"
  t="${v}_data"
  echo "  [sqlite] creating & importing view snapshot table $t"
  create_table_from_csv_header "$SQLITEDB" "$t" "$f"
  sqlite3 "$SQLITEDB" <<SQL
.mode csv
.import --skip 1 "$f" "$t"
SQL
  pgc=$(pg_count_view "$v")
  slc=$(sqlite_count "$t")
  csc=$(csv_count "$f")
  printf "     %-22s PGview:%-10s CSV:%-10s SQLITE:%-10s " "rows"
  if [[ "$pgc" == "$slc" && "$csc" == "$slc" ]]; then
    green "OK"
  else
    record_mismatch "view $v import rows PGview=$pgc CSV=$csc SQLITE=$slc"
  fi
done

# 4c) Create SQLite VIEWS pointing to the *_data tables
echo "==> Creating SQLite views"
for v in $views; do
  sqlite3 "$SQLITEDB" "DROP VIEW IF EXISTS \"$v\";"
  sqlite3 "$SQLITEDB" "CREATE VIEW \"$v\" AS SELECT * FROM \"${v}_data\";"
done

# -------- 5) Summary --------
echo
if (( mismatch_count == 0 )); then
  green "All counts match. SQLite: $SQLITEDB   CSVs: $OUTDIR/"
else
  red "Completed with $mismatch_count mismatches:"
  for m in "${mismatches[@]}"; do
    red "   - $m"
  done
  exit 2
fi
