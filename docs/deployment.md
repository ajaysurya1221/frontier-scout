# Deployment

## Local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
make demo
```

No model API key is required for the default demo.

## Docker

```bash
docker compose up --build
```

The compose stack includes the app, Qdrant, and an OpenTelemetry collector.
The required demo path still uses deterministic local retrieval so it remains
fast and reproducible.

The local collector binds OTLP receivers to `0.0.0.0` inside the demo network,
which is acceptable for the laptop compose profile. Production deployments
should bind receivers to an internal interface or localhost-forwarded endpoint,
enable the collector's localhost feature gate when appropriate, and place any
public ingress behind normal network policy and authentication.
