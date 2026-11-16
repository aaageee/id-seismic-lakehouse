-- Enrichment: nearest province (haversine to provincial capitals), local time
-- zone, and the Gutenberg-Richter energy equivalent for every valid event.
--
-- The distance join is a 3k x 38 cross product, which DuckDB handles in
-- milliseconds. A real GIS pipeline would use polygon boundaries and a spatial
-- index; the trade-off is documented in docs/decisions.md.

with valid_events as (

    select * from {{ ref('stg_usgs__events') }}
    where is_latest_revision and is_valid_event

),

provinces as (

    select * from {{ ref('id_provinces') }}

),

distances as (

    select
        e.*,
        p.province,
        p.island as capital_island,
        2 * 6371.0088 * asin(sqrt(
            power(sin(radians(p.lat - e.latitude) / 2), 2)
            + cos(radians(e.latitude)) * cos(radians(p.lat))
              * power(sin(radians(p.lon - e.longitude) / 2), 2)
        )) as distance_km
    from valid_events e
    cross join provinces p

),

nearest as (

    select *
    from (
        select
            distances.*,
            row_number() over (partition by event_id order by distance_km) as rn
        from distances
    )
    where rn = 1

),

zoned as (

    select
        *,
        case
            when longitude < 120 then 'Asia/Jakarta'
            when longitude < 135 then 'Asia/Makassar'
            else 'Asia/Jayapura'
        end as local_timezone
    from nearest

),

localised as (

    select
        *,
        timezone(local_timezone, event_time_utc) as event_time_local
    from zoned

)

select
    event_id,
    event_time_utc,
    updated_at_utc,
    local_timezone,
    event_time_local,
    cast(event_time_local as date) as event_date_local,
    magnitude,
    depth_km,
    latitude,
    longitude,
    place,
    case
        when distance_km <= {{ var('region_distance_km') }} then province
        else 'Luar wilayah'
    end as region,
    case
        when distance_km <= {{ var('region_distance_km') }} then capital_island
        else 'Offshore / outside'
    end as island,
    distance_km as region_distance_km,
    is_tsunami,
    alert_level,
    felt_reports,
    significance,
    review_status,
    magnitude_type,
    network,
    source_url,
    power(10, 4.8 + 1.5 * magnitude)              as energy_joules,
    power(10, 4.8 + 1.5 * magnitude) / 4.184e9    as energy_tons_tnt,
    ingest_date,
    source_file
from localised
