## Agent policy (advisory — Frontier Scout emits this; it does not enforce it)

> Advisory — Frontier Scout emits this guidance from a static repo scan; it does not enforce it at runtime. Treat it as a review aid, not a control.

### Allowed tools
- (none)

### Blocked tools
- (none)

### Blocked shell commands
- rm -rf
- sudo
- chmod 777
- git push --force
- git push -f
- curl | sh
- curl | bash
- wget | sh
- eval
- :(){
- mkfs
- dd if=
- > /dev/sda

### Protected paths
- **/.env
- **/.env.*
- **/*.pem
- **/*.key
- **/id_rsa
- **/credentials*
- **/.npmrc
- **/.pypirc
- **/secrets/**
- .github/workflows/**
- **/migrations/**
- **/alembic/**
- infra/**
- deploy/**
- **/*.tf
- **/k8s/**
- **/helm/**
- **/Dockerfile
- **/docker-compose*.y*ml
- **/.env*
- Dockerfile
- migrations/**

### MCP server allowlist
- (none)

### Approval gates
- network
- shell
- credential
- write
- protected-path
- ci
- deploy

### Required checks
- pytest
- ruff check .
