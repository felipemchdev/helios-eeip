

with deps as (
    select
        root_package,
        root_ecosystem,
        dep_name,
        dep_version,
        dep_ecosystem,
        is_direct
    from "eeip"."main_silver"."stg_dependencies"
),

pkgs as (
    select
        package_name,
        ecosystem,
        version,
        advisory_count
    from "eeip"."main_silver"."stg_packages"
),

joined as (
    select
        d.root_package,
        d.root_ecosystem,
        d.dep_name,
        d.dep_version,
        d.dep_ecosystem,
        d.is_direct,
        coalesce(p.advisory_count, 0) as advisory_count
    from deps d
    left join pkgs p
        on d.dep_name = p.package_name
        and d.dep_version = p.version
        and d.dep_ecosystem = p.ecosystem
),

aggregated as (
    select
        root_package,
        root_ecosystem,
        sum(case when is_direct then 1 else 0 end)::integer as direct_dep_count,
        sum(case when not is_direct then 1 else 0 end)::integer as transitive_dep_count,
        count(*)::integer as total_dep_count,
        sum(advisory_count)::integer as total_advisory_exposure,
        sum(case when advisory_count > 0 then 1 else 0 end)::integer as critical_dep_count
    from joined
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