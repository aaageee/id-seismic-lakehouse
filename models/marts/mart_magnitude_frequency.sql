-- Magnitude-frequency data for the Gutenberg-Richter plot, at national level and
-- per province. Only points with enough cumulative events are exposed; the
-- tail below that is sampling noise, not signal.
with base as (

    select region, magnitude
    from {{ ref('fct_earthquakes') }}
    where magnitude >= cast({{ var('completeness_magnitude') }} as double)

),

scope_events as (

    select 'national' as scope, magnitude from base
    union all
    select region as scope, magnitude from base

),

scope_totals as (

    select 'national' as scope, count(*) as n_events_above_mc from base
    union all
    select region as scope, count(*) as n_events_above_mc from base group by 1

),

binned as (

    select
        scope,
        floor(magnitude * 10) / 10.0 as mag_bin,
        count(*) as n_events
    from scope_events
    group by 1, 2

),

cumulative as (

    select
        scope,
        mag_bin,
        n_events,
        sum(n_events) over (
            partition by scope
            order by mag_bin desc
            rows between unbounded preceding and current row
        ) as n_cumulative
    from binned

),

fit_rows as (

    select *
    from cumulative
    where n_cumulative >= {{ var('min_cumulative_for_fit') }}

),

fitted as (

    select
        scope,
        -regr_slope(log10(cast(n_cumulative as double)), mag_bin) as b_value,
        regr_r2(log10(cast(n_cumulative as double)), mag_bin)     as r2,
        count(*)                                                   as n_bins
    from fit_rows
    group by 1

)

select
    c.scope,
    c.mag_bin,
    c.n_events,
    c.n_cumulative,
    f.b_value,
    f.r2,
    f.n_bins,
    cast({{ var('completeness_magnitude') }} as double) as mc,
    t.n_events_above_mc
from cumulative c
join fitted f using (scope)
join scope_totals t using (scope)
where c.n_cumulative >= {{ var('min_cumulative_for_fit') }}
order by c.scope, c.mag_bin
