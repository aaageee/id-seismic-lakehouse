-- Fails if the gold fact table contains duplicate event ids.
select event_id, count(*) as n
from {{ ref('fct_earthquakes') }}
group by 1
having count(*) > 1
