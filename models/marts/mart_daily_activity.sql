-- Daily grain, with a dense date spine so quiet days render as zero instead of
-- disappearing from the chart.
with fct as (

    select * from {{ ref('fct_earthquakes') }}

),

bounds as (

    select
        min(event_date_local) as min_date,
        max(event_date_local) as max_date
    from fct

),

spine as (

    select cast(day as date) as activity_date
    from generate_series(
        (select min_date from bounds),
        (select max_date from bounds),
        interval 1 day
    ) as t(day)

),

daily as (

    select
        event_date_local as activity_date,
        count(*) as n_events,
        count(*) filter (where magnitude_class = 'M2.5-3.9') as n_m25_39,
        count(*) filter (where magnitude_class = 'M4.0-4.9') as n_m40_49,
        count(*) filter (where magnitude_class = 'M5.0-5.9') as n_m50_59,
        count(*) filter (where magnitude_class = 'M6.0+') as n_m60plus,
        max(magnitude) as max_magnitude,
        sum(energy_tons_tnt) as energy_tons_tnt,
        sum(coalesce(felt, 0)) as felt_reports
    from fct
    group by 1

)

select
    s.activity_date,
    coalesce(d.n_events, 0) as n_events,
    coalesce(d.n_m25_39, 0) as n_m25_39,
    coalesce(d.n_m40_49, 0) as n_m40_49,
    coalesce(d.n_m50_59, 0) as n_m50_59,
    coalesce(d.n_m60plus, 0) as n_m60plus,
    d.max_magnitude,
    coalesce(d.energy_tons_tnt, 0) as energy_tons_tnt,
    coalesce(d.felt_reports, 0) as felt_reports
from spine s
left join daily d using (activity_date)
