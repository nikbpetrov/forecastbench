# test_question_set_io.py

- **From:** `src/tests/orchestration/test_question_set_io.py`
- **To:** `src/tests/integration/test_question_set_io.py`
- **Level/technique:** integration — real `_io` question-set readers; `_io.urlopen` (network) mocked; local-file reads to a temp tree.
- **Processing:** moved. Kept: raw/local read, latest-metadata symlink, path-escape validation, JSON-error passthrough, dataframe reader.
- **Relocated → `contract/`:** `test_raw_question_set_readers_do_not_require_gitpython` (packaging/dependency contract) → `contract/test_deploy_staging.py`; the now-unused module-level `ROOT`/list/`Path` import were removed.
