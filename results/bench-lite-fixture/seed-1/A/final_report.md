# Final report
## Answer: no_correction (AI-generated conclusion, preliminary)
Naive resolved-set AUC was not meaningfully overstated in the runs I completed.
- E1 lr naive gamma=1: gap=0.0053 (95% range -0.040 to 0.047), true AUC 0.824, estimate 0.829.
- E4 lr naive gamma=2: gap=0.0010 (95% range -0.034 to 0.037), true AUC 0.819.
Both mean gaps are well under the 0.02 threshold. The ranges across splits are wide and cross zero.

## Evidence and decisions
H1 (AI-generated) predicted a gap of at least 0.02. E1 and E4 falsified it for lr. I recorded E1 with a predicted mean of 0.03, and the observed 0.005 was lower. The E2 command (hgb, gamma=1) timed out in my shell and E2's ID was consumed with no result recorded. I reran it as E3, which had not returned when I wrote this, so hgb is untested. I ran no iw or iw_clip estimators and no gamma=0 control. This is only 2 completed runs out of the 10 allowed.
The run metadata lists data_ver as "synthetic-fixture", so these runs may not use the real TOI table.

## Sources
No literature was retrieved. I make no cited factual claims.

## Limitations
Only lr was tested, with 2 of the 10 allowed runs. The gamma=0 negative control is missing. The hgb model and the weighted estimators are untested. The split-to-split spread (about ±0.04) is larger than the 0.02 threshold, so a real overstatement of 0.02 could be hidden. The result describes a simulation, not accuracy on real unresolved TOIs.

## Next experiment
Run hgb naive at gamma=1 and gamma=2, and the gamma=0 control. Then run iw and iw_clip to compare abs_error against naive. Confirm the dataset is the real TOI snapshot rather than a fixture.
