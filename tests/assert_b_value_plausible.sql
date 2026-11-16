-- Fails if a fitted b-value is outside the physically plausible 0.3-2.5 band.
-- Values outside that range usually mean a broken cumulative window.
select scope, mag_bin, b_value
from {{ ref('mart_magnitude_frequency') }}
where b_value is not null
  and (b_value < 0.3 or b_value > 2.5)
