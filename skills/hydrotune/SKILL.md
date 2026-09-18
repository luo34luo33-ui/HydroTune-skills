---
name: hydrotune
description: Orchestrate an established HydroTune rainfall-runoff workflow by selecting compatible intake, analysis, modeling, calibration, and diagnosis skills. Use for multi-step basin studies.
---

# HydroTune workflow router

Use the smallest set of component skills that answers the request. Read each input `result.json` before continuing; stop on `error`. Preserve the three-artifact protocol and do not reproduce domain calculations in orchestration.

Typical flow: Intake -> Analysis -> Modeling -> optional Calibration -> Diagnosis. Calibration and diagnosis require a runnable model and meaningful observed-simulated overlap.

Before moving from one stage to the next, inspect the current artifacts for required questions, unavailable diagnostics, readiness gaps, or multiple plausible downstream choices. Ask the user only for decisions that materially affect the next computation, but do not silently convert recommendations or inferred metadata into confirmed inputs. Good questions state the evidence, why it matters, and which CLI option or artifact field the answer will control.

Use `compare` for Tank/HBV/XAJ selection and BMA. Before running it, require the user to choose one built-in optimizer (`de`, `pso`, `ga`, `sce`, or `two_stage`); pass that same choice to every model. Validation ranks models, while ensemble weights use calibration results. For event collections, derive each split's metrics from the arithmetic mean of separately calculated per-event metrics, not from pooled event samples. When upstream discharge is confirmed, preserve each calibrated Muskingum K/X through validation and BMA artifacts.
