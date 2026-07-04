import os
import pickle
import logging
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report, mean_absolute_error, mean_squared_error, r2_score

# Database connection configuration
DB_USER = "root"
DB_PASSWORD = "MyNewPassword123!"
DB_HOST = "localhost"
DB_PORT = "3306"
DB_NAME = "job_market_db"
DB_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_data_from_db():
    logging.info("Connecting to database to extract training data...")
    engine = create_engine(DB_URL)
    
    # Query all job postings with company and location details
    query_jobs = """
        SELECT 
            jp.job_id,
            jp.title,
            jp.description,
            jp.experience_min,
            jp.experience_max,
            jp.job_category,
            jp.is_remote,
            jp.salary_min_usd,
            jp.salary_max_usd,
            jp.salary_mid_usd,
            c.company_name,
            l.city,
            l.region,
            l.country
        FROM job_postings jp
        JOIN companies c ON jp.company_id = c.company_id
        LEFT JOIN locations l ON jp.location_id = l.location_id
    """
    df_jobs = pd.read_sql(query_jobs, engine)
    
    # Query skills associated with jobs
    query_skills = """
        SELECT 
            js.job_id,
            s.skill_name
        FROM job_skills js
        JOIN skills s ON js.skill_id = s.skill_id
    """
    df_skills = pd.read_sql(query_skills, engine)
    
    engine.dispose()
    logging.info(f"Retrieved {len(df_jobs)} job records and {len(df_skills)} skill mappings.")
    return df_jobs, df_skills

def train_category_classifier(df_jobs):
    logging.info("--- Training Job Category Classifier ---")
    
    # Combine title and description for richer text features
    df = df_jobs.copy()
    df['text_features'] = df['title'] + " " + df['description'].fillna("")
    
    # Filter rows with valid categories (exclude very minor or null)
    df = df[df['job_category'].notna() & (df['job_category'] != "")]
    
    X = df['text_features']
    y = df['job_category']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y if len(y.unique()) > 1 and y.value_counts().min() > 1 else None)
    
    # Create text classification pipeline
    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(max_features=1500, stop_words='english', ngram_range=(1, 2))),
        ('classifier', RandomForestClassifier(n_estimators=100, random_state=42))
    ])
    
    pipeline.fit(X_train, y_train)
    
    # Evaluate model
    y_pred = pipeline.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    logging.info(f"Category Classifier Accuracy: {accuracy:.4f}")
    logging.info("\n" + classification_report(y_test, y_pred, zero_division=0))
    
    # Save model
    os.makedirs('models', exist_ok=True)
    model_path = 'models/category_model.pkl'
    with open(model_path, 'wb') as f:
        pickle.dump(pipeline, f)
    logging.info(f"Saved Category Classifier model to {model_path}")
    
    return pipeline

def train_salary_regressor(df_jobs, df_skills):
    logging.info("--- Training Salary Predictor ---")
    
    df = df_jobs.copy()
    
    # Filter for listings with valid salary data
    df = df[df['salary_mid_usd'].notna() & (df['salary_mid_usd'] > 0)]
    
    if len(df) < 15:
        logging.warning("Too few records with salary data to train a robust regression model. Fabricating a small synthetic sample or skipping...")
        # To avoid failure in sparse testing environments, we'll bootstrap if needed
        # but with UK data we expect 80+ records.
        if len(df) == 0:
            logging.error("No salary data available. Skipping salary model training.")
            return None
            
    # Process skills: pivot skills table so each skill is a column
    # We select the top 20 most frequent skills to avoid high dimensionality
    if not df_skills.empty:
        top_skills = df_skills['skill_name'].value_counts().head(20).index.tolist()
        for skill in top_skills:
            # Check if job_id has this skill
            job_has_skill = df_skills[df_skills['skill_name'] == skill]['job_id'].tolist()
            df[f'skill_{skill}'] = df['job_id'].isin(job_has_skill).astype(int)
    else:
        top_skills = []
        
    # Prepare features and target
    categorical_features = ['job_category', 'country', 'is_remote']
    numeric_features = ['experience_min', 'experience_max']
    skill_features = [f'skill_{s}' for s in top_skills]
    
    features = categorical_features + numeric_features + skill_features
    X = df[features]
    y = df['salary_mid_usd']
    
    # Define preprocessing pipelines
    numeric_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler())
    ])
    
    categorical_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='most_frequent')),
        ('onehot', OneHotEncoder(handle_unknown='ignore'))
    ])
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, numeric_features),
            ('cat', categorical_transformer, categorical_features)
        ],
        remainder='passthrough' # Leave skill features (already binary) as-is
    )
    
    # Create regression pipeline
    pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('regressor', RandomForestRegressor(n_estimators=100, random_state=42))
    ])
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    pipeline.fit(X_train, y_train)
    
    # Evaluate model
    y_pred = pipeline.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)
    
    logging.info(f"Salary Regressor MAE: ${mae:.2f}")
    logging.info(f"Salary Regressor RMSE: ${rmse:.2f}")
    logging.info(f"Salary Regressor R2 Score: {r2:.4f}")
    
    # Save model and top skills vocabulary (needed for prediction features)
    model_path = 'models/salary_model.pkl'
    model_payload = {
        'pipeline': pipeline,
        'features': features,
        'top_skills': top_skills
    }
    with open(model_path, 'wb') as f:
        pickle.dump(model_payload, f)
    logging.info(f"Saved Salary Regressor model and features to {model_path}")
    
    return pipeline

def main():
    try:
        df_jobs, df_skills = get_data_from_db()
        if df_jobs.empty:
            logging.error("No job records in database. Ensure you run scraper and ETL first.")
            return
            
        train_category_classifier(df_jobs)
        train_salary_regressor(df_jobs, df_skills)
        logging.info("ML Pipeline training completed successfully!")
    except Exception as e:
        logging.error(f"Error in ML pipeline training: {e}")

if __name__ == "__main__":
    main()
