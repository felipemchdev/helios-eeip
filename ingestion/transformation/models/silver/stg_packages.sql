with raw as (
    select *
    from read_json_auto('az://bronze/raw/deps_dev/*/*.json', ignore_errors=true)
),

normalized as (
    select
        versionKey.name::varchar as package_name,
        versionKey.system::varchar as ecosystem,
        versionKey.version::varchar as version,
        array_length(coalesce(advisoryKeys, []))::integer as advisory_count,
        list_transform(coalesce(licenses, []), x -> x::varchar) as license_names,
        try_cast(publishedAt as timestamp) as published_at,
        try_cast(ingested_at as timestamp) as ingested_at,
        current_timestamp as dbt_updated_at
    from raw
),

ranked as (
    select
        *,
        row_number() over (
            partition by package_name, ecosystem, version
            order by ingested_at desc nulls last
        ) as rn
    from normalized
)

select
    package_name,
    ecosystem,
    version,
    advisory_count,
    license_names,
    published_at,
    ingested_at,
    dbt_updated_at
from ranked
where rn = 1
