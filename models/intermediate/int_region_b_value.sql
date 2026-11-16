-- Gutenberg-Richter b-value per province: log10(N >= M) = a - b*M.
--
-- Only bins with at least `min_cumulative_for_fit` events are used, and the
-- value is only surfaced when the region has enough events to be meaningful
-- (`min_events_for_reliable_b`). Nulls are honest; a fabricated b-value from
-- eight events is worse than no b-value.

with events as (

    select region, magnitude
    from {{ ref('fct_earthquakes') }}
    where magnitude >= cast({{ var('completeness_magnitude') }} as double)

),

binned as (

    select
        region,
        floor(magnitude * 10) / 10.0 as mag_bin,
        count(*) as n_events
    from events
    group by 1, 2

),

cumulative as (

    select
        region,
        mag_bin,
        n_events,
        sum(n_events) over (
            partition by region
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
        region,
        -regr_slope(log10(cast(n_cumulative as double)), mag_bin) as b_value,
        regr_r2(log10(cast(n_cumulative as double)), mag_bin)     as r2,
        count(*)                                                   as n_bins
    from fit_rows
    group by 1

),

totals as (

    select region, count(*) as n_events_above_mc
    from events
    group by 1

)

select
    f.region,
    case
        when t.n_events_above_mc >= {{ var('min_events_for_reliable_b') }}
         and f.n_bins >= 5
         and f.b_value between 0.3 and 2.5
        then f.b_value
    end as b_value,
    case
        when t.n_events_above_mc >= {{ var('min_events_for_reliable_b') }} then f.r2
    end as b_value_r2,
    t.n_events_above_mc,
    f.n_bins,
    (
        t.n_events_above_mc >= {{ var('min_events_for_reliable_b') }}
        and f.n_bins >= 5
        and f.b_value between 0.3 and 2.5
    ) as is_b_value_reliable
from fitted f
join totals t using (region)
