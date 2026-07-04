# test_constants.py  (root file)  —  DROPPED

- **From:** `src/tests/test_constants.py`  →  **deleted** (not relocated)
- **Reason:** the file's sole content (`test_logo_lookup_lives_with_leaderboard_code`) was three `not hasattr(constants, ...)` private-symbol-absence asserts. Per the agreed guard policy (Codex MUST-2 / AGENTS.md) it was pruned; its intent — logo lookup lives in the leaderboard, not `constants` — is already covered by the leaderboard `get_org_logo` tests (`unit/leaderboard/test_llm_identities.py`).
- **FLAG:** you had selected `test_constants` among the "clean-mapping" root files to fold. Because it carried no behavioral content, folding it = pruning it. Say the word to restore it verbatim under `unit/`.
