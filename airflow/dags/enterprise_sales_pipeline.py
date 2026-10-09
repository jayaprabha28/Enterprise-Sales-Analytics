"""Airflow DAG for Enterprise Sales Analytics pipeline (optional).

This is a reference DAG for scheduled execution. The existing Python scripts
remain the canonical way to run the pipeline.
"""
try:
    from datetime import datetime, timedelta
    from airflow import DAG
    from airflow.operators.bash import BashOperator
    AIRFLOW_AVAILABLE = True
except ImportError:
    AIRFLOW_AVAILABLE = False


if AIRFLOW_AVAILABLE:
    default_args = {
        "owner": "data-engineering",
        "depends_on_past": False,
        "start_date": datetime(2026, 1, 1),
        "email_on_failure": False,
        "email_on_retry": False,
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    }

    dag = DAG(
        "enterprise_sales_analytics_pipeline",
        default_args=default_args,
        description="End-to-end Enterprise Sales Analytics pipeline",
        schedule_interval=None,  # Manual trigger by default
        catchup=False,
        tags=["analytics", "sales", "ml"],
    )

    project_dir = "E:/enterprise-sales-analytics"

    data_cleaning = BashOperator(
        task_id="data_cleaning",
        bash_command=f"cd {project_dir} && python src/data_cleaning.py",
        dag=dag,
    )

    feature_engineering = BashOperator(
        task_id="feature_engineering",
        bash_command=f"cd {project_dir} && python src/feature_engineering.py",
        dag=dag,
    )

    load_postgres = BashOperator(
        task_id="load_postgres",
        bash_command=f"cd {project_dir} && python src/load_postgres.py",
        dag=dag,
    )

    run_sql = BashOperator(
        task_id="run_sql",
        bash_command=f"cd {project_dir} && python src/run_sql.py",
        dag=dag,
    )

    eda = BashOperator(
        task_id="eda",
        bash_command=f"cd {project_dir} && python src/eda.py",
        dag=dag,
    )

    segmentation = BashOperator(
        task_id="segmentation",
        bash_command=f"cd {project_dir} && python src/segmentation.py",
        dag=dag,
    )

    churn_model = BashOperator(
        task_id="churn_model",
        bash_command=f"cd {project_dir} && python src/churn_model.py",
        dag=dag,
    )

    forecasting = BashOperator(
        task_id="forecasting",
        bash_command=f"cd {project_dir} && python src/forecasting.py",
        dag=dag,
    )

    analytics = BashOperator(
        task_id="analytics",
        bash_command=f"cd {project_dir} && python src/analytics.py",
        dag=dag,
    )

    recommendation_engine = BashOperator(
        task_id="recommendation_engine",
        bash_command=f"cd {project_dir} && python src/recommendation_engine.py",
        dag=dag,
    )

    export_powerbi = BashOperator(
        task_id="export_powerbi",
        bash_command=f"cd {project_dir} && python src/export_powerbi.py",
        dag=dag,
    )

    data_cleaning >> feature_engineering >> load_postgres >> run_sql >> eda
    eda >> segmentation >> churn_model >> forecasting >> analytics
    analytics >> recommendation_engine >> export_powerbi
else:
    dag = None
