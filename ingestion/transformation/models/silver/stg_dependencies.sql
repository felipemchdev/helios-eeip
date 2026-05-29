with raw as (
    select *
    from read_json_auto('az://bronze/raw/deps_dev/*/*.json', ignore_errors=true)
),

exploded as (
    select
        versionKey.name::varchar as root_package,
        versionKey.system::varchar as root_ecosystem,
        try_cast(ingested_at as timestamp) as ingested_at,
        date(try_cast(ingested_at as timestamp)) as ingestion_date,
        dep_node
    from raw,
    unnest(coalesce(dependencies.nodes, [])) as t(dep_node)
),

normalized as (
    select
        root_package,
        root_ecosystem,
        dep_node.versionKey.name::varchar as dep_name,
        dep_node.versionKey.version::varchar as dep_version,
        dep_node.versionKey.system::varchar as dep_ecosystem,
        case
            when coalesce(dep_node.relation, '') ilike '%direct%'
                then 'DIRECT'
            else 'INDIRECT'
        end as relation_type,
        case
            when coalesce(dep_node.relation, '') ilike '%direct%'
                then true
            else false
        end as is_direct,
        ingested_at,
        ingestion_date
    from exploded
),

ranked as (
    select
        *,
        row_number() over (
            partition by root_package, dep_name, dep_version, ingestion_date
            order by ingested_at desc nulls last
        ) as rn
    from normalized
)

select
    root_package,
    root_ecosystem,
    dep_name,
    dep_version,
    dep_ecosystem,
    relation_type,
    is_direct,
    ingested_at,
    ingestion_date,
    current_timestamp as dbt_updated_at
from ranked
where rn = 1
