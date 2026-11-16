{{ config(materialized='view') }}

-- One row per USGS feature, deduplicated by event id (USGS revises events, so
-- the same id can appear in several daily partitions). Validity is flagged
-- here instead of dropped, so the quarantine model can explain every rejection.

with source as (

    select * from {{ source('bronze', 'usgs_events') }}

),

exploded as (

    select
        feature.id                                        as event_id,
        cast(feature.properties.mag as double)             as magnitude,
        feature.properties.place                           as place,
        cast(feature.properties.time as bigint)            as time_ms,
        cast(feature.properties.updated as bigint)         as updated_ms,
        coalesce(cast(feature.properties.tsunami as int), 0) as tsunami_flag,
        feature.properties.alert                            as alert_level,
        cast(feature.properties.felt as int)               as felt_reports,
        cast(feature.properties.sig as bigint)             as significance,
        feature.properties.status                          as review_status,
        feature.properties.magType                         as magnitude_type,
        feature.properties.net                             as network,
        feature.properties.url                             as source_url,
        cast(feature.geometry.coordinates[1] as double)     as longitude,
        cast(feature.geometry.coordinates[2] as double)     as latitude,
        cast(feature.geometry.coordinates[3] as double)     as depth_km,
        _source_file                                        as source_file,
        _ingest_date                                        as ingest_date,
        _loaded_at                                          as loaded_at
    from source
    cross join unnest(source.features) as t(feature)

),

typed as (

    select
        event_id,
        magnitude,
        place,
        to_timestamp(time_ms / 1000.0)    as event_time_utc,
        to_timestamp(updated_ms / 1000.0) as updated_at_utc,
        (tsunami_flag = 1)                as is_tsunami,
        alert_level,
        felt_reports,
        significance,
        review_status,
        magnitude_type,
        network,
        source_url,
        latitude,
        longitude,
        depth_km,
        source_file,
        ingest_date,
        loaded_at
    from exploded

),

ranked as (

    select
        *,
        row_number() over (
            partition by event_id
            order by updated_at_utc desc nulls last, ingest_date desc
        ) as revision_rank
    from typed

)

select
    event_id,
    magnitude,
    place,
    event_time_utc,
    updated_at_utc,
    is_tsunami,
    alert_level,
    felt_reports,
    significance,
    review_status,
    magnitude_type,
    network,
    source_url,
    latitude,
    longitude,
    depth_km,
    source_file,
    ingest_date,
    loaded_at,
    (revision_rank = 1) as is_latest_revision,
    (
        event_id is not null
        and magnitude is not null
        and event_time_utc is not null
        and latitude between -90 and 90
        and longitude between -180 and 180
        and depth_km is not null
    ) as is_valid_event
from ranked
