"""Unit tests for the ``metadata/validate_questions`` LLM gate.

Same model-boundary pattern as the tagger: MOCK ``model_eval.get_response_from_model`` and assert
the parsing of its raw text — ``Classification: ok`` -> valid, ``flag`` -> invalid, a missing
``Classification:`` -> left unvalidated (``""``), and an ambiguous verdict -> default-valid. The
model's actual judgement is out of scope.
"""

from unittest.mock import patch

import pandas as pd

from metadata.validate_questions import main as validate


def _to_validate(rows):
    """Build a question frame with empty ``valid_question`` (the to-validate marker)."""
    df = pd.DataFrame(rows)
    df["valid_question"] = ""
    return df


def test_validate_parses_each_verdict():
    df = _to_validate(
        [
            {"id": "ok", "question": "Q-ok"},
            {"id": "flag", "question": "Q-flag"},
            {"id": "noclass", "question": "Q-noclass"},
            {"id": "ambiguous", "question": "Q-ambiguous"},
        ]
    )

    def fake_model(model_name, prompt, max_tokens=None):
        if "Q-ok" in prompt:
            return "Reasoning...\nClassification: ok"
        if "Q-flag" in prompt:
            return "Reasoning...\nClassification: flag"
        if "Q-noclass" in prompt:
            return "I have no verdict here."  # no 'Classification:' -> None -> left ""
        return "Classification: hmmm"  # ambiguous (neither ok nor flag) -> default True

    with patch.object(validate.model_eval, "get_response_from_model", side_effect=fake_model):
        out = validate.validate_questions(df)

    by_id = dict(zip(out["id"], out["valid_question"]))
    assert by_id["ok"] is True
    assert by_id["flag"] is False
    assert by_id["noclass"] == ""  # unparseable -> stays unvalidated (driver drops it)
    assert by_id["ambiguous"] is True


def test_model_error_defaults_to_valid():
    df = _to_validate([{"id": "boom", "question": "Q-boom"}])

    with patch.object(
        validate.model_eval, "get_response_from_model", side_effect=RuntimeError("API down")
    ):
        out = validate.validate_questions(df)

    assert out.loc[out["id"] == "boom", "valid_question"].iloc[0] is True
