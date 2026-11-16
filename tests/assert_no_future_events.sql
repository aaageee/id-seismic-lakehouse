-- Fails if an origin time is in the future (timezone or unit-conversion bug).
select event_id, event_time_utc
from {{ ref('fct_earthquakes') }}
where event_time_utc > now() + interval 1 hour
