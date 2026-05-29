-- Flat dependency nodes per root package (direct + transitive).
-- The enriched payload from the ingestion function stores advisoryKeys
-- on each dep node after calling the version endpoint per dependency.
with raw as (
    select *
    from read_json_auto('az://bronze/raw/deps_dev/*/*.json')
),

exploded as (
    select
        versionKey.name::varchar                        as root_package,
        versionKey.system::varchar                      as root_ecosystem,
        try_cast(ingested_at as timestamp)              as ingested_at,
        date(try_cast(ingested_at as timestamp))        as ingestion_date,
        dep_node
    from raw,
    unnest(coalesce(dependencies.nodes, [])) as t(dep_node)
),

normalized as (
    select
        root_package,
        root_ecosystem,
        dep_node.versionKey.name::varchar               as dep_name,
        dep_node.versionKey.version::varchar            as dep_version,
        dep_node.versionKey.system::varchar             as dep_ecosystem,
        dep_node.relation::varchar                      as relation_raw,
        case
            when coalesce(dep_node.relation::varchar, '') ilike '%direct%' then 'DIRECT'
            when coalesce(dep_node.relation::varchar, '') ilike '%self%'   then 'SELF'
            else 'INDIRECT'
        end                                             as relation_type,
        case
            when coalesce(dep_node.relation::varchar, '') ilike '%direct%' then true
            else false
        end                                             as is_direct,
        -- advisoryKeys now populated by enrichment step in function_app.py
        list_transform(
            coalesce(dep_node.advisoryKeys, []),
            x -> x.id::varchar
        )                                               as advisory_ids,
        array_length(coalesce(dep_node.advisoryKeys, []))::integer as advisory_count,
        ingested_at,
        ingestion_date
    from exploded
    where coalesce(dep_node.relation::varchar, '') not ilike '%self%'
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
    advisory_ids,
    advisory_count,
    ingested_at,
    ingestion_date,
    current_timestamp as dbt_updated_at
from ranked
where rn = 1
