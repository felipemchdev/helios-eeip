-- Resolves parent → child relationships using the edges array.
-- edges[].fromNode and toNode are 0-based indices into nodes[].
-- DuckDB arrays are 1-based so we add +1 when accessing by index.
with raw as (
    select *
    from read_json_auto('az://bronze/raw/deps_dev/*/*.json')
),

edges_unnested as (
    select
        versionKey.name::varchar                    as root_package,
        versionKey.system::varchar                  as root_ecosystem,
        try_cast(ingested_at as timestamp)          as ingested_at,
        date(try_cast(ingested_at as timestamp))    as ingestion_date,
        e.fromNode::integer                         as from_idx,
        e.toNode::integer                           as to_idx,
        e.requirement::varchar                      as requirement_constraint,
        dependencies.nodes                          as all_nodes
    from raw,
    unnest(coalesce(dependencies.edges, [])) as t(e)
),

resolved as (
    select
        root_package,
        root_ecosystem,
        ingested_at,
        ingestion_date,
        requirement_constraint,
        -- parent dep (fromNode)
        all_nodes[from_idx + 1].versionKey.name::varchar    as parent_dep_name,
        all_nodes[from_idx + 1].versionKey.version::varchar as parent_dep_version,
        all_nodes[from_idx + 1].relation::varchar           as parent_relation,
        -- child dep (toNode)
        all_nodes[to_idx + 1].versionKey.name::varchar      as dep_name,
        all_nodes[to_idx + 1].versionKey.version::varchar   as dep_version,
        all_nodes[to_idx + 1].versionKey.system::varchar    as dep_ecosystem,
        all_nodes[to_idx + 1].relation::varchar             as relation_type
    from edges_unnested
),

ranked as (
    select
        *,
        row_number() over (
            partition by root_package, parent_dep_name, dep_name, dep_version, ingestion_date
            order by ingested_at desc nulls last
        ) as rn
    from resolved
    -- exclude self-referencing edges
    where parent_dep_name != dep_name or parent_dep_version != dep_version
)

select
    root_package,
    root_ecosystem,
    parent_dep_name,
    parent_dep_version,
    parent_relation,
    dep_name,
    dep_version,
    dep_ecosystem,
    relation_type,
    requirement_constraint,
    ingested_at,
    ingestion_date,
    current_timestamp as dbt_updated_at
from ranked
where rn = 1
