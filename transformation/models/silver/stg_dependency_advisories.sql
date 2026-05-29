with raw as (
    select *
    from read_json_auto('az://bronze/raw/deps_dev/*/*.json')
),

exploded_deps as (
    select
        versionKey.name::varchar as root_package,
        versionKey.system::varchar as root_ecosystem,
        dep_node
    from raw,
    unnest(coalesce(dependencies.nodes, [])) as t(dep_node)
),

exploded_advs as (
    select
        root_package,
        root_ecosystem,
        dep_node.versionKey.name::varchar as dep_name,
        dep_node.versionKey.version::varchar as dep_version,
        dep_node.versionKey.system::varchar as dep_ecosystem,
        adv.id::varchar as advisory_id
    from exploded_deps,
    unnest(coalesce(dep_node.advisoryKeys, [])) as a(adv)
)

select distinct
    root_package,
    root_ecosystem,
    dep_name,
    dep_version,
    dep_ecosystem,
    advisory_id
from exploded_advs
