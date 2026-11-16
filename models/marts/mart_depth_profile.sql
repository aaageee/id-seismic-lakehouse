-- Shallow/intermediate/deep split. Depth classes are the standard seismological
-- cut-offs for subduction-zone work (70 km and 300 km).
with fct as (

    select * from {{ ref('fct_earthquakes') }}

)

select
    depth_class,
    min(depth_km) as min_depth_km,
    max(depth_km) as max_depth_km,
    count(*) as n_events,
    count(*) / sum(count(*)) over () as share,
    max(magnitude) as max_magnitude,
    avg(magnitude) as avg_magnitude,
    sum(energy_tons_tnt) as energy_tons_tnt
from fct
group by 1
