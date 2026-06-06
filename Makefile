.PHONY: setup demo test coverage audit ci type lint

setup:
	python -m pip install -e ".[dev]"

# `demo` runs the offline sanctioned-packs demo (no API keys, no network).
demo:
	frontier-scout demo --no-serve

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q

coverage:
	coverage run --source=frontier_scout/platform/authz,frontier_scout/platform/orchestration,frontier_scout/platform/context,frontier_scout/platform/retrieval -m pytest -q tests/test_platform_authz.py tests/test_platform_retrieval.py tests/test_platform_context_gateway.py tests/test_platform_orchestration_tools.py
	coverage report --fail-under=80

audit:
	python -m pip_audit --progress-spinner off --requirement requirements.txt
	bandit -q -r frontier_scout/platform

lint:
	ruff check frontier_scout/platform tests/test_platform_authz.py tests/test_platform_retrieval.py tests/test_platform_context_gateway.py tests/test_platform_orchestration_tools.py

type:
	mypy

ci: lint type test coverage audit demo
