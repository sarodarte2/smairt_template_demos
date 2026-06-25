# Demo: SMAIRT with the Human Virome Project (HVP) Database

A step-by-step demo for using **SMAIRT** with the HVP soil-virome PostgreSQL
database and an AI assistant (**Zoo Code**).

**You are given:** the question, the background context, and the **method to build
the database** (the loaders + data in this folder).  

**You build:** the queries and analysis that answer the question using SMAIRT.
There are **no solution scripts here**; building the database is provided so you
spend your SMAIRT iterations on the science, not on data wrangling.

> New to AI assistants? Read [`../USING_ZOO_CODE.md`](../USING_ZOO_CODE.md) first
> (install, sign in, attach files, approve edits).

---

## The question

How do phage-host interaction patterns differ between **CRISPR-predicted** links and
**Hi-C** experimental links in the integrated soil virome database? Specifically, how
do link counts, unique viral contigs, and unique hosts compare across evidence
methods, and what does that imply about the biology each method captures?

Full context, schema, and data caveats are in
[`background/01_initial_question.md`](background/01_initial_question.md).

### Key terms

- **Phage:** a virus that infects bacteria. **Host:** the bacterium it infects.
- **Contig:** a stretch of assembled DNA; here, a viral genome fragment.
- **Phage-host link:** evidence that a phage infects a particular host.
- **CRISPR-spacer link:** inferred from a bacterium's CRISPR "immune memory". It
  records *past* infections (broad but indirect).
- **Hi-C link:** an experimental method that captures phage + host DNA physically
  together in one cell, which is evidence of an *active* infection at sampling time.
- **`viral_contig_host`:** the table with one row per phage-host link; the
  **`evidence_method`** table names the method that produced each link.

---

## What you'll set up

1. A running PostgreSQL database with GSVA + Wu Hi-C soil-virome data.
2. A SMAIRT project scaffolded from the cookiecutter template.
3. Zoo Code configured with the PNNL LLM endpoint.
4. Your `background/01_initial_question.md` seeded with full HVP context, ready
   for your first hypothesis.

## Prerequisites

- **PostgreSQL** 14+ (on your workstation or a shared server)
- **Python 3.10+** with `pip`
- **VS Code** + **Git**
- **Zoo Code** (the AI assistant). See [`../USING_ZOO_CODE.md`](../USING_ZOO_CODE.md)

> The database build files and source data are already in **this folder**
> (`build/`, `sql/`, `load_*.py`, `build_sql_database.sh`). No separate download
> is needed.

---

## Step 0: Set up your environment

From this folder (`hvp/`), create a virtual environment and install the
requirements (this provides `cookiecutter` plus the database-build libraries):

```bash
python3 -m venv .venv
source .venv/bin/activate                # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt          # cookiecutter, pandas, psycopg2-binary, openpyxl
```

> `command not found: cookiecutter` later means this step was skipped or your
> venv isn't active.
>
> Windows users: if PowerShell blocks activation, run
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal,
> then try `.venv\Scripts\Activate.ps1` again. In Command Prompt, use
> `.venv\Scripts\activate.bat`.

---

## Step 1: Build the database

### 1a. Ensure PostgreSQL is running

```bash
psql --version
pg_isready
```

If PostgreSQL isn't installed (macOS example):

```bash
brew --version    # install Homebrew first if needed:
# /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install postgresql@16
brew services start postgresql@16
psql --version && pg_isready
```

Windows users: PostgreSQL is usually easiest with the official installer from
https://www.postgresql.org/download/windows/. During installation, keep track of
which port and password you choose. If `psql` is not found afterward, open the
**SQL Shell (psql)** app from the Start menu or add PostgreSQL's `bin` directory
to your PATH.

### 1b. Download the GSVA resource files

The large GSVA source files are hosted on Figshare instead of stored in Git. Once
this Figshare item is published, download the files before building the database
(from this folder, venv active):

```bash
bash download_hvp_gsva_resources.sh
```

The script downloads Figshare article `32600796` into
`build/resource/GSVA/_figshare_downloads/`, extracts archives if needed, and
places the database inputs in `build/resource/GSVA/`. It checks for the files
expected by the database loader, including
`build/resource/GSVA/GSVA_all_soil_viruses_1.fna`,
`build/resource/GSVA/GSVA_soil_viruses_3.faa`,
`build/resource/GSVA/GSVA_soil_viruses_gene_metadata_4.tsv`, and
`build/resource/GSVA/AMG_withCAT_new.txt`.

If the Figshare article ID changes after publication, run:

```bash
FIGSHARE_ARTICLE_ID=<published_article_id> bash download_hvp_gsva_resources.sh
```

### 1c. Run the build (from this folder, venv active)

```bash
bash build_sql_database.sh
```

This single command will:

1. Drop and recreate the `hvp` database.
2. Apply the schema (`sql/hvp_schema.sql`) and views (`sql/views.sql`).
3. Run `load_hic_wu.py` (Wu Hi-C soil phage-host data).
4. Run `load_gsva.py` (Global Soil Virus Atlas: contigs, genes, proteins,
   taxonomy, hosts, AMGs).

The full build takes ~5 minutes; you'll see per-stage progress.

### 1d. Verify the build

At the end the script prints summary counts. You should see something like:

```
          tbl          |  count
-----------------------+---------
 virus_taxon           |      93
 avg_host              |       0
 sample                |    2960
 metagenome            |    2960
 viral_contig_host     |    1856
 viral_contig          |   51398
 viral_contig_sequence |   51398
 avg_function          | 1267490
 avg_gene              | 1432147
 avg_evidence          |  924537
 avg_sequence          | 1432147
```

Or check interactively:

```bash
psql -d hvp -c "SELECT 'contigs' AS what, count(*) FROM viral_contig
UNION ALL SELECT 'genes', count(*) FROM avg_gene
UNION ALL SELECT 'hosts', count(*) FROM viral_contig_host;"
```

> **Data note:** `avg_gene` (1,432,147 rows) is ALL predicted GSVA viral genes,
> not just AMGs. The AMG-CAT-labelled subset (~924,537, function terms
> `AMG_cat0` to `AMG_cat5`) is broader than the paper's filtered AMG set.
> `avg_host` is 0 because host links live at the contig level
> (`viral_contig_host`), not the gene level. Extending them could be part of your
> analysis.

<details>
<summary>Extra build options (you can usually ignore)</summary>

```bash
DB_NAME=my_hvp bash build_sql_database.sh   # different database name
bash build_sql_database.sh --no-recreate    # keep data, re-apply schema
bash build_sql_database.sh --no-hic         # GSVA only
bash build_sql_database.sh --no-load        # schema only, no data
bash build_sql_database.sh --keep-staging   # keep staging tables for debugging
```
</details>

No PostgreSQL available? Use `export_to_sqlite_from_active.sh` to produce a
portable SQLite snapshot, and point your analysis scripts at that instead.

---

## Step 2: Create your SMAIRT project

From this folder (venv active):

```bash
cookiecutter https://github.com/biodataganache/smairt-template.git
```

Cookiecutter asks a series of questions. If you've run it before you may first
see `Is it okay to delete and re-download it? [y/n] (y):`. Press **Enter**. For
the **Select** prompts, type the **number** (not the word). **Suggested answers:**

| Prompt | Suggested answer |
|--------|------------------|
| project_name | `HVP Phage Host` |
| project_slug | press Enter (auto) |
| author_name | your name |
| author_email | your email (or Enter) |
| description | `CRISPR vs Hi-C phage-host links` |
| project_mode | `1` (standard) |
| workflow_mode | `1` (ide_native) |
| initial_research_question | `How do phage-host interaction networks differ between CRISPR-predicted and Hi-C experimental evidence?` |
| domain | `3` (computational_biology) |
| ai_tool | `1` (roo_zoo / Zoo Code) |
| include_example_project | `1` (no) |
| starting_phase | `3` (real) |
| license | `1` (MIT) |
| create_git_repo | `1` (yes) |

This creates a folder named after your project_slug (e.g. `hvp_phage_host/`).

### Seed the HVP background context

```bash
cp background/01_initial_question.md hvp_phage_host/background/01_initial_question.md
```

This file gives your AI assistant the full picture of the database, including
tables, data sources, known issues, and the question/hypothesis. It can then help
you write meaningful queries from the start.

---

## Step 3: Set up Zoo Code (the AI assistant)

Full details in [`../USING_ZOO_CODE.md`](../USING_ZOO_CODE.md). In short:

1. Install **Zoo Code** from the VS Code Extensions panel (`Cmd+Shift+X` on Mac,
   `Ctrl+Shift+X` on Windows).
2. Open its settings → **API Provider: OpenAI Compatible**.
3. **API Key:** create a PNNL Birthright API key at https://ai-incubator-depot.pnnl.gov/.
4. **API Base URL:** `https://ai-incubator-api.pnnl.gov`
5. **Model:** try `gpt-5-birthright` first; if your key does not show it, use
   `gpt-5.5-project`.

> **Important URL check:** the `depot` URL is only for creating the API key. The
> API Base URL field must be `https://ai-incubator-api.pnnl.gov`, not the `depot`
> website.
>
> **Markdown preview tip:** press `Cmd+Shift+V` on Mac or `Ctrl+Shift+V` on
> Windows to render this file in VS Code.

**Test the connection** in the Zoo Code chat:

```text
What tables are in my hvp PostgreSQL database? Give me the SQL to list them,
formatted as: psql -d hvp -c "{SQL}"
```

A sensible reply means you're connected.

---

## Step 4: Prime the assistant

Open your project folder in VS Code (**File > Open Folder...** >
`hvp_phage_host/`). In the Zoo Code chat, paste this direct prompt:

```text
I'm starting a SMAIRT project to answer the question in
background/01_initial_question.md, using a PostgreSQL database named "hvp" that
I've already built. Please read these files before doing any work:
1. prompts/AI_CONTEXT.md
2. prompts/CODE_CONVENTIONS.md
3. background/01_initial_question.md

Follow the SMAIRT workflow described there: numbered scripts, output to console +
results/logs/, and a pasted-output comment block at the end of each script. The
full schema is in the background file. Don't write code yet. First summarize the
question and propose an analysis to compare the evidence methods.
```

Read the reply and decide whether the proposed plan is reasonable before moving on.

---

## Step 5: Run the SMAIRT loop one step at a time

**Record, then iterate.** After key runs:
1. Paste the output into the script's comment block (the breadcrumb trail).
2. Add interpretation in `analysis/ANALYSIS_01.md`: what did you learn? Was
   the hypothesis supported?
3. Log your prompts in `prompts/session_log.md`.
4. Record your key judgment call in `prompts/intellectual_contribution.md`.
5. Write the next step. It feeds your next hypothesis.

---

## Quick reference

### Connect from Python
```python
import psycopg2
conn = psycopg2.connect("dbname=hvp user=YOUR_USER gssencmode=disable")
cur = conn.cursor()
cur.execute("SELECT count(*) FROM viral_contig")
print(cur.fetchone()[0])
conn.close()
```

### Key tables
| Table | What it contains |
|-------|-----------------|
| `viral_contig` | 51K+ viral contigs (GSVA + Wu) |
| `avg_gene` | 1.4M viral genes (GSVA only) |
| `viral_contig_host` | phage-host links (CRISPR + Hi-C) |
| `evidence_method` | names each linking method |
| `host` | bacterial/archaeal host MAGs |
| `virus_taxon` | viral taxonomy hierarchy |
| `sample` | 2,960 soil samples (GPS + environment) |

### SMAIRT cheat sheet
| Action | Command |
|--------|---------|
| New script | `python scripts/new_script.py` |
| Compile context for AI | `python scripts/compile_for_ai.py` |
| Record hypothesis | edit `hypotheses/HYPOTHESIS_01.md` |
| Track your insight | edit `prompts/intellectual_contribution.md` |

---

## What "done" looks like

A first-pass result comparing the evidence methods, an interpretation that
respects the method-bias caveat (the two methods see different biology, so raw
counts aren't directly comparable), and a logged next step. The work should be
reproducible from your breadcrumb trail.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `command not found: cookiecutter` | venv not active or Step 0 skipped. `source .venv/bin/activate` then `pip install -r requirements.txt`. |
| `No such file or directory: .../.venv/bin/...` | The venv was deleted/moved. Recreate it (Step 0 lines). |
| Build: `psql: command not found` | PostgreSQL isn't installed/on PATH (see Step 1a). |
| Build: `role "..." does not exist` | Run `DB_USER=$USER bash build_sql_database.sh`. |
| Build: `database "hvp" already exists` / can't drop | Another session is connected: `psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='hvp' AND pid <> pg_backend_pid();"` then rebuild. |
| `psycopg2` import error | `pip install psycopg2-binary` (in the active venv). |
| `openpyxl` missing (Wu .xlsx) | `pip install openpyxl`. |
| Script connects but returns 0 rows | The DB wasn't loaded; re-run `bash build_sql_database.sh` and check the counts. |
| No PostgreSQL at all | Run `export_to_sqlite_from_active.sh` and point the script at the SQLite file. |
| AI counted raw rows | Tell it to use `COUNT(DISTINCT ...)` and `GROUP BY` the method name. |

### Zoo Code is stuck (an error a retry won't fix)

Don't keep retrying. **Start a fresh task/chat** (the `+` in Zoo Code) and
re-prime from your breadcrumb trail. Your files hold the context, and your `hvp`
database is still built on disk.

1. Keep your project folder open in the new task.
2. Attach `prompts/AI_CONTEXT.md`, `prompts/CODE_CONVENTIONS.md`, and
   `background/01_initial_question.md`, then paste:

   ```text
   I'm resuming a SMAIRT project (question in background/01_initial_question.md)
   after my previous AI session got stuck. The PostgreSQL database "hvp" is
   already built. Please read AI_CONTEXT.md and CODE_CONVENTIONS.md and follow the
   SMAIRT workflow. To catch up, read my existing files:
   - experiments/ (numbered scripts, output pasted at the bottom)
   - results/logs/ (run outputs)
   - analysis/ANALYSIS_01.md (conclusions so far)
   Summarize where the project stands and the next step. Don't rewrite working
   code. Continue from here.
   ```
   Tip: if it exists, run `python scripts/compile_for_ai.py` and paste its output
   to hand over the whole trail at once.

---

## Next steps

- Read `docs/SMAIRT_PHILOSOPHY.md` in your generated project for the framework.
- Explore the schema with `psql -d hvp`.
- Review `background/01_initial_question.md` for suggested research directions.
- Start your next hypothesis, experiment, results, and interpretation cycle.
