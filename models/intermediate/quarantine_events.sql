-- Events that failed structural validation. Keeping them in a table makes the
-- rejection rate observable instead of invisible, which is the whole point of a
-- quarantine layer.
with events as (

    select * from {{ ref('stg_usgs__events') }}
    where is_latest_revision and not is_valid_event

)

select
    event_id,
    magnitude,
    event_time_utc,
    latitude,
    longitude,
    depth_km,
    case
        when event_id is null then 'missing_event_id'
        when magnitude is null then 'missing_magnitude'
        when event_time_utc is null then 'missing_origin_time'
        when latitude is null or latitude not between -90 and 90 then 'invalid_latitude'
        when longitude is null or longitude not between -180 and 180 then 'invalid_longitude'
        when depth_km is null then 'missing_depth'
        else 'unknown'
    end as quarantine_reason,
    source_file,
    ingest_date
from events
