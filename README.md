# F1 Pit Stop Strategy Optimizer

A constraint-programming solver that computes the optimal pit-stop schedule and tire-compound sequence for a Formula 1 race. Built with Google OR-Tools (CP-SAT).

## Problem

Given:
- Race length (laps)
- A set of tire compounds, each with a base lap time, degradation rate, and maximum useful life
- A fixed pit-stop time penalty
- The FIA rule requiring at least two different dry compounds

Find the sequence of stints and pit-stop laps that **minimizes total race time**.

## Model

| Element | Encoding |
|---|---|
| Pit-stop count | Number of "used" stints − 1 |
| Stint length | IntVar ≥ 1 if stint is used, 0 otherwise |
| Compound per stint | IntVar over compound indices |
| Stint time | `L · base + deg · L(L−1)/2`, linearized via reification |
| Two-compound rule | At least one pair of used stints must differ |
| Tire wear cap | `stint_len ≤ max_life` per chosen compound |

## Run

```bash
pip install -r requirements.txt
python f1_strategy.py
```

Sample output for a 58-lap race:

```
F1 Pit Stop Strategy Optimizer
============================================================
Race length : 58 laps
Pit loss    : 22.0 s per stop
Compounds   : ['SOFT', 'MEDIUM', 'HARD']

Status      : OPTIMAL
Total time  : 1:18:42.300
Pit stops   : 2

Stint   Compound   Laps      Range       Time
--------------------------------------------------
    1     MEDIUM     18      1-18    24:12.450
    2     MEDIUM     22     19-40    29:48.900
    3       HARD     18     41-58    24:40.950
```

## Verification

`compare_bruteforce.py` enumerates every 1-stop and 2-stop strategy and reports the best, to sanity-check the CP-SAT solution:

```bash
python compare_bruteforce.py
```

## Tuning

Edit `COMPOUNDS` in `f1_strategy.py` to match a real circuit's tire data (base lap times, degradation curves, life). Adjust `PIT_LOSS_MS` per track.

## Requirements

- Python 3.9+
- `ortools >= 9.7`

## License

MIT
