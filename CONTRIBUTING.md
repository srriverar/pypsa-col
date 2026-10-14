# Contributing

1. Install `pip install -e '.[workflow,climate,dev]'` and verify the source pin.
2. Run `ruff check src scripts tests`, `pytest -q`, and the demo Snakefile.
3. Keep new scientific changes small and provide an equation, unit convention,
   source citation and test. Do not replace official data with synthetic values
   merely to make a test/model run succeed.
4. Source updates must explicitly change the Git pin and SHA-256 lock after
   reviewing changes in geometry, parsers, schemas, licenses and model assumptions.
   Do not auto-track a mutable branch or patch the external snapshot invisibly.
5. Raw downloads stay raw; normalize into separate processed tables. Preserve
   missingness, entity identifiers, request windows and retrieval provenance.
6. Crosswalk changes need sources and review. A fuzzy name match is a suggestion,
   not authority for allocating MW, water or an official planning region.
7. Verify both temporal and spatial conservation after aggregation. Test vintage
   activity, reservoir energy, reverse flows and price-weight normalization when
   changing optimization code.
8. Document limitations and distinguish demo, hybrid and researcher-reviewed data.
   Keep present-tense geographic/commissioning claims tied to dated sources.
9. Never commit `.cdsapirc`, API tokens, private engineering exports or solver
   credentials. Check dataset terms and source licensing before public releases.

The included GitHub workflow is a CI definition, not a claim that remote CI has
already run. Delivery validation is recorded separately in docs/VALIDATION.md.
Discuss contribution credit with the project owner before assigning paper authorship.
