"""Centralized logging utilities for the Enterprise Sales Analytics pipeline."""
import logging
import logging.config
import time
from typing import Any, Dict, Optional

from config import BASE_DIR


LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "pipeline.log"


def setup_logging(name: str = "enterprise_sales_analytics") -> logging.Logger:
    """Set up and return a configured logger."""
    config_dict = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "simple": {
                "format": "%(asctime)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "simple",
            },
            "file": {
                "class": "logging.FileHandler",
                "level": "DEBUG",
                "formatter": "detailed",
                "filename": str(LOG_FILE),
                "encoding": "utf-8",
            },
        },
        "loggers": {
            name: {
                "handlers": ["console", "file"],
                "level": "DEBUG",
                "propagate": False,
            },
        },
    }
    logging.config.dictConfig(config_dict)
    return logging.getLogger(name)


class PipelineTimer:
    """Context manager to track step duration."""

    def __init__(self, step_name: str, logger: Optional[logging.Logger] = None):
        self.step_name = step_name
        self.logger = logger or setup_logging()
        self.start_time: Optional[float] = None
        self.duration: Optional[float] = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        self.logger.info(f"Starting step: {self.step_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            self.duration = time.perf_counter() - self.start_time
        if exc_type is not None:
            self.logger.error(
                f"Failed step: {self.step_name} after {self.duration:.2f}s - {exc_type.__name__}: {exc_val}"
            )
            return False  # Re-raise the exception
        self.logger.info(f"Completed step: {self.step_name} in {self.duration:.2f}s")
        return True


def log_data_quality(check_name: str, passed: bool, details: Dict[str, Any], logger: Optional[logging.Logger] = None) -> None:
    """Log data quality check results."""
    logger = logger or setup_logging()
    status = "PASSED" if passed else "FAILED"
    logger.info(f"Data Quality Check [{check_name}]: {status} - {details}")
