# Final report (launcher smoke test)

## 1. Final answer
Recommend **candidate y**. AI-generated conclusion: on the stub runner, y scored roc_auc 0.91 versus 0.90 for x, a difference of 0.010, which exceeds the 0.003 practical-difference threshold. This is a single run per candidate on one fixed seed, so it is a preliminary observation, not a discovery.

## 2. Evidence
| Experiment | Candidate | Status | roc_auc | Prediction committed beforehand |
|---|---|---|---|---|
| E1 | x | ok | 0.90 | mean 0.75, sd 0.15 |
| E2 | y | ok | 0.91 | mean 0.90, sd 0.08 |

- Hypothesis H1 (AI-generated, prior 0.5): y scores higher than x by at least 0.003. Falsifier: roc_auc(y) - roc_auc(x) < 0.003. Observed difference +0.010, so H1 was not falsified.
- Sources: none. No literature tool was available, so no external claims are made or cited.
- No runs failed.

## 3. How results changed decisions
- After E1 (x = 0.90): result was within my predicted range (1 sd above the mean); plan unchanged, ran y. I tightened the E2 prediction to mean 0.90, sd 0.08, using x as the reference.
- After E2 (y = 0.91): H1 not falsified; run budget (2) exhausted, so I submitted y. Neither result changed the plan.

## 4. Uncertainty and limitations
- One run per candidate with a single fixed seed: there is no estimate of run-to-run variance, so I cannot say whether a 0.010 gap exceeds noise. It exceeds the stated practical threshold only.
- The task is a stub for launcher testing, not a real dataset; the numbers carry no scientific meaning beyond confirming the pipeline runs.
- My E1 prediction was poorly informed (wide sd), reflecting no prior knowledge of the stub.

## 5. Next experiment and validation needed
Repeat x and y across several seeds (e.g. 5 or more each) and compare the paired difference with a confidence interval, to check that the +0.010 gap is stable. On a real task, also confirm on held-out data before any recommendation.
