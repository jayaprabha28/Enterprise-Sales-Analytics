"""Automated tests for enhanced functionality."""
import sys
from pathlib import Path

sys.path.insert(0, "src")


def test_logger_module():
    from logger import setup_logging, PipelineTimer
    logger = setup_logging("test")
    assert logger is not None
    assert hasattr(logger, "info")


def test_data_quality_module():
    from data_quality import validate_schema
    import pandas as pd
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    ok, details = validate_schema(df, ["a", "b"])
    assert ok
    ok2, details2 = validate_schema(df, ["a", "c"])
    assert not ok2


def test_mongo_integration_disabled_by_default():
    from mongo_integration import MongoConfig, MongoIntegration
    cfg = MongoConfig()
    assert cfg.enabled is False  # Default is false
    mongo = MongoIntegration(cfg)
    assert mongo.is_enabled() is False


def test_mongo_config_from_env(monkeypatch):
    import os
    from mongo_integration import MongoConfig
    monkeypatch.setenv("MONGODB_ENABLED", "true")
    monkeypatch.setenv("MONGODB_URI", "mongodb://test:27017")
    monkeypatch.setenv("MONGODB_DB", "test_db")
    cfg = MongoConfig()
    assert cfg.enabled is True
    assert cfg.db_name == "test_db"


def test_ml_evaluation_module():
    from ml_evaluation import evaluate_classification
    import numpy as np
    y_true = np.array([0, 1, 1, 0])
    y_pred = np.array([0, 1, 0, 0])
    y_proba = np.array([0.2, 0.8, 0.4, 0.1])
    metrics = evaluate_classification(y_true, y_pred, y_proba)
    assert "accuracy" in metrics
    assert "precision" in metrics
    assert "recall" in metrics
    assert "f1" in metrics
    assert "roc_auc" in metrics
