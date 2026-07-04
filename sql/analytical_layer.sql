-- =============================================================================
-- SQL Analytical Layer for Job Market Analytics
-- Target: MySQL 8.0+
--
-- This script contains portfolio-quality exploratory queries. It uses
-- window functions, common table expressions (CTEs), multi-table joins,
-- and aggregation to extract intelligence from our scraped job listings.
-- =============================================================================

USE job_market_db;

-- =============================================================================
-- QUERY 1: Location × Role Category — Salary Rank
--
-- Purpose:  Rank cities within each country by their average midpoint salary 
--           for each job category using DENSE_RANK().
-- Features: CTEs, multi-table joins, Window Functions (DENSE_RANK() OVER PARTITION BY)
-- =============================================================================

WITH category_location_salary AS (
    SELECT
        jp.job_category,
        l.country,
        l.city,
        COUNT(*) AS posting_count,
        ROUND(AVG(jp.salary_mid_usd), 2) AS avg_salary_usd
    FROM job_postings jp
    JOIN companies c ON jp.company_id = c.company_id
    JOIN locations l ON jp.location_id = l.location_id
    -- Focus on postings where salary data exists
    WHERE jp.salary_mid_usd IS NOT NULL
    GROUP BY jp.job_category, l.country, l.city
),
ranked_locations AS (
    SELECT
        job_category,
        country,
        city,
        posting_count,
        avg_salary_usd,
        DENSE_RANK() OVER (
            PARTITION BY job_category, country
            ORDER BY avg_salary_usd DESC
        ) AS salary_rank
    FROM category_location_salary
)
SELECT
    job_category AS `Job Category`,
    country AS `Country`,
    city AS `City`,
    posting_count AS `Postings Count`,
    CONCAT('$', FORMAT(avg_salary_usd, 2)) AS `Average Midpoint Salary (USD)`,
    salary_rank AS `Salary Rank`
FROM ranked_locations
ORDER BY job_category, country, salary_rank;


-- =============================================================================
-- QUERY 2: 7-Day Moving Average of Posting Volume by Job Category
--
-- Purpose:  Track job posting volume trends using a rolling 7-day average.
-- Features: Window functions with custom frame definitions (ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
-- =============================================================================

WITH daily_category_counts AS (
    SELECT
        job_category,
        posted_date,
        COUNT(*) AS daily_postings
    FROM job_postings
    WHERE posted_date IS NOT NULL
    GROUP BY job_category, posted_date
)
SELECT
    job_category AS `Job Category`,
    posted_date AS `Posted Date`,
    daily_postings AS `Daily Postings`,
    -- 7-day rolling average of daily postings
    ROUND(
        AVG(daily_postings) OVER (
            PARTITION BY job_category
            ORDER BY posted_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS `7D Rolling Avg Postings`,
    -- Diagnostic to see how many days of history exist in the window
    COUNT(posted_date) OVER (
        PARTITION BY job_category
        ORDER BY posted_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS `Days in Window`
FROM daily_category_counts
ORDER BY job_category, posted_date DESC;


-- =============================================================================
-- QUERY 3: Top 5 In-Demand Skills by Job Category
--
-- Purpose:  Identify the most frequently requested skills for each job category,
--           filtering by skill category (technical vs soft).
-- Features: Inner Joins, GROUP BY with aggregation, ROW_NUMBER() window partition.
-- =============================================================================

WITH skill_frequencies AS (
    SELECT
        jp.job_category,
        s.skill_name,
        s.skill_category,
        COUNT(*) AS frequency
    FROM job_postings jp
    JOIN job_skills js ON jp.job_id = js.job_id
    JOIN skills s ON js.skill_id = s.skill_id
    WHERE jp.job_category IS NOT NULL
    GROUP BY jp.job_category, s.skill_name, s.skill_category
),
ranked_skills AS (
    SELECT
        job_category,
        skill_name,
        skill_category,
        frequency,
        ROW_NUMBER() OVER (
            PARTITION BY job_category, skill_category
            ORDER BY frequency DESC
        ) AS skill_rank
    FROM skill_frequencies
)
SELECT
    job_category AS `Job Category`,
    skill_category AS `Skill Type`,
    skill_name AS `Skill Name`,
    frequency AS `Job Count`,
    skill_rank AS `Rank`
FROM ranked_skills
WHERE skill_rank <= 5
ORDER BY job_category, skill_category, skill_rank;


-- =============================================================================
-- QUERY 4: Compensation by Work Mode and Experience Level
--
-- Purpose:  Examine salary differences across Work Modes (Remote vs Hybrid vs Onsite)
--           and derived experience buckets.
-- Features: Conditional case expressions, aggregated salary stats.
-- =============================================================================

SELECT
    is_remote AS `Work Mode`,
    CASE
        WHEN experience_min < 2 THEN 'Entry-Level (<2 yrs)'
        WHEN experience_min BETWEEN 2 AND 5 THEN 'Mid-Level (2-5 yrs)'
        WHEN experience_min > 5 THEN 'Senior-Level (>5 yrs)'
        ELSE 'Not Specified'
    END AS `Experience Bucket`,
    COUNT(*) AS `Total Listings`,
    CONCAT('$', FORMAT(MIN(salary_min_usd), 0)) AS `Min Salary (USD)`,
    CONCAT('$', FORMAT(AVG(salary_mid_usd), 0)) AS `Avg Midpoint Salary (USD)`,
    CONCAT('$', FORMAT(MAX(salary_max_usd), 0)) AS `Max Salary (USD)`
FROM job_postings
WHERE salary_mid_usd IS NOT NULL
GROUP BY `Work Mode`, `Experience Bucket`
ORDER BY `Work Mode`, FIELD(`Experience Bucket`, 'Entry-Level (<2 yrs)', 'Mid-Level (2-5 yrs)', 'Senior-Level (>5 yrs)', 'Not Specified');
