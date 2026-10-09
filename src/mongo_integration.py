"""Optional MongoDB integration for Enterprise Sales Analytics.

PostgreSQL remains the primary analytics database. MongoDB is used to store
flexible documents like logs, insights, model predictions, and metadata.
Integration can be enabled/disabled via configuration; failures won't break
the core pipeline.
"""
import os
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from pymongo import MongoClient, UpdateOne
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False

from config import PROCESSED_DIR
from logger import setup_logging


logger = setup_logging("mongo_integration")


class MongoConfig:
    def __init__(self):
        self.uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.db_name = os.getenv("MONGODB_DB", "enterprise_sales_analytics")
        self.enabled = os.getenv("MONGODB_ENABLED", "false").lower() in ("true", "1", "yes", "y")


class MongoIntegration:
    def __init__(self, config: Optional[MongoConfig] = None):
        self.config = config or MongoConfig()
        self.client = None
        self.db = None
        self._connected = False

    def is_enabled(self) -> bool:
        return self.config.enabled and PYMONGO_AVAILABLE

    def connect(self) -> bool:
        if not self.is_enabled():
            logger.info("MongoDB integration disabled or pymongo not available")
            return False
        try:
            self.client = MongoClient(self.config.uri, serverSelectionTimeoutMS=5000)
            self.client.admin.command("ping")
            self.db = self.client[self.config.db_name]
            self._connected = True
            logger.info(f"Connected to MongoDB: {self.config.db_name}")
            return True
        except Exception as e:
            logger.warning(f"MongoDB connection failed: {e}")
            self._connected = False
            return False

    def close(self):
        if self.client:
            self.client.close()
            self._connected = False

    def insert_pipeline_run(self, run_data: Dict[str, Any], prevent_duplicates: bool = True) -> Optional[str]:
        if not self._connected:
            return None
        try:
            coll = self.db["pipeline_runs"]
            if prevent_duplicates and "run_id" in run_data:
                existing = coll.find_one({"run_id": run_data["run_id"]})
                if existing:
                    logger.info(f"Pipeline run {run_data['run_id']} already exists, skipping")
                    return str(existing["_id"])
            run_data["timestamp"] = run_data.get("timestamp", datetime.utcnow())
            result = coll.insert_one(run_data)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to insert pipeline run: {e}")
            return None

    def sync_customer_insights(self, customer_data: List[Dict]) -> int:
        if not self._connected or not customer_data:
            return 0
        try:
            coll = self.db["customer_insights"]
            operations = []
            for c in customer_data:
                if "customer_id" not in c:
                    continue
                operations.append(
                    UpdateOne(
                        {"customer_id": c["customer_id"]},
                        {"$set": {**c, "synced_at": datetime.utcnow()}},
                        upsert=True,
                    )
                )
            if operations:
                result = coll.bulk_write(operations)
                logger.info(f"Synced {result.upserted_count + result.modified_count} customer insights")
                return result.upserted_count + result.modified_count
            return 0
        except Exception as e:
            logger.error(f"Failed to sync customer insights: {e}")
            return 0

    def log_model_prediction(self, prediction_data: Dict[str, Any]) -> Optional[str]:
        if not self._connected:
            return None
        try:
            coll = self.db["model_predictions"]
            prediction_data["timestamp"] = datetime.utcnow()
            result = coll.insert_one(prediction_data)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to log model prediction: {e}")
            return None

    def log_recommendation(self, rec_data: Dict[str, Any]) -> Optional[str]:
        if not self._connected:
            return None
        try:
            coll = self.db["recommendation_logs"]
            rec_data["timestamp"] = datetime.utcnow()
            result = coll.insert_one(rec_data)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to log recommendation: {e}")
            return None


def run_sync():
    """Sync key analytical results to MongoDB if enabled."""
    mongo = MongoIntegration()
    if not mongo.connect():
        return {"status": "SKIPPED", "reason": "MongoDB not available or disabled"}

    results = {}
    try:
        import pandas as pd

        cust_path = PROCESSED_DIR / "customer_features.csv"
        if cust_path.exists():
            df = pd.read_csv(cust_path)
            results["customer_insights"] = mongo.sync_customer_insights(df.to_dict("records"))
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        results["error"] = str(e)

    mongo.close()
    return {"status": "DONE", "results": results}


if __name__ == "__main__":
    print(json.dumps(run_sync(), indent=2))
