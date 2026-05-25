FROM python:3.11-slim

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -e ".[dev]"

CMD ["frontier-scout", "incident", "demo", "--output", ".scratch/incident-demo"]
