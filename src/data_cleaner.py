import re
import logging
from typing import Tuple, List, Set, Dict

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Comprehensive predefined list of skills to match
TECHNICAL_SKILLS = [
    "Python", "SQL", "Java", "C++", "C#", "JavaScript", "TypeScript", "React", "Angular", "Vue",
    "HTML", "CSS", "PHP", "Laravel", "Ruby", "Rails", "Go", "Rust", "Swift", "Kotlin", "Scala", 
    "Spark", "Hadoop", "Kafka", "Docker", "Kubernetes", "Git", "Jenkins", "Ansible", "Terraform",
    "AWS", "Azure", "GCP", "Google Cloud", "Salesforce", "Tableau", "Power BI", "Excel", "SAS",
    "R", "MATLAB", "SPSS", "Machine Learning", "Deep Learning", "NLP", "Computer Vision", 
    "TensorFlow", "PyTorch", "Scikit-Learn", "Keras", "OpenCV", "LangChain", "Agentic AI", "LLM",
    "OpenAI", "Generative AI", "Hugging Face", "MongoDB", "PostgreSQL", "MySQL", "SQLite", "Oracle",
    "Redis", "Elasticsearch", "Redshift", "Snowflake", "BigQuery", "DynamoDB", "Cassandra",
    "Flask", "Django", "FastAPI", "Spring Boot", "Node.js", "Express", "GraphQL", "Haskell", "COBOL",
    "Fortran", "ABAP", "SAP", "Informatica", "Linux", "Unix", "Bash", "Shell", "PowerShell", "ABAP",
    "RightAngle", "AS400", "RPGLE", "CLP", "DB2", "PL/SQL", "T-SQL", "SSIS", "SSAS", "SSRS",
    "COBOL", "CICS", "JCL", "Mainframe", "ABAP", "Web Dynpro", "Fiori", "HANA", "Basis", "GRC"
]

SOFT_SKILLS = [
    "Communication", "Leadership", "Agile", "Scrum", "Teamwork", "Collaboration", "Problem Solving",
    "Analytical Skills", "Critical Thinking", "Project Management", "Time Management", "Creativity",
    "Adaptability", "Negotiation", "Mentoring", "Presentation", "Interpersonal Skills", "Decision Making"
]

# Case-insensitive mapping for role categories
ROLE_CATEGORIES = {
    "data_scientist": ["data scientist", "machine learning", "ml engineer", "deep learning", "nlp engineer", "ai scientist"],
    "data_analyst": ["data analyst", "business intelligence", "bi analyst", "analytics", "reporting analyst", "data visualization"],
    "business_analyst": ["business analyst", "systems analyst", "product analyst", "operations analyst"],
    "data_engineer": ["data engineer", "data architect", "database engineer", "etl developer", "big data engineer"],
    "software_engineer": ["developer", "engineer", "programmer", "full stack", "frontend", "backend", "web developer", "coder"],
    "devops": ["devops", "sre", "cloud engineer", "system administrator", "infrastructure"],
    "management": ["manager", "director", "lead", "head of", "scrum master", "product manager", "project manager"]
}

# Fixed exchange rates relative to USD (base: 2026)
CURRENCY_EXCHANGE_TO_USD = {
    "INR": 0.012,   # 1 INR = 0.012 USD
    "GBP": 1.28,    # 1 GBP = 1.28 USD
    "USD": 1.0,     # 1 USD = 1.0 USD
    "EUR": 1.08,    # 1 EUR = 1.08 USD
    "CAD": 0.73,    # 1 CAD = 0.73 USD
    "AUD": 0.66     # 1 AUD = 0.66 USD
}

class JobDataCleaner:
    def __init__(self):
        # Prepare technical and soft skills compiled patterns for performance
        self.tech_patterns = {skill: re.compile(rf'\b{re.escape(skill)}\b', re.IGNORECASE) for skill in TECHNICAL_SKILLS}
        # Add special regex mappings for skills with special characters
        self.tech_patterns.update({
            "C++": re.compile(r'\bC\+\+\b', re.IGNORECASE),
            "C#": re.compile(r'\bC#\b', re.IGNORECASE),
            ".NET": re.compile(r'\b\.NET\b', re.IGNORECASE),
            "Vue.js": re.compile(r'\bVue(?:\.js)?\b', re.IGNORECASE),
            "Node.js": re.compile(r'\bNode(?:\.js)?\b', re.IGNORECASE),
            "React.js": re.compile(r'\bReact(?:\.js)?\b', re.IGNORECASE)
        })
        self.soft_patterns = {skill: re.compile(rf'\b{re.escape(skill)}\b', re.IGNORECASE) for skill in SOFT_SKILLS}

    def extract_skills(self, text_content: str) -> Tuple[Set[str], Set[str]]:
        """Extracts technical and soft skills from the combined title & description text."""
        if not text_content:
            return set(), set()
            
        tech_found = set()
        soft_found = set()
        
        for skill, pattern in self.tech_patterns.items():
            if pattern.search(text_content):
                tech_found.add(skill)
                
        for skill, pattern in self.soft_patterns.items():
            if pattern.search(text_content):
                soft_found.add(skill)
                
        return tech_found, soft_found

    def extract_experience(self, text_content: str) -> Tuple[float, float]:
        """Extracts minimum and maximum experience required in years from text."""
        if not text_content:
            return None, None
            
        # Standardize space and dash variations
        text_clean = re.sub(r'[\u2013\u2014]', '-', text_content) # en-dash and em-dash to hyphen
        
        # Pattern 1: X-Y years / X to Y years
        range_pattern = re.compile(r'\b(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:years|yrs|yr|year)\b', re.IGNORECASE)
        match = range_pattern.search(text_clean)
        if match:
            try:
                min_exp = float(match.group(1))
                max_exp = float(match.group(2))
                return min_exp, max_exp
            except ValueError:
                pass
                
        # Pattern 2: X+ years / X+ yrs
        plus_pattern = re.compile(r'\b(\d+(?:\.\d+)?)\s*\+\s*(?:years|yrs|yr|year)\b', re.IGNORECASE)
        match = plus_pattern.search(text_clean)
        if match:
            try:
                min_exp = float(match.group(1))
                # Set max experience as min_exp + 4 as a fallback representation
                return min_exp, min_exp + 4.0
            except ValueError:
                pass

        # Pattern 3: Experience: X years / Experience: X yrs
        exp_pattern = re.compile(r'(?:experience|exp)(?:\s*level)?\s*(?::|—|-)?\s*(\d+(?:\.\d+)?)\s*(?:years|yrs|yr|year)?\b', re.IGNORECASE)
        match = exp_pattern.search(text_clean)
        if match:
            try:
                min_exp = float(match.group(1))
                return min_exp, min_exp  # Assuming exact match as both min and max
            except ValueError:
                pass
                
        return None, None

    def determine_job_category(self, title: str) -> str:
        """Categorizes job listings into standardized roles based on job title."""
        if not title:
            return "Other"
            
        title_lower = title.lower()
        
        # Check in order of specificity
        for category, keywords in ROLE_CATEGORIES.items():
            for keyword in keywords:
                # Use word boundaries or check if exact phrase is contained
                if keyword in title_lower:
                    # Clean the category string for user display
                    return " ".join([w.capitalize() for w in category.split("_")])
                    
        return "Other"

    def determine_work_mode(self, text_content: str) -> str:
        """Determines if a job is remote, hybrid, or onsite from description."""
        if not text_content:
            return "Onsite"
            
        text_lower = text_content.lower()
        
        if "remote" in text_lower or "work from home" in text_lower or "wfh" in text_lower:
            return "Remote"
        elif "hybrid" in text_lower or "flexible work" in text_lower or "partially remote" in text_lower:
            return "Hybrid"
        else:
            return "Onsite"

    def standardize_salary(self, salary_min: float, salary_max: float, country: str) -> Tuple[float, float, float, str]:
        """Standardizes salary to USD based on the country and returns min, max, mid, and currency."""
        # Map country to standard currency
        country_clean = country.lower().strip() if country else "india"
        
        if "united kingdom" in country_clean or "uk" in country_clean or "gb" in country_clean:
            currency = "GBP"
        elif "united states" in country_clean or "us" in country_clean or "usa" in country_clean:
            currency = "USD"
        elif "canada" in country_clean or "ca" in country_clean:
            currency = "CAD"
        elif "australia" in country_clean or "au" in country_clean:
            currency = "AUD"
        elif "europe" in country_clean or "germany" in country_clean or "france" in country_clean:
            currency = "EUR"
        else:
            currency = "INR" # Default to India INR
            
        exchange_rate = CURRENCY_EXCHANGE_TO_USD.get(currency, 1.0)
        
        if salary_min is None and salary_max is None:
            return None, None, None, currency
            
        if salary_min is not None and salary_max is None:
            salary_max = salary_min
        if salary_max is not None and salary_min is None:
            salary_min = salary_max
            
        # Convert to USD
        salary_min_usd = float(salary_min) * exchange_rate
        salary_max_usd = float(salary_max) * exchange_rate
        salary_mid_usd = (salary_min_usd + salary_max_usd) / 2.0
        
        return salary_min_usd, salary_max_usd, salary_mid_usd, currency

# Example test run
if __name__ == "__main__":
    cleaner = JobDataCleaner()
    test_desc = "Seeking a Data Analyst with 3 - 6 years experience in Python, SQL, and Power BI. Experience with AWS is a plus."
    tech, soft = cleaner.extract_skills(test_desc)
    min_exp, max_exp = cleaner.extract_experience(test_desc)
    category = cleaner.determine_job_category("Senior Python Developer")
    mode = cleaner.determine_work_mode(test_desc)
    sal_min, sal_max, sal_mid, curr = cleaner.standardize_salary(500000, 800000, "India")
    
    print("Test Description parsing:")
    print(f"Technical Skills: {tech}")
    print(f"Soft Skills: {soft}")
    print(f"Experience: {min_exp} - {max_exp} years")
    print(f"Category: {category}")
    print(f"Work Mode: {mode}")
    print(f"Standardized Salary (INR): {sal_min} - {sal_max} USD (Mid: {sal_mid}) in {curr}")
