-- Fails if any event was not assigned to a province or the outside bucket, or
-- if the assigned distance is negative (haversine regression).
select event_id, region, region_distance_km
from {{ ref('fct_earthquakes') }}
where region is null or region_distance_km < 0
