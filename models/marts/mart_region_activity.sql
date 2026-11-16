-- Province-level rollup. "Last 30 days" is measured relative to the newest
-- event in the warehouse, not wall-clock time, so the committed dashboard stays
-- internally consistent even when it is reviewed weeks after generation.
with fct as (

    select * from {{ ref('fct_earthquakes') }}

),

reference as (

    select max(event_time_local) as ref_ts from fct

),

agg as (

    select
        region,
        island,
        count(*)                                             as n_events,
        max(magnitude)                                       as max_magnitude,
        count(*) filter (where magnitude >= 5)                as n_m5plus,
        count(*) filter (where tsunami)                       as n_tsunami,
        avg(depth_km)                                        as avg_depth_km,
        sum(energy_tons_tnt)                                 as energy_tons_tnt,
        min(event_time_local)                                as first_event_at,
        max(event_time_local)                                as latest_event_at,
        max(event_time_local) filter (where magnitude >= 5)  as last_m5_at
    from fct
    group by 1, 2

),

recent as (

    select region, count(*) as n_events_30d
    from fct, reference
    where event_time_local >= reference.ref_ts - interval 30 day
    group by 1

),

b_values as (

    select region, b_value, b_value_r2, n_events_above_mc, is_b_value_reliable
    from {{ ref('int_region_b_value') }}

)

select
    a.region,
    a.island,
    a.n_events,
    coalesce(r.n_events_30d, 0) as n_events_30d,
    a.max_magnitude,
    a.n_m5plus,
    a.n_tsunami,
    a.avg_depth_km,
    a.energy_tons_tnt,
    a.first_event_at,
    a.latest_event_at,
    a.last_m5_at,
    case
        when a.last_m5_at is null then null
        else date_diff('day', a.last_m5_at, reference.ref_ts)
    end as days_since_m5,
    b.b_value,
    b.b_value_r2,
    b.n_events_above_mc,
    coalesce(b.is_b_value_reliable, false) as is_b_value_reliable
from agg a
cross join reference
left join recent r using (region)
left join b_values b using (region)
order by a.n_events desc, a.max_magnitude desc
