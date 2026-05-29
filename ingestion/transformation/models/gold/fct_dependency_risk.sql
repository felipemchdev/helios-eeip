with dim as (
    select * from {{ ref('dim_dependency_chain') }}
),

aggregated as (
    select
        root_package,
        root_ecosystem,
        count(distinct case when is_direct then dep_name end)::integer as direct_dep_count,
        count(distinct case when not is_direct then dep_name end)::integer as transitive_dep_count,
        count(distinct dep_name)::integer as total_dep_count,
        count(distinct advisory_id)::integer as total_advisory_exposure,
        count(distinct case when severity in ('CRITICAL', 'HIGH') then dep_name end)::integer as critical_dep_count
    from dim
    group by root_package, root_ecosystem
)

select
    root_package,
    root_ecosystem,
    direct_dep_count,
    transitive_dep_count,
    total_dep_count,
    total_advisory_exposure,
    critical_dep_count,
    case
        when total_dep_count = 0 then 0.0
        else total_advisory_exposure::double / total_dep_count::double
    end as risk_density,
    case
        when (case when total_dep_count = 0 then 0.0 else total_advisory_exposure::double / total_dep_count::double end) > 0.5 then 'HIGH'
        when (case when total_dep_count = 0 then 0.0 else total_advisory_exposure::double / total_dep_count::double end) > 0.1 then 'MEDIUM'
        else 'LOW'
    end as risk_level,
    current_timestamp as calculated_at
from aggregated
