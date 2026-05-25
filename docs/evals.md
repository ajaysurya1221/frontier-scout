# Evals

The Incident Change Scout eval lives in `evals/incident_change_scout/golden.json`.

Thresholds:

- Required terms must appear in the final answer.
- At least two citations must be bound to the answer.
- Overall score must be at least `0.8`.

Run:

```bash
make eval
```

The eval writes `.scratch/incident-eval/eval.json`.

