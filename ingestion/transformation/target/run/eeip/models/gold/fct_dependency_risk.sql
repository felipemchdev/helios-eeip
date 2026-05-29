create or replace view "eeip"."main_gold"."fct_dependency_risk__dbt_int" as (
        select * from 'az://gold/fct_dependency_risk/fct_dependency_risk.parquet'
    );