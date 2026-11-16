-- One-row observability mart: the numbers a data team would page on.
with staged as (

    select * from {{ ref('stg_usgs__events') }}

),

quarantine as (

    select count(*) as quarantined_rows from {{ ref('quarantine_events') }}

),

valid as (

    select * from {{ ref('fct_earthquakes') }}

)

select
    (select count(*) from staged)                                      as total_raw_rows,
    (select count(*) from staged where is_latest_revision)             as latest_revision_rows,
    (select count(*) from staged where not is_latest_revision)         as duplicate_rows_removed,
    (select quarantined_rows from quarantine)                          as quarantined_rows,
    (select count(*) from valid)                                       as valid_events,
    (select quarantined_rows from quarantine)                          as invalid_events,
    (select count(distinct ingest_date) from staged)                   as ingest_days,
    (select count(distinct source_file) from staged)                   as ingest_files,
    (select max(ingest_date) from staged)                              as last_ingest_date,
    (select max(loaded_at) from staged)                                as last_loaded_at,
    (select min(event_time_utc) from valid)                            as first_event_utc,
    (select max(event_time_utc) from valid)                            as latest_event_utc,
    (select max(event_time_local) from valid)                          as latest_event_local,
    (select min(event_date_local) from valid)                          as first_event_date,
    (select max(event_date_local) from valid)                          as latest_event_date,
    (select date_diff('day', min(event_date_local), max(event_date_local)) + 1 from valid) as coverage_days,
    (select date_diff('hour', max(event_time_utc), now()) from valid)  as event_age_hours,
    (select count(distinct region) from valid)                         as distinct_regions,
    (select count(*) from valid where region is null)                  as null_region_rows,
    (select count(*) from valid where magnitude is null)               as null_magnitude_rows,
    (select min(latitude) from valid)                                  as min_latitude,
    (select max(latitude) from valid)                                  as max_latitude,
    (select min(longitude) from valid)                                 as min_longitude,
    (select max(longitude) from valid)                                 as max_longitude
