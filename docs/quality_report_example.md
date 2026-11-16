# Data quality report

Generated: 17 Nov 2026 00:24 - 10/10 checks passed.

| # | Check | Observed | Result |
|---|-------|----------|--------|
| 1 | Gold fact table is populated | 3,051 events | **PASS** |
| 2 | Daily mart reconciles with fact table | 3,051 vs 3,051 | **PASS** |
| 3 | No duplicate event ids | 0 duplicates | **PASS** |
| 4 | Every event mapped to a region | 0 unmapped | **PASS** |
| 5 | Coordinates inside valid ranges | 0 bad lat / 0 bad lon | **PASS** |
| 6 | Magnitudes inside 0-10 | 0 out of range | **PASS** |
| 7 | No future timestamps | 0 future rows | **PASS** |
| 8 | Quarantine rate below 10% | 0.0% | **PASS** |
| 9 | b-value fitted for national scope | 0 missing fits | **PASS** |
| 10 | Data freshness (target < 72h) | 10.2 h | **PASS** |

Checks run against the gold marts after `dbt build`. A `WARN` means the data is
structurally valid but should be refreshed (for example when reviewing the
committed demo sample, which is intentionally historical).
