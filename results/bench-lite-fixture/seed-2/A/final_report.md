# Final report (AI-generated analysis)

## 1. Answer: no_correction
Naive grouped-CV AUC (logistic regression) is not meaningfully overstated in this simulation. Mean gap (naive minus true pseudo-unresolved AUC), 20 splits each:
- gamma 0 (E1): -0.002 (95% range -0.027 to 0.036)
- gamma 1 (E2): -0.002 (-0.043 to 0.037)
- gamma 2 (E3): +0.002 (-0.018 to 0.043)

All means are far below the 0.02 threshold, and the ranges are centred on zero. Report resolved-set AUC (about 0.82) with its interval.

## 2. Evidence
Experiments E1-E3 are recorded in the run records. E4 (hgb_naive_g1) was started but had not finished when I wrote this, so it is not used.
No literature was retrieved, so I cite no sources. Nothing here rests on an external claim.

## 3. Decisions
H1 (AI-generated, prior 0.6) predicted gap >= 0.02 at gamma 1. E2 falsified it for LR. I did not test the correction estimators because there was no bias to correct.
My E1 prediction (mean 0, sd 0.01) was too tight. The per-split spread is about 0.03.
The first batched command timed out at 60 s and E2's output was lost from the terminal. I recovered the E2 result from run_records.jsonl.

## 4. Limitations
- Only LR with the naive estimator was run, and only 3 runs finished.
- HGB was not evaluated, and neither were iw or iw_clip. HGB could behave differently.
- The data_ver field reads "synthetic-fixture@bd9aba94...", so the data may be a fixture and not the real TOI table.
- Results describe the simulation only, not real unresolved TOIs.
- The resolution model is weak (out-of-fold AUC 0.75).
- The split-to-split ranges are wide (about ±0.04), so a small true gap cannot be excluded.
- The seed was fixed at 2, so this is one seed family.

## 5. Next
Run HGB naive at gamma 1 and 2, then iw and iw_clip, to compare error. Check whether the data is the real TOI snapshot. Test more seeds.
