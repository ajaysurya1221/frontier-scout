.PHONY: setup demo test coverage eval audit ci type lint

setup:
	python -m pip install -e ".[dev]"

demo:
	frontier-scout incident demo

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q

coverage:
	coverage run --source=frontier_scout/platform/authz,frontier_scout/platform/orchestration,frontier_scout/platform/context,frontier_scout/platform/retrieval -m pytest -q tests/test_platform_authz.py tests/test_platform_retrieval.py tests/test_platform_context_gateway.py tests/test_platform_orchestration_tools.py tests/test_incident_change_scout.py
	coverage report --fail-under=80

eval:
	python -m frontier_scout.platform.incident_change_scout.cli_eval

audit:
	python -m pip_audit --progress-spinner off --requirement requirements.txt
	bandit -q -r frontier_scout/platform

lint:
	ruff check frontier_scout/platform tests/test_platform_authz.py tests/test_platform_retrieval.py tests/test_platform_context_gateway.py tests/test_platform_orchestration_tools.py tests/test_incident_change_scout.py

type:
	mypy

ci: lint type test coverage eval audit demo
