# Data dictionary

All models live in the DuckDB warehouse at `data/warehouse/seismic.duckdb`.
Schemas mirror the medallion layers: `bronze` (raw), `silver` (cleaned and
enriched), `gold` (serving marts).

## `bronze.usgs_events`

Raw USGS GeoJSON documents, one row per ingested partition. Written by
`python -m pipeline load`; dbt only reads it.

| Column | Type | Notes |
|---|---|---|
| `type` | VARCHAR | Always `FeatureCollection`. |
| `metadata` | STRUCT | USGS response metadata (count, status, URL). |
| `features` | LIST(STRUCT) | Untouched GeoJSON features. |
| `_source_file` | VARCHAR | Absolute path of the partition file. |
| `_ingest_date` | VARCHAR | Partition date extracted from `dt=YYYY-MM-DD`. |
| `_loaded_at` | TIMESTAMPTZ | Warehouse load time, used for source freshness. |

## `silver.stg_usgs__events`

Typed and deduplicated events. Duplicate revisions are kept but flagged, so the
quarantine model can count them.

| Column | Type | Notes |
|---|---|---|
| `event_id` | VARCHAR | USGS event id (business key). |
| `magnitude` | DOUBLE | Preferred magnitude. |
| `event_time_utc` | TIMESTAMPTZ | Origin time, converted from epoch milliseconds. |
| `updated_at_utc` | TIMESTAMPTZ | Last USGS revision. |
| `is_tsunami` | BOOLEAN | USGS tsunami flag (bulletin, not a warning). |
| `alert_level` | VARCHAR | PAGER alert (`green` … `red`), usually null. |
| `felt_reports` | INTEGER | Number of "felt" reports. |
| `significance` | BIGINT | USGS significance score. |
| `review_status` | VARCHAR | `reviewed`, `automatic` or `deleted`. |
| `magnitude_type` | VARCHAR | `mww`, `mb`, `mwb`, … |
| `network` | VARCHAR | Reporting network (`us`, `ci`, …). |
| `source_url` | VARCHAR | USGS event page. |
| `latitude` / `longitude` | DOUBLE | Epicentre, decimal degrees (GeoJSON order is lon, lat). |
| `depth_km` | DOUBLE | Hypocentre depth, positive down. |
| `is_latest_revision` | BOOLEAN | Newest revision of this `event_id`. |
| `is_valid_event` | BOOLEAN | Structural validity flag. |

## `silver.quarantine_events`

Invalid latest revisions with a `quarantine_reason` (`missing_magnitude`,
`invalid_latitude`, …). Expected to be empty for a healthy USGS feed.

## `silver.int_events_enriched`

Valid events with province, local time, and energy.

| Column | Notes |
|---|---|
| `region` | Nearest provincial capital within 700 km, else `Luar wilayah`. |
| `island` | Island group of the assigned province, else `Offshore / outside`. |
| `region_distance_km` | Haversine distance to the assigned capital. |
| `local_timezone` | `Asia/Jakarta`, `Asia/Makassar` or `Asia/Jayapura`, derived from longitude. |
| `event_time_local` | Origin time in the event's local zone. |
| `event_date_local` | Local calendar date used for daily marts. |
| `energy_joules` | `10^(4.8 + 1.5 * M)`. |
| `energy_tons_tnt` | Joules / 4.184e9. |

## `gold.fct_earthquakes`

One row per earthquake. Adds `magnitude_class` (`M2.5-3.9`, `M4.0-4.9`,
`M5.0-5.9`, `M6.0+`) and `depth_class` (`Shallow (<70 km)`,
`Intermediate (70-300 km)`, `Deep (>300 km)`). Primary key: `event_id`.

## `gold.mart_daily_activity`

Dense daily spine (`activity_date`), counts per magnitude class, max magnitude,
energy and felt reports. Zero-event days are included on purpose.

## `gold.mart_region_activity`

Province rollup: `n_events`, `n_events_30d` (relative to the newest event in the
warehouse), `max_magnitude`, `n_m5plus`, `n_tsunami`, `avg_depth_km`,
`energy_tons_tnt`, `last_m5_at`, `days_since_m5`, `b_value`, `b_value_r2`,
`n_events_above_mc`, `is_b_value_reliable`.

`b_value` is null until a province has at least 40 events above Mc (M4.0); the
flag makes that explicit instead of hiding it.

## `gold.mart_magnitude_frequency`

`scope` (`national` or province), `mag_bin`, `n_events`, `n_cumulative`,
`b_value`, `r2`, `n_bins`, `mc`, `n_events_above_mc`. Only bins with at least 5
cumulative events are exposed.

## `gold.mart_depth_profile`

`depth_class`, depth bounds, `n_events`, `share`, `max_magnitude`,
`avg_magnitude`, `energy_tons_tnt`.

## `gold.mart_pipeline_health`

One-row observability mart: raw vs. deduplicated rows, duplicates removed,
quarantined rows, coverage days, freshness age, ingest files/days, coordinate
bounds. Consumed by `pipeline quality` and the dashboard footer.

## `ops.pipeline_runs`

Written by Python (not dbt): `run_id`, `step`, `started_at`, `finished_at`,
`status`, `row_count`, `duration_s`, `details` (JSON). This is the audit trail
for ingestion runs.
