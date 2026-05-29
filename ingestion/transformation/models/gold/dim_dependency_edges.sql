{{ config(materialized='table') }}

with edges as (
    select * from {{ ref('stg_dependency_edges') }}
),
dep_advs as (
    select * from {{ ref('stg_dependency_advisories') }}
),
advs as (
    select * from {{ ref('stg_advisories') }}
)
select
    e.root_package,
    e.root_ecosystem,
    e.parent_dep_name,
    e.parent_dep_version,
    e.parent_relation,
    e.dep_name,
    e.dep_version,
    e.dep_ecosystem,
    e.relation_type,
    e.requirement_constraint,
    a.advisory_id,
    a.cve_id,
    a.title,
    a.severity,
    a.cvss3_score
from edges e
left join dep_advs da
    on e.root_package = da.root_package
    and e.dep_name = da.dep_name
    and e.dep_version = da.dep_version
left join advs a
    on da.advisory_id = a.advisory_id
