.PHONY: install sources demo xm drought investment test lint workflow
install:
	python -m pip install -e '.[workflow,climate,dev]'
sources:
	python scripts/bootstrap_sources.py
demo: sources
	pypsa-col run --config config/demo.yaml
xm: sources
	pypsa-col run --config config/xm-example.yaml
drought: sources
	pypsa-col run --config config/el-nino.yaml
investment: sources
	pypsa-col run --config config/investment2030.yaml
test:
	pytest -q
lint:
	ruff check src scripts tests
workflow:
	snakemake -s workflow/Snakefile --config study=config/demo.yaml --cores 2
