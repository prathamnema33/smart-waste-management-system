# Analytics and Power BI

## Run the read-only pipeline

From `backend/`, with the backend virtual environment active:

```powershell
.\venv\Scripts\python.exe etl\run_etl.py
.\venv\Scripts\python.exe eda.py
```

The ETL reads PostgreSQL and writes snapshots under `data\raw\`, cleaned
candidate tables under `data\processed\`, analytics datasets under
`data\analytics\`, and issue/quarantine reports under `data\quality\`. It does
not write to PostgreSQL. EDA is also read-only and writes its report, tables,
and plots to `eda_output\`.

The current seeded development dataset has 100 generated citizens and 20
generated workers. It does not meet the separate portfolio target of 1,000
citizens and 50 workers. This analytics work does not add, reset, or delete
operational records.

## Warehouse files

`data\analytics\` contains one CSV per dataset. Dimensions are descriptive
lookups; fact files retain source event grain unless noted.

| Dataset | Grain / use |
|---|---|
| `dim_date` | One calendar day across observed source dates |
| `dim_ward` | One authoritative municipal ward, including its source geometry |
| `dim_area` | One operational area and its parent ward; provisional areas are flagged |
| `dim_worker`, `dim_citizen`, `dim_vehicle`, `dim_waste_type` | Entity/category lookups |
| `fact_waste` | One waste report; includes area and ward attributes |
| `fact_collection` | One collection request; includes its report's area and ward |
| `fact_rating` | One source rating |
| `fact_segmentation` | One rating enriched with request/report/area/ward keys |
| `fact_complaint`, `fact_reward`, `fact_penalty`, `fact_gps`, `fact_alert` | One source event each |
| `analytics_ward_performance` | One row per municipal ward; separately aggregated observed metrics |
| `analytics_ward_priority_score` | One row per ward with documented development priority components |
| `analytics_ward_daily`, `analytics_ward_weekly`, `analytics_ward_monthly` | Ward/time aggregates |
| `analytics_forecast_features` | Complete ward/day calendar with lag features; forecast features, not predictions |
| `analytics_business_insights` | Evidence-backed findings, measured evidence, caveats, and recommendations |
| `powerbi_*` | Curated import files for overview/map, time, type, area, and worker pages |

## Power BI model

Use `dim_ward`, `dim_area`, `dim_worker`, `dim_citizen`, `dim_vehicle`,
`dim_waste_type`, and `dim_date` as lookup tables. Relate facts to their
corresponding dimensions by matching IDs; use single-direction, one-to-many
relationships where the keys are unique in the dimension. `dim_ward` filters
`dim_area`, which filters `fact_waste`, `fact_collection`, `fact_complaint`,
`fact_gps`, `fact_alert`, and `fact_segmentation`. `dim_worker` filters
worker-bearing facts; citizen and vehicle dimensions filter their corresponding
activity facts. `dim_ward` also filters ward-performance tables. Avoid
fact-to-fact relationships and multiple active paths for the same dimension.

`fact_segmentation` is a rating-grain, ward-enriched convenience export. Use
its `area_id` relationship for area/ward rating measures; do not also connect
its copied `ward_id` to `dim_ward`, as that creates a second filter path. Keep
`fact_rating` as the source-grain rating table for cases that require its
un-enriched fields; do not include both rating tables in the same visual. The
`powerbi_*` files are denormalized visual inputs and should not be joined back
into the normalized warehouse model.

Use `reported_at`, `assigned_at`, `collected_at`, `rated_at`, and other event
timestamps for their respective event analyses. For shared date slicers,
designate one active date relationship at a time or use role-playing date
dimensions; do not imply that assignment, collection, report, and rating dates
are interchangeable.

Suggested measures (rename table/column identifiers to match the Power BI
model if needed):

```DAX
Reported Waste (kg) =
SUM ( fact_waste[quantity_kg] )

Waste Reports =
DISTINCTCOUNT ( fact_waste[report_id] )

Average kg per Report =
DIVIDE ( [Reported Waste (kg)], [Waste Reports] )

Collection Requests =
DISTINCTCOUNT ( fact_collection[request_id] )

Collected Requests =
CALCULATE (
    [Collection Requests],
    fact_collection[collection_status] = "COLLECTED"
)

Collection Efficiency % =
DIVIDE ( [Collected Requests], [Collection Requests] )

Segregation Ratings =
DISTINCTCOUNT ( fact_segmentation[rating_id] )

Good Segregation Rate % =
DIVIDE (
    CALCULATE (
        [Segregation Ratings],
        fact_segmentation[rating] IN { 4, 5 }
    ),
    [Segregation Ratings]
)

Average Segregation Rating =
AVERAGE ( fact_segmentation[rating] )
```

Collection efficiency is completed requests divided by requests, not reports.
Coverage is a separate metric: requests divided by reports. Good segregation
rate is ratings of 4 or 5 divided by all available ratings; it is `BLANK` when
no ratings exist, not zero.

## Suggested report pages

1. **Ward overview:** report count, total/average kg, collection coverage and
   efficiency, rating count/good-segregation rate, complaints, and priority
   category; add ward and time slicers.
2. **Ward map:** use `powerbi_ward_map` and its ward GeoJSON with a map visual
   that accepts polygon geometry. Color by one selected metric/priority.
3. **Trends:** daily, weekly, and monthly waste and collection exports; use
   `analytics_forecast_features` for historical lags only, not as a forecast.
4. **Operations:** `powerbi_area_operations` and
   `powerbi_worker_performance`; expose request workload alongside completion
   so low-volume rates are not overinterpreted.
5. **Composition and evidence:** waste type distributions and
   `analytics_business_insights`, retaining each insight's evidence and
   limitations alongside the recommendation.

## Interpretation and source limitations

- This dataset is controlled development data, not a representative municipal
  sample. The seeded counts remain 100 citizens and 20 workers.
- Population is a demand prior only. `0.45 kg/person/day` is a development
  assumption used for context, not an official Bhopal rate or observed tonnage.
- Ward 44's population remains `NULL`; it is never changed by ETL. Priority
  scoring imputes the median observed ward population solely in its normalized
  population component and records `population_observed`.
- Provisional operational areas are a data-management layer based on existing
  ward geometry, not official locality boundaries. No further area splitting
  is performed.
- Collection efficiency is only measurable for requests. Reports without
  requests are not counted as uncollected requests.
- Penalties have no rating/reference key in the source schema. Citizen-level
  totals cannot establish that an individual penalty was caused by a particular
  segregation rating.
- Priority scores are a within-extract review aid, not an official municipal
  standard. Weights are 30% reported waste, 25% collection shortfall, 20%
  segregation shortfall, 15% complaint rate, and 10% population. Unobserved
  collection efficiency is treated as zero, unobserved segregation as a neutral
  50% good rate, and missing population as the non-null median only for scoring.
- ETL quality issue counts may refer to overlapping checks. `quarantined_rows`
  in `etl_summary.csv` counts unique source rows excluded during cleaning;
  `quarantine_dataset_rows` is the sum of reason-specific quarantine files and
  may count a row more than once.

## SQL practice and business questions

Run the read-only query examples in `sql\business_questions.sql` using a
PostgreSQL client against the configured database. They cover ward volume,
collection and segregation, complaints, worker workload, time trends,
operational bottlenecks, and a priority shortlist. The examples use CTEs,
joins, `GROUP BY`/`HAVING`, `CASE`, `RANK`, `DENSE_RANK`, `LAG`, running
aggregates, and `DATE_TRUNC`. The SQL shortlist aggregates each subject in a
separate CTE to avoid fan-out double counting.
