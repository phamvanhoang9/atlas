import pytest
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.config.config import Config, ConfigError

@pytest.fixture
def temp_config_file():
    config_data = {
        "retriever": "tavily",
        "llm_model": "custom_model",
        "token_limit": 5000
    }
    config_file = Path(__file__).with_name("_tmp_config.json")
    config_file.write_text(json.dumps(config_data), encoding="utf-8")
    try:
        yield str(config_file)
    finally:
        config_file.unlink(missing_ok=True)

def test_config_from_file(temp_config_file):
    config = Config(config_file=temp_config_file)
    assert config.retriever == "tavily"
    assert config.llm_model == "custom_model"
    assert config.token_limit == 5000

def test_default_config_file_is_optional():
    config = Config()
    assert config.retriever == "tavily"
    assert config.llm_model == "gpt-4o-mini"
    assert config.enable_evaluation is False
    assert config.evaluation_mode == "online"
    assert config.eval_top_k == 3

def test_explicit_missing_config_file_raises():
    with pytest.raises(FileNotFoundError):
        Config(config_file="non_existent.json")

@patch.dict(os.environ, {"RETRIEVER": "tavily", "TOKEN_LIMIT": "9999"})
def test_config_env_vars():
    # Mock open to avoid FileNotFoundError
    with patch("os.path.exists", return_value=True), patch("builtins.open", MagicMock()):
        with patch("json.load", return_value={}):
            config = Config(config_file="non_existent.json")
            assert config.retriever == "tavily"
            assert config.token_limit == 9999

@patch.dict(
    os.environ,
    {
        "ENABLE_EVALUATION": "true",
        "EVALUATION_MODE": "both",
        "EVAL_TOP_K": "5",
        "EVAL_FAIL_THRESHOLDS": '{"min_faithfulness": 0.9}',
    },
)
def test_evaluation_config_env_vars():
    with patch("os.path.exists", return_value=True), patch("builtins.open", MagicMock()):
        with patch("json.load", return_value={}):
            config = Config(config_file="non_existent.json")
            assert config.enable_evaluation is True
            assert config.evaluation_mode == "both"
            assert config.eval_top_k == 5
            assert config.eval_fail_thresholds["min_faithfulness"] == 0.9

def test_apply_mode_config():
    with patch("os.path.exists", return_value=True), patch("builtins.open", MagicMock()):
        with patch("json.load", return_value={}):
            config = Config()
            
            # Test 'hỏi đáp' mode
            config.apply_mode_config("hỏi đáp")
            assert config.max_iterations == 1
            assert config.total_words == 700
            
            # Test 'phân tích' mode
            config.apply_mode_config("phân tích")
            assert config.max_iterations == 5
            assert config.total_words == 3000

def test_invalid_config_value_raises_config_error():
    with patch("os.path.exists", return_value=True), patch("builtins.open", MagicMock()):
        with patch("json.load", return_value={"token_limit": 999999}):
            with pytest.raises(ConfigError):
                Config()

@patch.dict(os.environ, {"REQUIRE_API_KEYS": "true"}, clear=True)
def test_required_secrets_validation():
    with patch("os.path.exists", return_value=True), patch("builtins.open", MagicMock()):
        with patch("json.load", return_value={}):
            with pytest.raises(ConfigError) as excinfo:
                Config()

    assert "OPENAI_API_KEY" in str(excinfo.value)
    assert "TAVILY_API_KEY" in str(excinfo.value)

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("RETRIEVER", raising=False)
    monkeypatch.delenv("TOKEN_LIMIT", raising=False)
    monkeypatch.delenv("CONFIG_FILE", raising=False)
    monkeypatch.delenv("REQUIRE_API_KEYS", raising=False)
    monkeypatch.delenv("ENABLE_EVALUATION", raising=False)
    monkeypatch.delenv("EVALUATION_MODE", raising=False)
    monkeypatch.delenv("EVAL_TOP_K", raising=False)
    monkeypatch.delenv("EVAL_FAIL_THRESHOLDS", raising=False)
