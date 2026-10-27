-- Smart Waste Management & Collection Analytics
-- PostgreSQL queries against the operational schema.
-- All rates are observed development-data metrics, not official standards.

-- 1. Rank wards by reported waste (the HAVING clause excludes empty wards).
WITH ward_waste AS (
    SELECT
        mw.ward_id,
        mw.ward_number,
        mw.ward_name,
        mw.population,
        COUNT(wr.report_id) AS report_count,
        SUM(wr.quantity_kg) AS total_waste_kg,
        AVG(wr.quantity_kg) AS average_kg_per_report
    FROM municipal_wards AS mw
    JOIN areas AS a ON a.ward_id = mw.ward_id
    JOIN waste_reports AS wr ON wr.area_id = a.area_id
    GROUP BY mw.ward_id, mw.ward_number, mw.ward_name, mw.population
    HAVING COUNT(wr.report_id) > 0
)
SELECT *,
    RANK() OVER (ORDER BY total_waste_kg DESC) AS waste_rank,
    DENSE_RANK() OVER (ORDER BY total_waste_kg DESC) AS dense_waste_rank
FROM ward_waste
ORDER BY waste_rank, ward_id;

-- 2. Collection efficiency by ward. Requests are joined through report/area
-- so unstaffed reports do not appear as implicit uncollected requests.
SELECT
    mw.ward_id,
    mw.ward_number,
    mw.ward_name,
    COUNT(cr.request_id) AS requests,
    COUNT(cr.request_id) FILTER (WHERE cr.status = 'COLLECTED') AS collected,
    ROUND(
        100.0 * COUNT(cr.request_id) FILTER (WHERE cr.status = 'COLLECTED')
        / NULLIF(COUNT(cr.request_id), 0),
        2
    ) AS collection_efficiency_pct
FROM municipal_wards AS mw
LEFT JOIN areas AS a ON a.ward_id = mw.ward_id
LEFT JOIN waste_reports AS wr ON wr.area_id = a.area_id
LEFT JOIN collection_requests AS cr ON cr.report_id = wr.report_id
GROUP BY mw.ward_id, mw.ward_number, mw.ward_name
ORDER BY collection_efficiency_pct NULLS FIRST;

-- 3. High waste with poor collection (eligible wards have requests).
WITH ward_operations AS (
    SELECT
        mw.ward_id,
        mw.ward_number,
        mw.ward_name,
        COALESCE(w.total_waste_kg, 0) AS total_waste_kg,
        COALESCE(c.request_count, 0) AS request_count,
        COALESCE(c.collected_count, 0) AS collected_count
    FROM municipal_wards AS mw
    LEFT JOIN (
        SELECT a.ward_id, SUM(wr.quantity_kg) AS total_waste_kg
        FROM areas AS a
        JOIN waste_reports AS wr ON wr.area_id = a.area_id
        GROUP BY a.ward_id
    ) AS w ON w.ward_id = mw.ward_id
    LEFT JOIN (
        SELECT a.ward_id,
            COUNT(cr.request_id) AS request_count,
            COUNT(cr.request_id) FILTER (WHERE cr.status = 'COLLECTED') AS collected_count
        FROM areas AS a
        JOIN waste_reports AS wr ON wr.area_id = a.area_id
        JOIN collection_requests AS cr ON cr.report_id = wr.report_id
        GROUP BY a.ward_id
    ) AS c ON c.ward_id = mw.ward_id
),
city_baseline AS (
    SELECT AVG(total_waste_kg) AS average_ward_waste_kg
    FROM ward_operations
)
SELECT
    o.*,
    ROUND(100.0 * collected_count / NULLIF(request_count, 0), 2)
        AS collection_efficiency_pct
FROM ward_operations AS o
CROSS JOIN city_baseline AS b
WHERE o.total_waste_kg > b.average_ward_waste_kg
  AND o.request_count > 0
  AND 100.0 * o.collected_count / NULLIF(o.request_count, 0) < 80
ORDER BY o.total_waste_kg DESC;

-- 4. Good segregation rate and mean rating by ward, using ratings with
-- their corresponding completed collection reports only.
SELECT
    mw.ward_id,
    mw.ward_number,
    COUNT(sr.rating_id) AS rating_count,
    ROUND(AVG(sr.rating)::numeric, 2) AS average_rating,
    ROUND(
        100.0 * COUNT(sr.rating_id) FILTER (WHERE sr.rating IN (4, 5))
        / NULLIF(COUNT(sr.rating_id), 0),
        2
    ) AS good_segregation_rate_pct
FROM municipal_wards AS mw
LEFT JOIN areas AS a ON a.ward_id = mw.ward_id
LEFT JOIN waste_reports AS wr ON wr.area_id = a.area_id
LEFT JOIN collection_requests AS cr
    ON cr.report_id = wr.report_id AND cr.status = 'COLLECTED'
LEFT JOIN segregation_ratings AS sr
    ON sr.request_id = cr.request_id
   AND sr.citizen_id = wr.citizen_id
   AND sr.worker_id = cr.worker_id
GROUP BY mw.ward_id, mw.ward_number
ORDER BY good_segregation_rate_pct NULLS FIRST;

-- 5. Complaint rate per 100 reports and unresolved complaint count.
WITH ward_counts AS (
    SELECT
        mw.ward_id,
        mw.ward_number,
        COUNT(DISTINCT wr.report_id) AS reports,
        COUNT(DISTINCT c.complaint_id) AS complaints,
        COUNT(DISTINCT c.complaint_id)
            FILTER (WHERE c.status <> 'RESOLVED') AS unresolved_complaints
    FROM municipal_wards AS mw
    LEFT JOIN areas AS a ON a.ward_id = mw.ward_id
    LEFT JOIN waste_reports AS wr ON wr.area_id = a.area_id
    LEFT JOIN complaints AS c ON c.area_id = a.area_id
    GROUP BY mw.ward_id, mw.ward_number
)
SELECT
    *,
    ROUND(100.0 * complaints / NULLIF(reports, 0), 2)
        AS complaints_per_100_reports
FROM ward_counts
ORDER BY complaints_per_100_reports DESC NULLS LAST;

-- 6. Worker workload and collection completion.
SELECT
    w.worker_id,
    u.name AS worker_name,
    a.area_name,
    COUNT(cr.request_id) AS assigned_requests,
    COUNT(cr.request_id) FILTER (WHERE cr.status = 'COLLECTED') AS collected,
    COUNT(cr.request_id) FILTER (WHERE cr.status <> 'COLLECTED') AS outstanding,
    ROUND(
        100.0 * COUNT(cr.request_id) FILTER (WHERE cr.status = 'COLLECTED')
        / NULLIF(COUNT(cr.request_id), 0),
        2
    ) AS completion_pct
FROM workers AS w
JOIN users AS u ON u.user_id = w.user_id
JOIN areas AS a ON a.area_id = w.assigned_area
LEFT JOIN collection_requests AS cr ON cr.worker_id = w.worker_id
GROUP BY w.worker_id, u.name, a.area_name
ORDER BY assigned_requests DESC, completion_pct ASC NULLS FIRST;

-- 7. Workload outliers with below-average completion.
WITH worker_metrics AS (
    SELECT
        w.worker_id,
        u.name AS worker_name,
        COUNT(cr.request_id) AS assigned_requests,
        COUNT(cr.request_id) FILTER (WHERE cr.status = 'COLLECTED') AS collected,
        100.0 * COUNT(cr.request_id) FILTER (WHERE cr.status = 'COLLECTED')
            / NULLIF(COUNT(cr.request_id), 0) AS completion_pct
    FROM workers AS w
    JOIN users AS u ON u.user_id = w.user_id
    LEFT JOIN collection_requests AS cr ON cr.worker_id = w.worker_id
    GROUP BY w.worker_id, u.name
),
baselines AS (
    SELECT
        AVG(assigned_requests) AS average_workload,
        AVG(completion_pct) AS average_completion
    FROM worker_metrics
)
SELECT m.*, b.average_workload, b.average_completion
FROM worker_metrics AS m
CROSS JOIN baselines AS b
WHERE m.assigned_requests > b.average_workload
  AND m.completion_pct < b.average_completion
ORDER BY m.assigned_requests DESC;

-- 8. Weekly waste and collection trend, week-over-week change and cumulative kg.
WITH weekly_waste AS (
    SELECT
        DATE_TRUNC('week', wr.reported_at)::date AS week_start,
        COUNT(DISTINCT wr.report_id) AS reports,
        SUM(wr.quantity_kg) AS waste_kg
    FROM waste_reports AS wr
    GROUP BY DATE_TRUNC('week', wr.reported_at)::date
),
weekly_collection AS (
    SELECT
        DATE_TRUNC('week', cr.assigned_at)::date AS week_start,
        COUNT(cr.request_id) AS requests,
        COUNT(cr.request_id) FILTER (WHERE cr.status = 'COLLECTED') AS collected_requests
    FROM collection_requests AS cr
    GROUP BY DATE_TRUNC('week', cr.assigned_at)::date
),
weekly AS (
    SELECT
        COALESCE(w.week_start, c.week_start) AS week_start,
        COALESCE(w.reports, 0) AS reports,
        COALESCE(w.waste_kg, 0) AS waste_kg,
        COALESCE(c.requests, 0) AS requests,
        COALESCE(c.collected_requests, 0) AS collected_requests
    FROM weekly_waste AS w
    FULL OUTER JOIN weekly_collection AS c USING (week_start)
)
SELECT
    week_start,
    reports,
    requests,
    collected_requests,
    waste_kg,
    LAG(waste_kg) OVER (ORDER BY week_start) AS previous_week_kg,
    waste_kg - LAG(waste_kg) OVER (ORDER BY week_start) AS week_change_kg,
    SUM(waste_kg) OVER (
        ORDER BY week_start ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_waste_kg,
    AVG(waste_kg) OVER (
        ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
    ) AS four_week_average_kg
FROM weekly
ORDER BY week_start;

-- 9. Area operational bottlenecks: waste, uncollected requests and complaints.
WITH waste AS (
    SELECT area_id, COUNT(*) AS reports, SUM(quantity_kg) AS waste_kg
    FROM waste_reports
    GROUP BY area_id
),
collection AS (
    SELECT
        wr.area_id,
        COUNT(cr.request_id) AS requests,
        COUNT(cr.request_id) FILTER (WHERE cr.status <> 'COLLECTED') AS outstanding
    FROM waste_reports AS wr
    JOIN collection_requests AS cr ON cr.report_id = wr.report_id
    GROUP BY wr.area_id
),
complaint AS (
    SELECT
        area_id,
        COUNT(*) AS complaints,
        COUNT(*) FILTER (WHERE status <> 'RESOLVED') AS unresolved
    FROM complaints
    GROUP BY area_id
)
SELECT
    a.area_id,
    a.area_name,
    mw.ward_number,
    COALESCE(w.reports, 0) AS reports,
    COALESCE(w.waste_kg, 0) AS waste_kg,
    COALESCE(c.requests, 0) AS requests,
    COALESCE(c.outstanding, 0) AS outstanding,
    COALESCE(cp.complaints, 0) AS complaints,
    COALESCE(cp.unresolved, 0) AS unresolved_complaints
FROM areas AS a
LEFT JOIN municipal_wards AS mw ON mw.ward_id = a.ward_id
LEFT JOIN waste AS w ON w.area_id = a.area_id
LEFT JOIN collection AS c ON c.area_id = a.area_id
LEFT JOIN complaint AS cp ON cp.area_id = a.area_id
ORDER BY outstanding DESC, waste_kg DESC;

-- 10. Immediate intervention shortlist. Aggregate each subject independently
-- to prevent waste, rating, and complaint join fan-out. Weights and treatment
-- of missing observations match etl/03_transform.py.
WITH waste AS (
    SELECT a.ward_id, COUNT(*) AS report_count, SUM(wr.quantity_kg) AS waste_kg
    FROM areas AS a
    JOIN waste_reports AS wr ON wr.area_id = a.area_id
    GROUP BY a.ward_id
),
collection AS (
    SELECT a.ward_id,
        COUNT(cr.request_id) AS requests,
        COUNT(cr.request_id) FILTER (WHERE cr.status = 'COLLECTED') AS collected
    FROM areas AS a
    JOIN waste_reports AS wr ON wr.area_id = a.area_id
    JOIN collection_requests AS cr ON cr.report_id = wr.report_id
    GROUP BY a.ward_id
),
segregation AS (
    SELECT a.ward_id,
        COUNT(sr.rating_id) AS ratings,
        COUNT(sr.rating_id) FILTER (WHERE sr.rating IN (4, 5)) AS good_ratings
    FROM areas AS a
    JOIN waste_reports AS wr ON wr.area_id = a.area_id
    JOIN collection_requests AS cr
        ON cr.report_id = wr.report_id AND cr.status = 'COLLECTED'
    JOIN segregation_ratings AS sr
        ON sr.request_id = cr.request_id
       AND sr.citizen_id = wr.citizen_id
       AND sr.worker_id = cr.worker_id
    GROUP BY a.ward_id
),
complaint_totals AS (
    SELECT a.ward_id, COUNT(*) AS complaint_count
    FROM areas AS a
    JOIN complaints AS c ON c.area_id = a.area_id
    GROUP BY a.ward_id
),
ward_metrics AS (
    SELECT mw.ward_id, mw.ward_number, mw.ward_name, mw.population,
        COALESCE(w.report_count, 0) AS report_count,
        COALESCE(w.waste_kg, 0)::numeric AS waste_kg,
        COALESCE(c.requests, 0) AS requests,
        COALESCE(c.collected, 0) AS collected,
        COALESCE(s.ratings, 0) AS ratings,
        COALESCE(s.good_ratings, 0) AS good_ratings,
        COALESCE(cp.complaint_count, 0) AS complaint_count,
        100.0 * c.collected / NULLIF(c.requests, 0) AS collection_efficiency,
        100.0 * s.good_ratings / NULLIF(s.ratings, 0) AS good_segregation_rate,
        100.0 * cp.complaint_count / NULLIF(w.report_count, 0) AS complaint_rate
    FROM municipal_wards AS mw
    LEFT JOIN waste AS w ON w.ward_id = mw.ward_id
    LEFT JOIN collection AS c ON c.ward_id = mw.ward_id
    LEFT JOIN segregation AS s ON s.ward_id = mw.ward_id
    LEFT JOIN complaint_totals AS cp ON cp.ward_id = mw.ward_id
),
population_baseline AS (
    SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY population) AS median_population
    FROM municipal_wards
    WHERE population IS NOT NULL
),
normalized AS (
    SELECT m.*,
        COALESCE(m.complaint_rate, 0) AS normalized_complaint_rate,
        COALESCE(m.population, p.median_population) AS score_population,
        CASE WHEN MAX(waste_kg) OVER () = MIN(waste_kg) OVER () THEN 0
            ELSE 100.0 * (waste_kg - MIN(waste_kg) OVER ())
                / NULLIF(MAX(waste_kg) OVER () - MIN(waste_kg) OVER (), 0)
        END AS waste_score,
        100 - COALESCE(collection_efficiency, 0) AS collection_score,
        100 - COALESCE(good_segregation_rate, 50) AS segregation_score,
        CASE
            WHEN MAX(COALESCE(complaint_rate, 0)) OVER ()
               = MIN(COALESCE(complaint_rate, 0)) OVER () THEN 0
            ELSE 100.0 * (
                COALESCE(complaint_rate, 0)
                - MIN(COALESCE(complaint_rate, 0)) OVER ()
            ) / NULLIF(
                MAX(COALESCE(complaint_rate, 0)) OVER ()
                - MIN(COALESCE(complaint_rate, 0)) OVER (), 0
            )
        END AS complaint_score
    FROM ward_metrics AS m
    CROSS JOIN population_baseline AS p
),
scored AS (
    SELECT n.*,
        CASE WHEN MAX(score_population) OVER () = MIN(score_population) OVER () THEN 0
            ELSE 100.0 * (score_population - MIN(score_population) OVER ())
                / NULLIF(MAX(score_population) OVER () - MIN(score_population) OVER (), 0)
        END AS population_score
    FROM normalized AS n
),
ranked AS (
    SELECT *,
        ROUND((
            0.30 * waste_score
            + 0.25 * collection_score
            + 0.20 * segregation_score
            + 0.15 * complaint_score
            + 0.10 * population_score
        )::numeric, 2) AS priority_score
    FROM scored
)
SELECT *,
    CASE
        WHEN priority_score <= 30 THEN 'Low'
        WHEN priority_score <= 60 THEN 'Medium'
        WHEN priority_score <= 80 THEN 'High'
        ELSE 'Critical'
    END AS priority_category
FROM ranked
ORDER BY priority_score DESC, ward_id
LIMIT 20;
