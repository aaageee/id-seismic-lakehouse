-- Gold fact table: one row per earthquake, ready for BI / dashboard queries.
with enriched as (

    select * from {{ ref('int_events_enriched') }}

)

select
    event_id,
    event_time_utc,
    event_time_local,
    local_timezone,
    event_date_local,
    magnitude,
    case
        when magnitude >= 6.0 then 'M6.0+'
        when magnitude >= 5.0 then 'M5.0-5.9'
        when magnitude >= 4.0 then 'M4.0-4.9'
        else 'M2.5-3.9'
    end as magnitude_class,
    depth_km,
    case
        when depth_km < 70 then 'Shallow (<70 km)'
        when depth_km <= 300 then 'Intermediate (70-300 km)'
        else 'Deep (>300 km)'
    end as depth_class,
    latitude,
    longitude,
    place,
    region,
    island,
    region_distance_km,
    is_tsunami as tsunami,
    alert_level as alert,
    felt_reports as felt,
    significance,
    review_status,
    magnitude_type,
    network,
    source_url,
    energy_joules,
    energy_tons_tnt,
    updated_at_utc,
    ingest_date
from enriched
