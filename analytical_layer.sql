-- =============================================================================
-- Day 3 — SQL Analytical Layer
-- job_market_db | MySQL 8.0+
--
-- Dataset as of 2026-06-22:
--   • 20 job postings, all posted_date = 2026-06-22 (single scrape run)
--   • salary_min / salary_max = NULL for every row — the Adzuna India API
--     does not disclose salary for these listings; this is a data-source
--     constraint, not a pipeline bug.
--
-- Limitations called out inline wherever they affect interpretation.
-- =============================================================================


-- =============================================================================
-- QUERY 1: Location × Role Category — Salary Rank
--
-- Purpose:  Rank locations by average salary within each role category using
--           DENSE_RANK() OVER (PARTITION BY category ...).
--
-- Honest caveat:  Every salary_min value in the current dataset is NULL.
--           AVG(salary_min) therefore returns NULL for every (category, city)
--           group, and DENSE_RANK produces NULL ranks. The query is structurally
--           correct and will populate with real values the moment the API starts
--           returning salary data. We report the NULL output as-is; fabricating
--           numbers would be worse than showing an honest NULL.
--
-- Role category: derived by stripping the last word ("Developer", "Manager",
--           etc.) to create a coarse grouping from the title field, since the
--           schema has no dedicated category column yet.
-- =============================================================================

WITH role_location_salary AS (
    -- Step 1: Aggregate average salary per (category, city) pair.
    -- TRIM(TRAILING suffix FROM title) is not portable; we use SUBSTRING_INDEX
    -- to split on the last space, giving us a rough role-family prefix.
    SELECT
        -- Derive a coarse category by taking everything before the final word
        -- e.g. "PHP Developer" -> "PHP", "Frontend Developer" -> "Frontend",
        --      "Developer" -> "Developer" (single-word titles kept as-is)
        CASE
            WHEN LOCATE(' ', jp.title) > 0
                THEN SUBSTRING_INDEX(jp.title, ' ', -1)   -- last word as role type
            ELSE jp.title
        END                                                  AS role_type,
        l.city,
        COUNT(*)                                             AS posting_count,
        AVG(jp.salary_min)                                   AS avg_salary_min,
        AVG(jp.salary_max)                                   AS avg_salary_max,
        -- Midpoint: if both bounds present use midpoint, else whichever exists
        AVG(
            CASE
                WHEN jp.salary_min IS NOT NULL AND jp.salary_max IS NOT NULL
                    THEN (jp.salary_min + jp.salary_max) / 2.0
                WHEN jp.salary_min IS NOT NULL THEN jp.salary_min
                WHEN jp.salary_max IS NOT NULL THEN jp.salary_max
                ELSE NULL
            END
        )                                                    AS avg_salary_mid
    FROM job_postings jp
    JOIN companies  c ON jp.company_id   = c.company_id
    LEFT JOIN locations l ON jp.location_id = l.location_id
    GROUP BY role_type, l.city
),
ranked AS (
    -- Step 2: Dense-rank locations within each role_type by average midpoint salary.
    -- DENSE_RANK is used (not ROW_NUMBER) so that ties share the same rank.
    SELECT
        role_type,
        city,
        posting_count,
        avg_salary_mid,
        DENSE_RANK() OVER (
            PARTITION BY role_type
            ORDER BY avg_salary_mid DESC   -- NULLs sort last in MySQL DESC windows
        ) AS salary_rank
    FROM role_location_salary
)
SELECT
    role_type,
    city,
    posting_count,
    -- Format salary for readability; show NULL explicitly rather than hiding it
    COALESCE(CAST(ROUND(avg_salary_mid, 2) AS CHAR), 'NULL — no salary data in API') AS avg_salary_midpoint,
    salary_rank
FROM ranked
ORDER BY role_type, salary_rank, city;


-- =============================================================================
-- QUERY 2: Rolling 7-Day Moving Average of Posting Volume by Role Category
--
-- Purpose:  Show how posting volume per role type trends over a rolling 7-day
--           window using a window frame:
--               ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
--
-- Honest caveat:  The entire current dataset consists of postings from a SINGLE
--           date (2026-06-22). A 7-day moving average over one date is
--           mathematically valid but produces the same value as the raw daily
--           count — there is no trend signal yet. This query is included because
--           the window function is architecturally correct and will produce
--           meaningful output as data accumulates across multiple scrape runs.
--           The output below is real; the interpretation caveat is explicit.
-- =============================================================================

WITH daily_counts AS (
    -- Step 1: Count postings per (role_type, day).
    -- Same role-type derivation as Query 1 (last word of title).
    SELECT
        CASE
            WHEN LOCATE(' ', jp.title) > 0
                THEN SUBSTRING_INDEX(jp.title, ' ', -1)
            ELSE jp.title
        END          AS role_type,
        jp.posted_date,
        COUNT(*)     AS daily_postings
    FROM job_postings jp
    WHERE jp.posted_date IS NOT NULL
    GROUP BY role_type, jp.posted_date
)
SELECT
    role_type,
    posted_date,
    daily_postings,
    -- 7-day rolling average: looks back up to 6 prior rows within the same partition.
    -- With only one date per role, this equals daily_postings — noted in comments above.
    ROUND(
        AVG(daily_postings) OVER (
            PARTITION BY role_type
            ORDER BY posted_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ),
    2) AS rolling_7d_avg_postings,
    -- Helpful diagnostics: show how many days are actually in the window
    COUNT(posted_date) OVER (
        PARTITION BY role_type
        ORDER BY posted_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS days_in_window   -- will equal 1 for all rows until more dates accumulate
FROM daily_counts
ORDER BY role_type, posted_date;
