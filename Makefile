.PHONY: setup demo test coverage audit ci type lint

setup:
	python -m pip install -e ".[dev]"

# `demo` compiles the bundled sample policy in a throwaway dir, offline (no keys,
# no network), then runs doctor over the result. Leaves the working tree clean.
demo:
	@tmp=$$(mktemp -d); cp examples/sample-repo/frontier-scout.policy.json $$tmp/; \
	 frontier-scout agent compile --repo $$tmp >/dev/null; \
	 frontier-scout doctor --repo $$tmp; rm -rf $$tmp

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q

coverage:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 coverage run --source=frontier_scout -m pytest -q -m "not live"
	coverage report --fail-under=80

audit:
	python -m pip_audit --progress-spinner off --requirement requirements.txt
	bandit -q -r frontier_scout

lint:
	ruff check frontier_scout tests

type:
	mypy

ci: lint type test coverage audit
