# Data quality rules

An inference is allowed only when observable column names, values, or file structure support it. Store the inference, confidence, and evidence in `dataset.json`. Do not infer a unit from a short variable name such as `Q`.

Errors stop downstream scientific computation: unparsable or missing timestamps, no recognized hydrologic variable, unresolved unit for a recognized variable, or unmet model input requirements. Missing samples, irregular intervals and possible outliers are warnings unless a caller has adopted stricter rules.
