# Engineering decisions

Short ADRs for the choices a reviewer is most likely to question. Each one lists
the alternative I deliberately did not take.

## ADR-001 — DuckDB + dbt instead of a cloud warehouse

**Decision:** DuckDB as the warehouse, dbt-duckdb for transformation.

**Why:** the project must be runnable by anyone who clones it, without a cloud
account, credentials or a credit card. DuckDB gives columnar execution,
window functions, `regr_slope` and Parquet/JSON readers in a single file, and
dbt keeps the transformation layer portable to BigQuery/Snowflake — the SQL and
tests are the artefact, the adapter is swappable.

**Trade-off:** no concurrent writers, no RBAC, no separation of storage and
compute. For 3k events/year that is a feature, not a bug.

## ADR-002 — Ingestion-time partitions + dedupe in SQL

**Decision:** write one `dt=YYYY-MM-DD` partition per ingest day, merge retries
by event id, then deduplicate again in `stg_usgs__events` keeping the newest
`updated` timestamp.

**Why:** USGS revises events (magnitude, depth, location) for days after they
occur, and a daily incremental window overlaps with the previous run. Bronze
must never lose history, so the raw payload is kept; the business key and
revision logic live in SQL where they are testable.

**Trade-off:** duplicate raw rows accumulate over time and are removed in the
warehouse. At larger volumes I would add a compaction job that rewrites
partitions into monthly files (see roadmap).

## ADR-003 — Nearest provincial capital for region assignment

**Decision:** cross join events to 38 provincial capitals, take the nearest by
haversine distance, and label anything beyond 700 km as `Luar wilayah`.

**Why:** it is deterministic, needs no shapefile or PostGIS extension, and is
good enough for "which province is this earthquake near?", which is how the
public actually reads earthquake news. Distances are also a useful signal on
their own.

**Trade-off:** a point can be closer to another island's capital than to its own
province (e.g. events between Bali and Lombok). Real boundary work needs
polygons and a spatial index; the seed file and the model are structured so that
swap is local to one CTE.

## ADR-004 — b-value with Mc = 4.0 and a reliability threshold

**Decision:** fit `log10(N≥M) = a - bM` with least squares over magnitude bins
with at least 5 cumulative events, for events at or above M4.0, and only publish
a province's b-value when it has 40+ events above Mc and a fit inside 0.3–2.5.

**Why:** b-values are easy to produce and easy to fake. Below the completeness
magnitude the catalog is missing small events, which inflates b; below ~40
events the regression is noise. Returning null is more honest than a confident
wrong number, and the `is_b_value_reliable` flag makes the gap visible.

**Trade-off:** fewer provinces get a b-value, especially early in the coverage
window. That is visible in the dashboard's regional table (blank cell).

## ADR-005 — Static HTML dashboard instead of a BI tool

**Decision:** render the dashboard at build time as one self-contained
`index.html` with inline SVG, published to GitHub Pages.

**Why:** zero infrastructure, no API keys, instant page loads, and the chart code
is reviewable in the same PR as the SQL. It also means CI can assert on the
rendered output, which is hard with a hosted BI tool.

**Trade-off:** no ad-hoc exploration or filters for viewers. For self-service I
would point Metabase/Superset at the same gold marts — the marts are the product,
the dashboard is a view of them.

## ADR-006 — Quality gate as code

**Decision:** dbt schema tests + singular tests for invariants (no duplicates, no
future timestamps, daily mart reconciliation, region coverage) plus a Python
report that turns the health mart into a readable markdown page.

**Why:** the pipeline should fail loudly on a broken assumption, and the report
should show what was checked. `WARN` is reserved for stale-but-valid data (the
committed sample), so CI stays green on the offline demo while a production run
still escalates hard failures.

**Trade-off:** the freshness target is wall-clock based, so an offline build of
historical sample data will always warn. That is intentional and documented.
