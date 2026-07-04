import os
import json
import time
import random
import logging
from datetime import datetime
import requests
from dotenv import load_dotenv

# Load secret keys from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pipeline.log"),
        logging.StreamHandler()
    ]
)

class AdzunaApiIngestion:
    def __init__(self):
        # Retrieve credentials securely from environment variables
        self.app_id = os.getenv("ADZUNA_APP_ID")
        self.app_key = os.getenv("ADZUNA_APP_KEY")
        
        if not self.app_id or not self.app_key:
            raise ValueError("CRITICAL ERROR: Missing API Credentials in .env file.")

    def fetch_job_data(self, country="in", page=1, keyword="Developer"):
        """Executes the authenticated HTTP request with defensive error handling."""
        base_url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
        
        # Query parameters required by Adzuna
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": 20, 
            "what": keyword,
            "content-type": "application/json"
        }
        
        try:
            logging.info(f"Querying Adzuna API for country='{country}', page={page}, keyword='{keyword}'")
            response = requests.get(base_url, params=params, timeout=15)
            
            # Enforce defensive validation on response codes
            response.raise_for_status()
            return response.json() # Direct JSON extraction
            
        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTP Connection Blocked: {http_err}")
        except requests.exceptions.Timeout:
            logging.error("API Gateway Timeout encountered.")
        except requests.exceptions.RequestException as req_err:
            logging.error(f"Catastrophic network failure: {req_err}")
        return None

    def process_payload(self, raw_payload, country="in"):
        """Maps nested API responses directly to our required target fields, attaching country context."""
        if not raw_payload or "results" not in raw_payload:
            logging.warning("Empty or malformed payload provided. Aborting transformation.")
            return []

        processed_records = []
        
        for job in raw_payload["results"]:
            try:
                # Target Field 1 & 2: Title & Company (with defensive parsing fallbacks)
                title = job.get("title", "N/A").strip()
                company_info = job.get("company", {})
                company = company_info.get("display_name", "N/A").strip()
                
                # Target Field 3: Location (Adzuna passes this as an array of areas)
                location_info = job.get("location", {})
                location_list = location_info.get("area", ["N/A"])
                # Extract city/region and build a display string
                location = location_list[-1] if location_list else "N/A"
                
                # Target Field 4: Description
                description = job.get("description", "No description provided.").strip()
                
                # Target Field 5: Salary Range Processing
                salary_min = job.get("salary_min")
                salary_max = job.get("salary_max")
                
                if salary_min and salary_max:
                    salary = f"{salary_min} - {salary_max}"
                elif salary_min:
                    salary = f"{salary_min}"
                else:
                    salary = "N/A" # Defensive strategy for missing salary fields

                # Source url
                source_url = job.get("redirect_url", "")

                processed_records.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "country": "India" if country == "in" else "United Kingdom",
                    "description": description,
                    "salary": salary,
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "source_url": source_url,
                    "scraped_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                })
                
            except Exception as e:
                logging.warning(f"Skipping transactional item processing block due to exception: {e}")
                continue
                
        return processed_records

    def save_raw_lake(self, serialized_data):
        """Saves clean data into our local raw storage tier."""
        if not serialized_data:
            return
            
        os.makedirs('data/raw', exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path = f"data/raw/api_jobs_{timestamp}.json"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(serialized_data, f, ensure_ascii=False, indent=4)
            
        logging.info(f"Pipeline executed successfully. Saved {len(serialized_data)} JSON objects to {file_path}")
        return file_path

    def run(self, countries=["in", "gb"], keywords=["Developer", "Data Analyst", "Data Scientist", "Business Analyst", "Data Engineer"], pages_per_query=2):
        """Orchestrates pipeline workflow execution across countries, keywords, and pages."""
        all_data = []
        
        for country in countries:
            for keyword in keywords:
                for page in range(1, pages_per_query + 1):
                    raw_json = self.fetch_job_data(country=country, page=page, keyword=keyword)
                    
                    if raw_json:
                        processed_data = self.process_payload(raw_json, country=country)
                        all_data.extend(processed_data)
                        logging.info(f"Fetched and processed {len(processed_data)} records for country='{country}', keyword='{keyword}', page={page}")
                    
                    # Implement a random delay before processing data to replicate human intervals
                    time.sleep(random.uniform(1.0, 2.0))
        
        if all_data:
            file_path = self.save_raw_lake(all_data)
            return file_path
        else:
            logging.warning("No data was scraped in this run.")
            return None

if __name__ == "__main__":
    pipeline = AdzunaApiIngestion()
    # Scrape 2 pages for each combination to fetch a decent dataset of 200+ jobs
    pipeline.run(countries=["in", "gb"], keywords=["Developer", "Data Analyst", "Data Scientist", "Business Analyst", "Data Engineer"], pages_per_query=2)