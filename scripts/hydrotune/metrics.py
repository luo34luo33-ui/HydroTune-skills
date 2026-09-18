"""HydroTune deterministic model performance metrics."""

from __future__ import annotations
import math
import numpy as np


def metrics(observed: np.ndarray, simulated: np.ndarray) -> dict[str, float]:
    valid=np.isfinite(observed)&np.isfinite(simulated); obs,sim=observed[valid],simulated[valid]
    if len(obs)<2: return {}
    mean=np.mean(obs); denominator=np.sum((obs-mean)**2); nse=float(1-np.sum((sim-obs)**2)/denominator) if denominator else math.nan
    corr=float(np.corrcoef(obs,sim)[0,1]) if np.std(obs) and np.std(sim) else math.nan; alpha=np.std(sim,ddof=1)/np.std(obs,ddof=1) if np.std(obs,ddof=1) else math.nan; beta=np.mean(sim)/mean if mean else math.nan
    kge=float(1-math.sqrt((corr-1)**2+(alpha-1)**2+(beta-1)**2)) if all(np.isfinite([corr,alpha,beta])) else math.nan
    return {"n":int(len(obs)),"KGE":kge,"NSE":nse,"RMSE":float(np.sqrt(np.mean((sim-obs)**2))),"MAE":float(np.mean(np.abs(sim-obs))),"PBIAS":float(100*(np.sum(sim)-np.sum(obs))/np.sum(obs)) if np.sum(obs) else math.nan}
