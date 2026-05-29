with raw as (
    select *
    from read_json_auto('az://bronze/raw/advisories/*/*.json', ignore_errors=true)
),

exploded as (
    select adv
    from raw,
    unnest(coalesce(advisories, [])) as a(adv)
),

normalized as (
    select
        adv.advisoryKey.id::varchar as advisory_id,
        coalesce(adv.aliases[1]::varchar, adv.advisoryKey.id::varchar) as cve_id,
        adv.title::varchar as title,
        try_cast(adv.cvss3Score as double) as cvss3_score,
        case
            when try_cast(adv.cvss3Score as double) >= 9.0 then 'CRITICAL'
            when try_cast(adv.cvss3Score as double) >= 7.0 then 'HIGH'
            when try_cast(adv.cvss3Score as double) >= 4.0 then 'MEDIUM'
            when try_cast(adv.cvss3Score as double) > 0 then 'LOW'
            else 'UNKNOWN'
        end as severity
    from exploded
)

select distinct *
from normalized
