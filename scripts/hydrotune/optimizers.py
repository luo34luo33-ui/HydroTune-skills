"""HydroTune seeded optimizer orchestration runtime."""

from __future__ import annotations

from typing import Callable
import numpy as np
from scipy.optimize import differential_evolution, dual_annealing, minimize


def optimize(name: str, objective: Callable[[np.ndarray], float], bounds: list[tuple[float, float]], iterations: int, seed: int, config: dict | None = None) -> tuple[np.ndarray, float, list[dict]]:
    """Run a seeded minimizer and return the best vector, loss, and compact history."""
    config = config or {}; rng = np.random.default_rng(seed); name = name.lower(); history: list[dict] = []
    def record(x: np.ndarray, loss: float) -> None:
        history.append({"loss": float(loss), "parameters": [float(v) for v in x]})
    if name == "de":
        result = differential_evolution(objective, bounds, maxiter=iterations, seed=seed, popsize=int(config.get("pop_size", 15)), mutation=config.get("mutation_factor", .8), recombination=config.get("crossover_prob", .7), polish=True)
        record(result.x, result.fun); return result.x, float(result.fun), history
    if name == "two_stage":
        first = dual_annealing(objective, bounds, maxiter=max(1, iterations // 2), seed=seed, no_local_search=True)
        second = minimize(objective, first.x, method="L-BFGS-B", bounds=bounds, options={"maxiter": max(1, iterations)})
        result = second if second.fun <= first.fun else first; record(result.x, result.fun); return result.x, float(result.fun), history
    n, dim = int(config.get("pop_size", config.get("n_particles", max(20, 4 * len(bounds))))), len(bounds)
    low, high = np.array([b[0] for b in bounds]), np.array([b[1] for b in bounds])
    pop = rng.uniform(low, high, size=(n, dim)); values = np.array([objective(x) for x in pop]); best = pop[values.argmin()].copy(); best_loss = float(values.min())
    if name == "pso":
        velocity = np.zeros_like(pop); personal, personal_loss = pop.copy(), values.copy(); w, c1, c2 = config.get("w", .7), config.get("c1", 1.5), config.get("c2", 1.5)
        for _ in range(iterations):
            velocity = w * velocity + c1 * rng.random(pop.shape) * (personal - pop) + c2 * rng.random(pop.shape) * (best - pop); pop = np.clip(pop + velocity, low, high); values = np.array([objective(x) for x in pop])
            improved = values < personal_loss; personal[improved], personal_loss[improved] = pop[improved], values[improved]; idx = values.argmin()
            if values[idx] < best_loss: best, best_loss = pop[idx].copy(), float(values[idx])
            record(best, best_loss)
    elif name == "ga":
        mutation, crossover = config.get("mutation_rate", .1), config.get("crossover_rate", .8)
        for _ in range(iterations):
            ranked = pop[np.argsort(values)]; children = [ranked[0].copy()]
            while len(children) < n:
                a, b = ranked[rng.integers(0, n // 2)], ranked[rng.integers(0, n // 2)]; child = np.where(rng.random(dim) < crossover, a, b)
                child = np.where(rng.random(dim) < mutation, rng.uniform(low, high), child); children.append(np.clip(child, low, high))
            pop = np.asarray(children); values = np.array([objective(x) for x in pop]); idx = values.argmin()
            if values[idx] < best_loss: best, best_loss = pop[idx].copy(), float(values[idx])
            record(best, best_loss)
    elif name == "sce":
        for _ in range(iterations):
            ranked = pop[np.argsort(values)]; elite = ranked[: max(3, n // 3)]; trial = elite[rng.integers(len(elite))] + rng.random(dim) * (elite[rng.integers(len(elite))] - elite[rng.integers(len(elite))])
            worst = np.argmax(values); candidate = np.clip(trial, low, high); candidate_loss = objective(candidate)
            if candidate_loss < values[worst]: pop[worst], values[worst] = candidate, candidate_loss
            else: pop[worst], values[worst] = rng.uniform(low, high), objective(pop[worst])
            idx = values.argmin()
            if values[idx] < best_loss: best, best_loss = pop[idx].copy(), float(values[idx])
            record(best, best_loss)
    else: raise ValueError("unsupported optimizer; choose de, pso, ga, sce, or two_stage")
    return best, best_loss, history
