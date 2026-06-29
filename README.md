# Replication code for the LABOUR submission

This repository belongs to the paper:

**Constructing Treatment in National Minimum-Wage Reforms: Youth Employment Evidence from Spain**

The paper is submitted to **LABOUR: Review of Labour Economics and Industrial
Relations (Wiley)**. The repository is prepared as the public replication
package for the submitted version. It will be made public, completed with the
final paper citation, and updated with the published article DOI and final
journal location once the paper is published.

Until publication, the repository should be read as a transparent replication
skeleton for review and archiving. It documents the key treatment-construction
and HonestDiD steps without relying on the author's local Google Drive paths.

Repository URL:

```text
https://github.com/mlacasa/minimum-wage-bites-spain-2019
```

## Statements for Editors and Reviewers

### Code availability

The code shared in this repository covers the construction of the minimum-wage
bite measures and the R pipeline used for event-study estimation and HonestDiD
sensitivity analysis. The repository is intended for editors and reviewers of
the submitted manuscript and will be made public and updated after publication.

### Software availability

The Python stage uses:

```text
pandas
numpy
pyarrow
```

The R stage uses:

```text
fixest
HonestDiD
dplyr
readr
broom
stringr
tibble
```

The R pipeline writes `session_info.txt` to the results folder at execution
time, so the exact R version and package versions used in each replication run
are recorded with the outputs.

## What This Repository Covers

The paper studies Spain's 2019 increase in the statutory minimum wage. Because
the reform was national, treatment intensity is not directly observed as a
treated/control indicator. It is constructed from pre-reform exposure to the
incoming 2019 wage floor.

This repository focuses on the two parts of the workflow most important for
replication:

1. **Python stage:** construction of exposure measures, or bites, from
   reconstructed administrative cells.
2. **R stage:** event-study estimation and HonestDiD sensitivity analysis using
   the current R pipeline.

The raw public sources are documented in [data/README.md](data/README.md).

## Python Stage: IPF, Accounting Closure, and Bites

The empirical design combines two AEAT sources that observe different margins
of the labour market:

- **Modelo 190** gives employment and wage-bill information by territory,
  sector and age bracket, but it does not directly cross age with detailed
  salary bins.
- **AEAT salary-distribution files** give the earnings distribution in salary
  bins, but not the full age-by-sector-by-territory structure needed for the
  causal panel.

The full internal pipeline therefore reconstructs a latent table using
iterative proportional fitting (IPF). Conceptually, IPF starts from a feasible
seed table and repeatedly scales it so that it matches all observed margins.
The key accounting restrictions are:

- macroterritory-sector-year employment totals match the Modelo 190 totals;
- age margins match the published age totals;
- salary-tier margins match the reconstructed salary distribution in real 2019
  euros;
- no final latent cell contradicts the fixed support used in the design;
- the reconstructed table closes back to the observed administrative totals
  within numerical tolerance.

That closure is essential: the bites are not estimated from survey weights or
ad hoc shares, but from a latent table that is forced to respect the published
administrative margins. The public Python script in this repository starts
from that post-IPF latent cell table. It does not rerun the full raw-data
harmonisation and IPF notebooks; instead, it provides the clean, generic step
that turns the closed latent table into the panel used by R.

Script:

```text
scripts/python/prepare_bites_for_honestdid.py
```

Example:

```bash
python scripts/python/prepare_bites_for_honestdid.py \
  --latent-cells data_intermediate/nb05_causal_cell_table_employees.parquet \
  --outcome-panel data_intermediate/nb06_outcome_panel_final_18_25_2009_2023.parquet \
  --cost-table outputs_tables/nb06_bite_y_cost_2018_bin_18_25.csv \
  --out data/derived/Panel_Main_EventStudy.csv \
  --audit-out data/derived/bite_construction_audit.csv \
  --macro-col region_group_main_t3_v4 \
  --outcome-macro-col macro_label \
  --age-col age_bracket \
  --tier-col causal_tier \
  --employees-col employees_causal \
  --outcome-employees-col employees_18_25 \
  --youth-age 18_25 \
  --exposed-tiers T1_lt_085 T2_085_100_BITE
```

The script exports:

- `Panel_Main_EventStudy.csv`
- `bite_construction_audit.csv`
- a small metadata JSON file recording the input paths and bite definition

## BITE-1 and BITE-2

The paper uses two related but distinct exposure measures.

### BITE-1: Incidence Bite

BITE-1 is the preferred treatment measure. It is an incidence measure:

```text
BITE-1 = workers aged 18-25 in exposed salary tiers in 2018
         ---------------------------------------------------
         all workers aged 18-25 in 2018
```

In the current manuscript, the exposed tiers are:

```text
T1_lt_085
T2_085_100_BITE
```

BITE-1 asks how many young workers were located below or around the incoming
2019 minimum-wage threshold before the reform. It is a share, frozen in 2018,
and in the preferred design it varies effectively at the macroterritorial
level.

### BITE-2: Cost Bite

BITE-2 is a monetary shortfall measure:

```text
BITE-2 = total salary shortfall to the incoming threshold in 2018
         -------------------------------------------------------
         total wage bill in 2018
```

It uses the salary-bin distribution to approximate the wage bill required to
bring workers below the incoming annual threshold up to that threshold. BITE-2
is useful as a design diagnostic and comparison measure, but it is not treated
as the preferred causal design in the paper because it produces different
dynamics and less favourable pre-trend diagnostics.

The Python script can incorporate BITE-2 when a cost table is supplied. If no
cost table is supplied, it still constructs the BITE-1 panel and writes
`bite_y_cost_2018` as missing.

## R Stage: Current HonestDiD Pipeline

The R script implements the HonestDiD pipeline used at the current submission
stage, dated **18 June 2026**.

Script:

```text
scripts/R/run_honestdid_macro.R
```

Example:

```bash
Rscript scripts/R/run_honestdid_macro.R \
  --input data/derived/Panel_Main_EventStudy.csv \
  --outdir results/r_honestdid \
  --bite bite_y_inc_2018
```

The script does four things:

1. Reads the long panel produced by the Python stage.
2. Aggregates the macroterritory-sector panel to the macroterritorial level
   for the preferred BITE-1 design.
3. Estimates the event-study model with two-way fixed effects:

```text
log(youth employment) ~ i(rel_year, bite, ref = -1) | macroterritory + year
```

4. Applies HonestDiD relative-magnitude sensitivity analysis to:

- the first post-treatment coefficient, `rel_year = 0`;
- the average post-treatment coefficient over the observed post-treatment
  years.

The event-time convention is:

```text
2018 -> rel_year = -1  (omitted category)
2019 -> rel_year = 0   (first post-treatment year)
```

The current R script uses the installed versions available at execution time
and writes `session_info.txt` to the output folder so that the exact R and
package versions are recorded with the results. As of 18 June 2026, the
current public package references are:

- `fixest` from CRAN for two-way fixed-effects estimation;
- `HonestDiD` from the public `asheshrambachan/HonestDiD` R package repository;
- `dplyr`, `readr`, `broom`, `stringr` and `tibble` from CRAN.

Expected outputs:

```text
results/r_honestdid/
  es_macro_coefs.csv
  honestdid_macro_results.csv
  honestdid_macro_warnings.txt   # only if warnings are emitted
  event_study_macro.rds
  session_info.txt
```

## Software

Python dependencies:

```text
pandas
numpy
pyarrow
```

R dependencies:

```text
fixest
HonestDiD
dplyr
readr
broom
stringr
tibble
```

## Status

This repository is aligned with the submitted LABOUR manuscript and will be
updated after publication with:

- the final article citation;
- the final DOI;
- the permanent data/code archive link;
- any journal-requested replication-package changes.
