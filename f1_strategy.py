"""
F1 Pit Stop Strategy Optimizer
Finds the optimal pit-stop schedule and tire-compound sequence using
CP-SAT constraint programming.

Decision variables:
    - pit_lap[i]   : lap at which the i-th pit stop occurs
    - compound[s]  : tire compound used in stint s

Objective: minimize total race time
"""

from ortools.sat.python import cp_model
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class TireCompound:
    name: str
    base_lap_time_ms: int   # fresh tire lap time in milliseconds
    degradation_ms: int     # extra ms added per lap of wear
    max_life: int           # safe lap count before falloff


# Typical 2024-spec Pirelli compounds (representative numbers)
COMPOUNDS = [
    TireCompound("SOFT",   78_500,  120, 18),
    TireCompound("MEDIUM", 79_200,   75, 28),
    TireCompound("HARD",   80_100,   45, 40),
]

PIT_LOSS_MS = 22_000   # time lost per pit stop (entry + service + exit)


def optimize(total_laps: int,
             max_stops: int = 3,
             must_use_two_compounds: bool = True) -> dict:
    """Return the optimal pit-stop strategy as a dict."""
    model = cp_model.CpModel()
    n_stints = max_stops + 1

    # ── Variables ──────────────────────────────────────────────────────
    # Stint length (laps) of each stint
    stint_len = [model.NewIntVar(1, total_laps, f"stint_{s}_len")
                 for s in range(n_stints)]
    # Compound choice per stint (index into COMPOUNDS)
    compound = [model.NewIntVar(0, len(COMPOUNDS) - 1, f"compound_{s}")
                for s in range(n_stints)]
    # Whether the stint is actually used (length > 0 already enforces this,
    # but we allow zero-length stints to encode "no pit stop").
    used = [model.NewBoolVar(f"used_{s}") for s in range(n_stints)]

    # ── Constraints ────────────────────────────────────────────────────
    # Stint length is positive iff used; zero otherwise.
    for s in range(n_stints):
        model.Add(stint_len[s] >= 1).OnlyEnforceIf(used[s])
        model.Add(stint_len[s] == 0).OnlyEnforceIf(used[s].Not())

    # First stint is always used.
    model.Add(used[0] == 1)
    # If stint s is not used, all later stints are also not used (compaction).
    for s in range(1, n_stints):
        model.AddImplication(used[s - 1].Not(), used[s].Not())

    # Total laps covered = race length.
    model.Add(sum(stint_len) == total_laps)

    # Tire life cap per stint.
    for s in range(n_stints):
        for c, comp in enumerate(COMPOUNDS):
            is_c = model.NewBoolVar(f"is_c{s}_{c}")
            model.Add(compound[s] == c).OnlyEnforceIf(is_c)
            model.Add(compound[s] != c).OnlyEnforceIf(is_c.Not())
            model.Add(stint_len[s] <= comp.max_life).OnlyEnforceIf(is_c)

    # FIA rule: at least two different compounds in dry conditions.
    if must_use_two_compounds:
        diff_pair = []
        for i in range(n_stints):
            for j in range(i + 1, n_stints):
                d = model.NewBoolVar(f"diff_{i}_{j}")
                model.Add(compound[i] != compound[j]).OnlyEnforceIf(d)
                model.Add(compound[i] == compound[j]).OnlyEnforceIf(d.Not())
                both_used = model.NewBoolVar(f"both_{i}_{j}")
                model.AddBoolAnd([used[i], used[j]]).OnlyEnforceIf(both_used)
                model.AddBoolOr([used[i].Not(), used[j].Not()]) \
                    .OnlyEnforceIf(both_used.Not())
                final = model.NewBoolVar(f"compound_pair_{i}_{j}")
                model.AddBoolAnd([d, both_used]).OnlyEnforceIf(final)
                model.AddBoolOr([d.Not(), both_used.Not()]) \
                    .OnlyEnforceIf(final.Not())
                diff_pair.append(final)
        model.AddBoolOr(diff_pair)

    # ── Objective: total race time in ms ───────────────────────────────
    # Stint time = sum_{lap=1..L} (base + (lap-1)*deg)
    #            = L*base + deg * L*(L-1)/2
    # We linearize by precomputing per-compound stint times for every L.
    max_L = total_laps
    stint_times = []  # stint_times[s] = chosen time for that stint
    for s in range(n_stints):
        # For each possible compound c and length L, the time is fixed.
        # Model as: time_s = sum_c sum_L  ind_{s,c,L} * T(c,L)
        time_s = model.NewIntVar(0, max_L * 200_000, f"time_{s}")
        terms = []
        ind_vars = []
        for c, comp in enumerate(COMPOUNDS):
            for L in range(0, min(comp.max_life, max_L) + 1):
                T = L * comp.base_lap_time_ms + comp.degradation_ms * (L * (L - 1) // 2)
                ind = model.NewBoolVar(f"ind_{s}_{c}_{L}")
                model.Add(compound[s] == c).OnlyEnforceIf(ind)
                model.Add(stint_len[s] == L).OnlyEnforceIf(ind)
                # If ind is false, at least one of the two differs (handled by exactly_one).
                terms.append(T * ind)
                ind_vars.append(ind)
        model.AddExactlyOne(ind_vars)
        model.Add(time_s == sum(terms))
        stint_times.append(time_s)

    # Number of pit stops = number of used stints - 1
    n_stops = sum(used) - 1
    total_time = sum(stint_times) + PIT_LOSS_MS * n_stops
    model.Minimize(total_time)

    # ── Solve ──────────────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.num_search_workers = 4
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": "infeasible"}

    stints = []
    current_lap = 0
    for s in range(n_stints):
        if solver.Value(used[s]):
            L = solver.Value(stint_len[s])
            c = COMPOUNDS[solver.Value(compound[s])]
            stints.append({
                "stint":    s + 1,
                "compound": c.name,
                "laps":     L,
                "start":    current_lap + 1,
                "end":      current_lap + L,
                "time_ms":  solver.Value(stint_times[s]),
            })
            current_lap += L

    return {
        "status":      "optimal" if status == cp_model.OPTIMAL else "feasible",
        "total_time_ms": solver.Value(total_time),
        "n_stops":     len(stints) - 1,
        "stints":      stints,
    }


def format_time(ms: int) -> str:
    s = ms / 1000.0
    m = int(s // 60)
    s -= m * 60
    return f"{m}:{s:06.3f}"


def main():
    print("F1 Pit Stop Strategy Optimizer")
    print("=" * 60)
    laps = 58  # e.g. Monaco GP
    print(f"Race length : {laps} laps")
    print(f"Pit loss    : {PIT_LOSS_MS / 1000:.1f} s per stop")
    print(f"Compounds   : {[c.name for c in COMPOUNDS]}\n")

    result = optimize(total_laps=laps, max_stops=3)
    if result["status"] == "infeasible":
        print("No feasible strategy found.")
        return

    print(f"Status      : {result['status'].upper()}")
    print(f"Total time  : {format_time(result['total_time_ms'])}")
    print(f"Pit stops   : {result['n_stops']}\n")
    print(f"{'Stint':>5} {'Compound':>10} {'Laps':>6} {'Range':>10} {'Time':>10}")
    print("-" * 50)
    for s in result["stints"]:
        rng = f"{s['start']}-{s['end']}"
        print(f"{s['stint']:>5} {s['compound']:>10} {s['laps']:>6} "
              f"{rng:>10} {format_time(s['time_ms']):>10}")


if __name__ == "__main__":
    main()
