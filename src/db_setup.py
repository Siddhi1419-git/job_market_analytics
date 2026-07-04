import logging
from sqlalchemy import create_engine, text

# Database connection configuration
DB_USER = "root"
DB_PASSWORD = "MyNewPassword123!"
DB_HOST = "localhost"
DB_PORT = "3306"
DB_NAME = "job_market_db"

# Engine to create database if not exists
ADMIN_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}"
DB_URL = f"{ADMIN_URL}/{DB_NAME}"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def setup_database():
    # 1. Create database if it doesn't exist
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    with admin_engine.connect() as conn:
        logging.info(f"Checking if database '{DB_NAME}' exists...")
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"))
        logging.info(f"Database '{DB_NAME}' is ready.")
    admin_engine.dispose()

    # 2. Establish connection to job_market_db
    engine = create_engine(DB_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        # Create core tables if they do not exist
        logging.info("Creating tables if they do not exist...")
        
        # companies
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS companies (
                company_id INT AUTO_INCREMENT PRIMARY KEY,
                company_name VARCHAR(255) NOT NULL UNIQUE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """))
        
        # locations (basic structure)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS locations (
                location_id INT AUTO_INCREMENT PRIMARY KEY,
                city VARCHAR(150) NOT NULL,
                region VARCHAR(150) DEFAULT NULL,
                UNIQUE KEY uq_city_region (city, region)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """))
        
        # job_postings (basic structure)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS job_postings (
                job_id INT AUTO_INCREMENT PRIMARY KEY,
                company_id INT NOT NULL,
                location_id INT DEFAULT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                salary_min DECIMAL(10,2) DEFAULT NULL,
                salary_max DECIMAL(10,2) DEFAULT NULL,
                posted_date DATE DEFAULT NULL,
                source_url VARCHAR(500) DEFAULT NULL,
                scraped_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_job_company FOREIGN KEY (company_id) REFERENCES companies (company_id) ON DELETE CASCADE,
                CONSTRAINT fk_job_location FOREIGN KEY (location_id) REFERENCES locations (location_id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """))
        
        # skills
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS skills (
                skill_id INT AUTO_INCREMENT PRIMARY KEY,
                skill_name VARCHAR(100) NOT NULL UNIQUE,
                skill_category ENUM('technical', 'soft') DEFAULT 'technical'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """))
        
        # job_skills
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS job_skills (
                job_id INT NOT NULL,
                skill_id INT NOT NULL,
                PRIMARY KEY (job_id, skill_id),
                CONSTRAINT fk_jobskill_job FOREIGN KEY (job_id) REFERENCES job_postings (job_id) ON DELETE CASCADE,
                CONSTRAINT fk_jobskill_skill FOREIGN KEY (skill_id) REFERENCES skills (skill_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """))

        # 3. Alter tables to add new required columns if they do not exist
        logging.info("Performing migrations and schema updates...")
        
        # Check locations columns
        loc_cols = [r[0] for r in conn.execute(text("SHOW COLUMNS FROM locations")).fetchall()]
        if 'country' not in loc_cols:
            logging.info("Adding 'country' column to locations table...")
            conn.execute(text("ALTER TABLE locations ADD COLUMN country VARCHAR(100) DEFAULT 'India'"))
            # Recreate unique key to include country
            try:
                conn.execute(text("ALTER TABLE locations DROP KEY uq_city_region"))
            except Exception as e:
                logging.warning(f"Could not drop uq_city_region key: {e}")
            try:
                conn.execute(text("ALTER TABLE locations ADD CONSTRAINT uq_city_region_country UNIQUE (city, region, country)"))
            except Exception as e:
                logging.warning(f"Could not add uq_city_region_country constraint: {e}")

        # Check job_postings columns
        job_cols = [r[0] for r in conn.execute(text("SHOW COLUMNS FROM job_postings")).fetchall()]
        
        migrations = {
            'experience_min': "INT DEFAULT NULL",
            'experience_max': "INT DEFAULT NULL",
            'job_category': "VARCHAR(100) DEFAULT NULL",
            'is_remote': "VARCHAR(50) DEFAULT 'onsite'",
            'salary_currency': "VARCHAR(10) DEFAULT 'INR'",
            'salary_min_usd': "DECIMAL(12,2) DEFAULT NULL",
            'salary_max_usd': "DECIMAL(12,2) DEFAULT NULL",
            'salary_mid_usd': "DECIMAL(12,2) DEFAULT NULL"
        }
        
        for col, col_def in migrations.items():
            if col not in job_cols:
                logging.info(f"Adding '{col}' column to job_postings table...")
                conn.execute(text(f"ALTER TABLE job_postings ADD COLUMN {col} {col_def}"))
        
        # Commit transactional modifications
        conn.execute(text("COMMIT"))
        logging.info("Database setup and schema migration completed successfully.")
        
    engine.dispose()

if __name__ == "__main__":
    setup_database()
