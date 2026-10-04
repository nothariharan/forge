# Final report

## 1. Answer: no_correction (AI-generated conclusion, preliminary)
Naive grouped-CV AUC for logistic regression showed no meaningful overstatement. Mean gap, with 95% range over the 20 splits:
- E1, gamma 0 (negative control): -0.0047 (-0.071 to 0.032)
- E2, gamma 1: -0.0012 (-0.060 to 0.048)
- E4, gamma 2: +0.0010 (-0.034 to 0.037)

All means are far below the 0.02 threshold. The ranges are wide (about +/-0.05), so a gap of 0.02 or more cannot be excluded for individual splits.

## 2. Evidence
- E1: lr naive g0, gap -0.0047, true AUC 0.825, abs_error 0.026.
- E2: lr naive g1, gap -0.0012, true AUC 0.823, abs_error 0.027.
- E4: lr naive g2, gap +0.0010, true AUC 0.819, abs_error 0.017.
- E3 (hgb naive g1) was still running when time ran out and has no recorded result. It was launched in a command that timed out. The hgb model, and the iw and iw_clip estimators, were therefore not tested.
- No literature was retrieved, so I cite no sources. There are no verified references.
- The run records list data_ver as "synthetic-fixture@...". The runs may therefore use a synthetic fixture rather than the real TESS TOI snapshot.

## 3. Decisions
After E2 showed a gap near 0, I planned to test stronger selection (gamma 2, E4) and hgb (E3). The gap stayed near 0 at gamma 2. Slow runs and the 10-minute limit prevented the hgb and weighted-estimator runs.

## 4. Limitations
- Only lr was tested, with one fixed seed.
- hgb and the weighted estimators were not run.
- The 95% ranges are wide.
- The data may be a synthetic fixture.
- The result describes the simulation, not real unresolved TOIs.
- Hypothesis H1 (AI-generated, prior 0.5) predicted a gap of about 0.03 at gamma 1. The lr runs contradict it for lr.

## 5. Next
Run hgb naive at gamma 1 and 2, then the iw and iw_clip estimators. Compare their abs_error against naive, use more seeds, and confirm the data is the real TOI table.
