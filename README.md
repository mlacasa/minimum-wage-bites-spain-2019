# Data notes

This project uses public, micro-aggregated data. The public repository should
not include local paths or unpublished intermediate files unless the final
replication package explicitly archives them.

## Public data sources

### AEAT Modelo 190

Annual withholding declarations and labour-income tabulations.

URL:

```text
https://sede.agenciatributaria.gob.es/Sede/datosabiertos/catalogo/hacienda/Estadistica-Retenciones-Ingresos-Cuenta-Modelo-190.html
```

Role in the pipeline:

- employment by year, territory, sector and age bracket;
- wage-bill totals used as denominator information;
- construction of the outcome panel for workers aged 18-25.

### AEAT salary distribution

Salary distribution by sex and salary bracket from personal income-tax
statistics.

URL:

```text
https://sede.agenciatributaria.gob.es/Sede/datosabiertos/catalogo/hacienda/Estadistica-Distribucion-Salarios.html
```

Role in the pipeline:

- annual wage-bin distribution;
- reconstruction of exposure around the incoming 2019 minimum-wage threshold;
- construction of cost-based bite inputs.

### INE CPI

Consumer price index used to express annual thresholds in 2019 euros.

URL:

```text
https://www.ine.es/
```

## Minimal input contract for Python

The script `scripts/python/prepare_bites_for_honestdid.py` expects two required
inputs and one optional input.

### 1. Latent cells

One row per:

```text
year x macroterritory x sector x age bracket x salary tier
```

Required variables, with configurable names:

| Concept | Default column |
|---|---|
| Year | `year` |
| Macroterritory | `macro_label` |
| Sector code | `sector_code` |
| Sector name | `sector_name` |
| Age bracket | `age_bracket` |
| Salary tier | `salary_tier` |
| Employees | `employees` |

For the current project outputs, the corresponding columns are:

| Concept | Project column |
|---|---|
| Macroterritory | `region_group_main_t3_v4` |
| Salary tier | `causal_tier` |
| Employees | `employees_causal` |

### 2. Outcome panel

One row per:

```text
year x macroterritory x sector
```

Required variables, with configurable names:

| Concept | Default column |
|---|---|
| Year | `year` |
| Macro code | `macro_code` |
| Macro label | `macro_label` |
| Sector code | `sector_code` |
| Sector name | `sector_name` |
| Youth employment | `employees_youth` |

If `ln_employees_youth` is absent, it is computed as the natural logarithm of
positive youth employment.

### 3. Optional cost table

One row per baseline macroterritory-sector unit. This table can contain either:

- `bite_y_cost_2018`, already computed; or
- `shortfall_cost_total_bin_2018` and `salary_amount_total_2018`, from which
  the script computes `bite_y_cost_2018`.

The cost table is optional because the preferred manuscript design uses the
incidence bite. If omitted, the script writes `bite_y_cost_2018 = NA`.

## Output panel

The Python script exports a long panel suitable for the R event-study and
HonestDiD script. The most important columns are:

| Column | Meaning |
|---|---|
| `unit_id` | Stable macroterritory-sector identifier |
| `year` | Calendar year |
| `rel_year` | `year - treatment_year` |
| `post` | `1` from the treatment year onwards |
| `first_treat` | Treatment year, normally 2019 |
| `employees_youth` | Youth employment in levels |
| `ln_employees_youth` | Natural log of youth employment |
| `weight_2018` | Baseline youth employment weight |
| `bite_y_inc_2018` | Incidence bite, frozen in 2018 |
| `bite_y_cost_2018` | Cost bite, frozen in 2018, if available |

