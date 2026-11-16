-- Fails if the daily mart does not reconcile with the fact table.
with fact as (
    select count(*) as n from {{ ref('fct_earthquakes') }}
),
daily as (
    select coalesce(sum(n_events), 0) as n from {{ ref('mart_daily_activity') }}
)
select fact.n as fact_rows, daily.n as daily_rows
from fact, daily
where fact.n <> daily.n
