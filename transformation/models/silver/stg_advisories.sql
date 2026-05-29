-- Advisory metadata from the deps.dev /advisories endpoint.
-- Saved by function_app.py to bronze/raw/advisories/*/*.json.
with raw as (
    select *
    from read_json_auto('az://bronze/raw/advisories/*/*.json', ignore_errors=true)
),

exploded as (
    select adv
    from raw,
    unnest(coalesce(advisories, [])) as t(adv)
),

normalized as (
    select
        adv.advisoryKey.id::varchar                 as advisory_id,
        -- Prefer CVE alias, fall back to GHSA id
        coalesce(
            list_filter(
                list_transform(coalesce(adv.aliases, []), x -> x::varchar),
                x -> x like 'CVE-%'
            )[1],
            adv.advisoryKey.id::varchar
        )                                           as cve_id,
        adv.title::varchar                          as title,
        try_cast(adv.cvss3Score as double)          as cvss3_score,
        -- Derive severity from CVSS score
        case
            when try_cast(adv.cvss3Score as double) >= 9.0 then 'CRITICAL'
            when try_cast(adv.cvss3Score as double) >= 7.0 then 'HIGH'
            when try_cast(adv.cvss3Score as double) >= 4.0 then 'MEDIUM'
            when try_cast(adv.cvss3Score as double) > 0    then 'LOW'
            else 'UNKNOWN'
        end                                           as severity,
        adv.advisoryKey.id::varchar                 as ghsa_id
    from exploded
    where adv.advisoryKey.id is not null
)

select distinct *
from normalized
