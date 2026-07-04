# Codex review — rounds 2 & 3 (gpt-5.5, xhigh, read-only)

## Round 2 (on PLAN v2)
**"Both push-backs accepted. The path table and e2e/golden design are sufficient."** →
**CHANGES REQUIRED** with 4 residual MUSTs:
1. Add the `test_smoke_test.py → unit/llm_forecaster/` mapping (only its subprocess assertion → contract).
2. Complete guard pruning: drop `test_constants.py`; drop the shared-run `__file__` assert; drop the
   identity `.model`-absence assert.
3. Preserve unique deploy contracts: manager `TEST_OR_PROD`, exact job names, leaderboard staging of
   `src/llm_forecaster`.
4. Move retained architecture/registry checks to `contract/`: top-level-import policy,
   future-annotations convention, provider coverage, active-model release-date coverage.

All 4 folded into PLAN v3 (§2, §4, §5, §9).

## Round 3 (on PLAN v3)
- r2-1 addressed; r2-3 addressed; r2-2 drops specified; r2-4 addressed.
- **AGREE on substance.** Residual = plan-consistency only: §2/§8 still relocated `test_constants.py`
  (now shown as DROP); §3 named `test_import_boundaries.py` (now `test_llm_forecaster_conventions.py`);
  stale v2/round-2 labels (now v3/agreed). All three fixed in PLAN v3. **Plan settled.**
