# HVP Viromics Database Pipeline

### 1. Overview
________________________________
This repository contains a suite of scripts to build, populate, and manage a PostgreSQL database designed for hosting integrated host-virus and viromics data. The pipeline is designed to be robust and repeatable, providing a complete end-to-end solution for data ingestion and subsequent analysis or distribution.  

The core functionalities include:  
- **Database Creation**: Automatically sets up a PostgreSQL database from a detailed schema (hvp_schema.sql), including tables, custom types, functions, and indexes.  
- **Data Ingestion**: Features two Python loaders for ingesting multi-file datasets. The primary loaders included are for:  
Global Soil Viromes (GSVA): Loads samples, metagenomes, viral contigs, gene predictions, protein sequences, taxonomies, predicted hosts, functional annotations (PFAM, CAZy, KEGG), and contig clusters (vOTU, genus, family).  
Wu et al. Hi-C Data: Ingests viral-host association data derived from Hi-C experiments using load_hic_wu.py.  
- **Data Denormalization**: Applies a set of SQL views (views.sql) to provide convenient, pre-joined, and user-friendly tables for querying and analysis.  
- **Portability**: Includes a utility to export the entire populated PostgreSQL database into a portable, single-file SQLite database and a collection of CSV files, perfect for sharing or offline analysis.  
The system is orchestrated by a main build_sql_database.sh script that handles the entire setup process, from database creation to running the data loaders.  

### 2. Prerequisites & Installation
________________________________
Before running any scripts, you must have the following software installed and available in your system's PATH.  
  
**Software Dependencies**:  
1) **PostgreSQL**: A running instance of PostgreSQL is required. You also need the client command-line tools:  
  - `psql`: The interactive terminal for PostgreSQL.    
  - `createdb`: The command to create a new database.  
2) **Bash Shell**: The main scripts are written in Bash and require a compatible shell (standard on Linux and macOS).  
3) **Python 3**: The data loaders are written in Python 3.  
4) **SQLite 3**: The command-line tool for SQLite is needed for the export script.  
  
**Python Libraries**:  
The Python data loaders depend on a couple key libraries. You can install them using pip:
```
pip install pandas psycopg2-binary
```

`pandas`: Used for efficient parsing and manipulation of large CSV and TSV data files.  
`psycopg2-binary`: The most popular PostgreSQL database adapter for Python.  

### 3. Directory Structure
________________________________
The scripts expect a specific layout for data and SQL files. You should arrange your project directory as follows:
```
.
├── build_sql_database.sh         # Main build script
├── export_to_sqlite_from_active.sh # Export script
├── load_gsva.py                  # Python loader for GSVA data
├── load_hic_wu.py                # Python loader for Hi-C data
│
├── sql/
│   ├── hvp_schema.sql            # Core database schema
│   └── views.sql                 # SQL views for analysis
│
└── build/
    └── resource/
        ├── GSVA/
        │   ├── GSVA_sample_metadata_5.csv
        │   ├── GSVA_soil_viruses_genome_metadata_2.tsv
        │   ├── GSVA_soil_viruses_gene_metadata_4.tsv
        │   ├── GSVA_soil_viruses_3.faa
        │   ├── GSVA_all_soil_viruses_1.fna
        │   └── AMG_withCAT_new.txt
        │
        └── HiC_Wu/
            ├── viral_contigs.fna
            ├── viral_host_associations_HiC.tsv
            ├── wu_hiC_supp_1.xlsx
            ├── wu_hiC_supp_2.xlsx
            ├── wu_hiC_supp_3.xlsx
            ├── wu_hiC_supp_4.xlsx
            ├── wu_hiC_supp_5.xlsx
            ├── wu_hiC_supp_6.xlsx
            ├── wu_hiC_supp_7.xlsx
            ├── wu_hiC_supp_8.xlsx
            ├── wu_hiC_supp_9.xlsx
            └── MAGs_dir/
                └── ...
```

### 4. Workflow & Usage
________________________________
The typical workflow involves two main steps: building the primary PostgreSQL database and optionally exporting it to SQLite.  

**Step 1**: Build and Populate the PostgreSQL Database. 
The `build_sql_database.sh` script is the main entry point for this process. It handles everything from creating the database to running the data loaders.  
  
**Default Execution** 
By default, the script will perform a "clean build": it completely drops the database if it exists, recreates it, applies the schema, and runs all data   loaders.  
To run with default settings (assuming your PostgreSQL user is your system user and you can connect locally):  
```
bash ./build_sql_database.sh
```

This command will:  
- Drop and recreate a database named hvp.  
- Apply the schema from `./sql/hvp_schema.sql`.  
- Apply the views from `./sql/views.sql`.  
- Run `load_hic_wu.py` with default data paths.  
- Run `load_gsva.py` with default data paths.  

**Step 2**: Export the Database to SQLite and CSV 
After successfully populating the PostgreSQL database, you can create a portable snapshot using the export_to_sqlite_from_active.sh script.  

**Default Execution** 
This script reads from the PostgreSQL database and writes to an out_csv/ directory and an out.sqlite file.  
```
bash ./export_to_sqlite_from_active.sh
```

This will:
Connect to the hvp database in PostgreSQL.  
Create an out_csv/ directory.  
Export every table and view into its own CSV file inside out_csv/.  
Create a new SQLite database named out.sqlite.  
Import all the data from the CSVs into the SQLite database.  
Perform row count validation at each step to ensure consistency.  

**Configuration via Environment Variables** 
You can control the script's behavior by setting these environment variables:  
`PGDB`: The name of the PostgreSQL database to read from (default: hvp).  
`OUTDIR`: The directory to save CSV files to (default: out_csv).  
`SQLITEDB`: The path for the output SQLite database file (default: out.sqlite).  
Example:
```
PGDB="hvp_prod" OUTDIR="./prod_export" SQLITEDB="hvp_prod.sqlite" ./export_to_sqlite_from_active.sh
```

### 5. Querying the Data
________________________________

Once the database is populated, you can connect to it and run SQL queries. The provided views (v_sample_overview, v_contig_overview, etc.) are the easiest way to start exploring the data.  
  
Connect to the database with:  
```
psql -d hvp
```

You can then run queries like:
```
SELECT * FROM v_sample_overview LIMIT 10;
```


### 6. Viewing the SQLite Database
________________________________

For a more visual way to explore the database, you can use a graphical tool like DB Browser for SQLite. This is especially useful for browsing tables without writing SQL.  

1) Download and Install

- Go to the official website: https://sqlitebrowser.org/
- Download and install the version for your operating system (Windows, macOS, or Linux).

2) Load the Database File

- Launch DB Browser for SQLite.
- Click the Open Database button, navigate to your project directory, and select the out.sqlite file.

3) Browse Data

- Once loaded, click on the Browse Data tab.
- Use the "Table" dropdown menu to select any table (e.g., viral_contig) or view (e.g., v_contig_overview) to see its contents in a spreadsheet format.

4) Execute SQL

- Click on the Execute SQL tab.
- Type your SQL query into the top panel.
- Click the "Execute" button (a blue "play" icon) to run the query. The results will appear in the panel below.