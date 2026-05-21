"""
Compare optimizer output against all 1-stop and 2-stop brute-force strategies.
Useful for sanity-checking the CP-SAT result.
"""

from itertools import combinations, product
from f1_strategy import COMPOUNDS, PIT_LOSS_MS, optimize, format_time


def stint_time(compound_idx: int, laps: int) -> int:
    c = COMPOUNDS[compound_idx]
    if laps > c.max_life or laps <= 0:
        return 10**12  # infeasible sentinel
    return laps * c.base_lap_time_ms + c.degradation_ms * (laps * (laps - 1) // 2)


def brute_force(total_laps: int, n_stops: int) -> tuple:
    best = (10**18, None)
    for cuts in combinations(range(1, total_laps), n_stops):
        stints = []
        prev = 0
        for cut in cuts:
            stints.append(cut - prev); prev = cut
        stints.append(total_laps - prev)

        for combo in product(range(len(COMPOUNDS)), repeat=n_stops + 1):
            if len(set(combo)) < 2:  # FIA: 2 compounds
                continue
            total = sum(stint_time(c, L) for c, L in zip(combo, stints))
            total += PIT_LOSS_MS * n_stops
            if total < best[0]:
                best = (total, (stints, combo))
    return best


if __name__ == "__main__":
    laps = 58
    print(f"Brute-forcing 1-stop and 2-stop strategies for {laps} laps...")
    for n in (1, 2):
        t, plan = brute_force(laps, n)
        print(f"  Best {n}-stop: {format_time(t)}  {plan}")

    print("\nCP-SAT optimizer:")
    r = optimize(total_laps=laps, max_stops=3)
    print(f"  Optimal: {format_time(r['total_time_ms'])} "
          f"({r['n_stops']} stops)")
