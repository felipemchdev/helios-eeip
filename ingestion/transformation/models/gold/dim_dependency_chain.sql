with deps as (
    select * from {{ ref('stg_dependencies') }}
),
dep_advs as (
    select * from {{ ref('stg_dependency_advisories') }}
),
advs as (
    select * from {{ ref('stg_advisories') }}
),
joined as (
    select
        d.root_package,
        d.root_ecosystem,
        d.dep_name,
        d.dep_version,
        d.dep_ecosystem,
        d.relation_type,
        d.is_direct,
        a.advisory_id,
        a.cve_id,
        a.title,
        a.severity,
        a.cvss3_score
    from deps d
    left join dep_advs da
        on d.root_package = da.root_package
        and d.dep_name = da.dep_name
        and d.dep_version = da.dep_version
    left join advs a
        on da.advisory_id = a.advisory_id
)
select * from joined
