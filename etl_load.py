"""
Day 2 — ETL: load raw scraped job data into the normalized MySQL schema.

Usage:
    python etl_load.py path/to/jobs_raw.json
    python etl_load.py path/to/jobs_raw.csv

Auto-detects CSV vs JSON from the file extension.
Handles both flat fields ("company": "Acme") and nested API-style fields.
Uses the JobDataCleaner to perform feature engineering (skills, experience, category, USD salaries).
"""

import sys
import re
import csv
import json
from datetime import date

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Import data cleaner
from src.data_cleaner import JobDataCleaner

# ---------------------------------------------------------------
# 1. DB CONNECTION CONFIG — edit these to match your local MySQL
# ---------------------------------------------------------------
DB_USER = "root"
DB_PASSWORD = "MyNewPassword123!"
DB_HOST = "localhost"
DB_PORT = "3306"
DB_NAME = "job_market_db"

DB_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


class JobETL:
    """Object-oriented ETL pipeline: extract from CSV/JSON, transform, load into MySQL."""

    def __init__(self, db_url: str):
        self.engine = create_engine(db_url, pool_pre_ping=True)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        # In-memory caches so we don't re-query the DB for every row
        self._company_cache = {}
        self._location_cache = {}
        self._skill_cache = {}

    # ---------- EXTRACT ----------
    def read_csv(self, filepath: str):
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [row for row in reader]

    def read_json(self, filepath: str):
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        # APIs commonly wrap the list in a key like "results" or "jobs"
        if isinstance(data, dict):
            for key in ("results", "jobs", "data", "postings"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            # fallback: maybe it's a single job object
            return [data]
        return data  # already a list

    def read_file(self, filepath: str):
        if filepath.lower().endswith(".json"):
            return self.read_json(filepath)
        return self.read_csv(filepath)

    # ---------- TRANSFORM helpers ----------
    @staticmethod
    def extract_text(value):
        """Handles both plain strings and nested dicts like {'display_name': '...'}."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for key in ("display_name", "name", "title", "value"):
                if key in value and value[key]:
                    return str(value[key]).strip()
        return str(value).strip()

    @staticmethod
    def parse_salary(raw_salary):
        """Turns messy strings like '$80,000 - $100,000' into (min, max) floats."""
        if raw_salary is None:
            return None, None
        if isinstance(raw_salary, (int, float)):
            return float(raw_salary), float(raw_salary)
        numbers = re.findall(r"[\d,]+(?:\.\d+)?", str(raw_salary))
        numbers = [float(n.replace(",", "")) for n in numbers]
        if len(numbers) == 0:
            return None, None
        if len(numbers) == 1:
            return numbers[0], numbers[0]
        return min(numbers), max(numbers)

    @staticmethod
    def parse_location(raw_location: str):
        """Splits 'Bengaluru, Karnataka' into (city, region). Falls back gracefully."""
        if not raw_location:
            return None, None
        parts = [p.strip() for p in raw_location.split(",")]
        city = parts[0] if parts else None
        region = parts[1] if len(parts) > 1 else None
        return city, region

    # ---------- LOAD helpers (get-or-create pattern) ----------
    def get_or_create_company(self, name: str):
        if not name:
            name = "Unknown"
        if name in self._company_cache:
            return self._company_cache[name]

        row = self.session.execute(
            text("SELECT company_id FROM companies WHERE company_name = :name"),
            {"name": name},
        ).fetchone()

        if row:
            company_id = row[0]
        else:
            result = self.session.execute(
                text("INSERT INTO companies (company_name) VALUES (:name)"),
                {"name": name},
            )
            company_id = result.lastrowid

        self._company_cache[name] = company_id
        return company_id

    def get_or_create_location(self, city: str, region: str, country: str):
        key = (city, region, country)
        if key in self._location_cache:
            return self._location_cache[key]

        if city is None:
            return None

        row = self.session.execute(
            text(
                "SELECT location_id FROM locations "
                "WHERE city = :city AND (region = :region OR (:region IS NULL AND region IS NULL)) "
                "AND (country = :country OR (:country IS NULL AND country IS NULL))"
            ),
            {"city": city, "region": region, "country": country},
        ).fetchone()

        if row:
            location_id = row[0]
        else:
            result = self.session.execute(
                text("INSERT INTO locations (city, region, country) VALUES (:city, :region, :country)"),
                {"city": city, "region": region, "country": country},
            )
            location_id = result.lastrowid

        self._location_cache[key] = location_id
        return location_id

    def get_or_create_skill(self, skill_name: str, skill_category: str = "technical"):
        if skill_name in self._skill_cache:
            return self._skill_cache[skill_name]
            
        row = self.session.execute(
            text("SELECT skill_id FROM skills WHERE skill_name = :name"),
            {"name": skill_name},
        ).fetchone()

        if row:
            skill_id = row[0]
        else:
            result = self.session.execute(
                text("INSERT INTO skills (skill_name, skill_category) VALUES (:name, :category)"),
                {"name": skill_name, "category": skill_category},
            )
            skill_id = result.lastrowid

        self._skill_cache[skill_name] = skill_id
        return skill_id

    def add_job_skill(self, job_id: int, skill_id: int):
        self.session.execute(
            text("INSERT IGNORE INTO job_skills (job_id, skill_id) VALUES (:job_id, :skill_id)"),
            {"job_id": job_id, "skill_id": skill_id},
        )

    def insert_job_posting(self, title, description, salary_min, salary_max,
                            company_id, location_id, source_url,
                            experience_min, experience_max, job_category, is_remote,
                            salary_currency, salary_min_usd, salary_max_usd, salary_mid_usd):
        result = self.session.execute(
            text(
                """
                INSERT INTO job_postings
                    (title, description, salary_min, salary_max,
                     company_id, location_id, posted_date, source_url,
                     experience_min, experience_max, job_category, is_remote,
                     salary_currency, salary_min_usd, salary_max_usd, salary_mid_usd)
                VALUES
                    (:title, :description, :salary_min, :salary_max,
                     :company_id, :location_id, :posted_date, :source_url,
                     :experience_min, :experience_max, :job_category, :is_remote,
                     :salary_currency, :salary_min_usd, :salary_max_usd, :salary_mid_usd)
                """
            ),
            {
                "title": title,
                "description": description,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "company_id": company_id,
                "location_id": location_id,
                "posted_date": date.today(),
                "source_url": source_url,
                "experience_min": experience_min,
                "experience_max": experience_max,
                "job_category": job_category,
                "is_remote": is_remote,
                "salary_currency": salary_currency,
                "salary_min_usd": salary_min_usd,
                "salary_max_usd": salary_max_usd,
                "salary_mid_usd": salary_mid_usd
            },
        )
        return result.lastrowid

    # ---------- ORCHESTRATION ----------
    def run(self, filepath: str):
        # Initialize the data cleaner
        cleaner = JobDataCleaner()
        
        rows = self.read_file(filepath)
        print(f"Read {len(rows)} raw rows from {filepath}")

        inserted, skipped = 0, 0

        for row in rows:
            try:
                # Normalize keys to lowercase so header/field casing doesn't matter
                row = {str(k).strip().lower(): v for k, v in row.items()}

                title = self.extract_text(row.get("title"))
                if not title:
                    skipped += 1
                    continue

                company_name = self.extract_text(row.get("company"))
                location_raw = self.extract_text(row.get("location"))
                city, region = self.parse_location(location_raw)
                
                # Fetch country context
                country = row.get("country", "India")
                
                description = self.extract_text(row.get("description"))
                source_url = row.get("source_url", "")

                # Some APIs give one combined "salary" string,
                # others give separate salary_min / salary_max fields.
                if "salary_min" in row or "salary_max" in row:
                    salary_min, _ = self.parse_salary(row.get("salary_min"))
                    salary_max, _ = self.parse_salary(row.get("salary_max"))
                    if salary_max is None:
                        salary_max = salary_min
                    if salary_min is None:
                        salary_min = salary_max
                else:
                    salary_min, salary_max = self.parse_salary(row.get("salary"))

                # Data Cleaning & Feature Engineering
                exp_min, exp_max = cleaner.extract_experience(description)
                if exp_min is None:
                    # try title if not found in description
                    exp_min, exp_max = cleaner.extract_experience(title)
                    
                job_category = cleaner.determine_job_category(title)
                is_remote = cleaner.determine_work_mode(description)
                
                # Standardize salary to USD
                sal_min_usd, sal_max_usd, sal_mid_usd, salary_currency = cleaner.standardize_salary(
                    salary_min, salary_max, country
                )

                company_id = self.get_or_create_company(company_name)
                location_id = self.get_or_create_location(city, region, country)

                job_id = self.insert_job_posting(
                    title, description, salary_min, salary_max,
                    company_id, location_id, source_url,
                    exp_min, exp_max, job_category, is_remote,
                    salary_currency, sal_min_usd, sal_max_usd, sal_mid_usd
                )
                
                # Parse and link skills
                tech_skills, soft_skills = cleaner.extract_skills(title + " " + description)
                
                for skill in tech_skills:
                    skill_id = self.get_or_create_skill(skill, "technical")
                    self.add_job_skill(job_id, skill_id)
                    
                for skill in soft_skills:
                    skill_id = self.get_or_create_skill(skill, "soft")
                    self.add_job_skill(job_id, skill_id)

                inserted += 1

            except Exception as e:
                # Defensive: one bad row should never kill the whole batch
                print(f"  [skipped row] {row.get('title', '?')} -> {e}")
                skipped += 1
                continue

        self.session.commit()
        print(f"Done. Inserted: {inserted}, Skipped: {skipped}")

    def close(self):
        self.session.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python etl_load.py path/to/jobs_raw.json")
        sys.exit(1)

    etl = JobETL(DB_URL)
    try:
        etl.run(sys.argv[1])
    finally:
        etl.close()