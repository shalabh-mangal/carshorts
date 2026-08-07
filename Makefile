# Convenience targets. The pre-push git hook is the real guard (.githooks/pre-push);
# these mirror it for manual runs and one-time setup. `make` is optional — on a box
# without it, run the underlying commands directly (see each recipe).
PY ?= python

.PHONY: check lint test install-hooks

## check: run exactly what CI runs — whole-repo ruff + full pytest
check: lint test

lint:
	$(PY) -m ruff check .

test:
	$(PY) -m pytest -q

## install-hooks: point git at the committed hooks so pre-push runs `make check`
install-hooks:
	git config core.hooksPath .githooks
	@echo "pre-push guard active (bypass a single push with: git push --no-verify)"
