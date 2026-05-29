FROM apache/airflow:2.9.3-python3.11

ENV AIRFLOW__CORE__EXECUTOR=SequentialExecutor
ENV AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=sqlite:////tmp/airflow.db
ENV AIRFLOW__CORE__LOAD_EXAMPLES=False
ENV _AIRFLOW_WWW_USER_USERNAME=admin
ENV _AIRFLOW_WWW_USER_PASSWORD=admin123

USER root
RUN mkdir -p /opt/dbt && chown -R airflow /opt/dbt

USER airflow

RUN pip install --no-cache-dir \
    azure-storage-file-datalake \
    azure-identity \
    requests \
    dbt-duckdb==1.7.4

COPY orchestration/dags/ /opt/airflow/dags/
COPY transformation/ /opt/dbt/transformation/

CMD ["airflow", "standalone"]