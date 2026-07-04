import os
import pickle
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "MyNewPassword123!")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "job_market_db")
DB_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Page configuration
st.set_page_config(
    page_title="Job Market Analytics & Salary Predictor",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load custom CSS stylesheet
def local_css(file_name):
    if os.path.exists(file_name):
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

local_css("assets/custom.css")

# Data loading functions with caching
@st.cache_data
def load_job_data():
    try:
        engine = create_engine(DB_URL)
        query = """
            SELECT 
                jp.job_id,
                jp.title,
                jp.description,
                jp.experience_min,
                jp.experience_max,
                jp.job_category,
                jp.is_remote,
                jp.salary_min,
                jp.salary_max,
                jp.salary_min_usd,
                jp.salary_max_usd,
                jp.salary_mid_usd,
                jp.salary_currency,
                jp.posted_date,
                c.company_name,
                l.city,
                l.region,
                l.country
            FROM job_postings jp
            JOIN companies c ON jp.company_id = c.company_id
            LEFT JOIN locations l ON jp.location_id = l.location_id
        """
        df = pd.read_sql(query, engine)
        engine.dispose()
        return df
    except Exception as e:
        st.error(f"Error connecting to database: {e}")
        return pd.DataFrame()

@st.cache_data
def load_job_skills():
    try:
        engine = create_engine(DB_URL)
        query = """
            SELECT 
                js.job_id,
                s.skill_name,
                s.skill_category
            FROM job_skills js
            JOIN skills s ON js.skill_id = s.skill_id
        """
        df = pd.read_sql(query, engine)
        engine.dispose()
        return df
    except Exception as e:
        st.error(f"Error loading job skills: {e}")
        return pd.DataFrame()

# Load models safely
@st.cache_resource
def load_ml_models():
    cat_model, sal_model = None, None
    
    if os.path.exists("models/category_model.pkl"):
        try:
            with open("models/category_model.pkl", "rb") as f:
                cat_model = pickle.load(f)
        except Exception as e:
            logging.error(f"Failed to load category model: {e}")
            
    if os.path.exists("models/salary_model.pkl"):
        try:
            with open("models/salary_model.pkl", "rb") as f:
                sal_model = pickle.load(f)
        except Exception as e:
            logging.error(f"Failed to load salary model: {e}")
            
    return cat_model, sal_model

# ----------------- MAIN APP -----------------

st.markdown('<div class="main-title">Job Market Analytics Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">An end-to-end interactive intelligence tool for job market analytics and salary predictions</div>', unsafe_allow_html=True)

# Fetch Data
df_jobs = load_job_data()
df_skills = load_job_skills()
cat_model, sal_model = load_ml_models()

if df_jobs.empty:
    st.warning("⚠️ No data was found in the database. Please run the scraping and ETL ingestion pipeline first to load data.")
    st.info("Run in terminal:\n`python scraper.py` followed by `python etl_load.py data/raw/api_jobs_...json`")
else:
    # --- Sidebar Filters ---
    st.sidebar.header("🔍 Global Search Filters")
    
    # Filter: Country
    countries = ["All"] + list(df_jobs["country"].dropna().unique())
    selected_country = st.sidebar.selectbox("Country", countries)
    
    # Filter: Job Category
    categories = ["All"] + list(df_jobs["job_category"].dropna().unique())
    selected_category = st.sidebar.selectbox("Job Category", categories)
    
    # Filter: Location
    cities = ["All"] + list(df_jobs[df_jobs["country"] == selected_country]["city"].dropna().unique() if selected_country != "All" else df_jobs["city"].dropna().unique())
    selected_city = st.sidebar.selectbox("City/Location", cities)
    
    # Filter: Work Mode
    work_modes = ["All"] + list(df_jobs["is_remote"].dropna().unique())
    selected_work_mode = st.sidebar.selectbox("Work Mode", work_modes)
    
    # Filter: Experience Level
    exp_level_options = ["All", "Entry Level (< 2 yrs)", "Mid Level (2-5 yrs)", "Senior Level (> 5 yrs)"]
    selected_exp_level = st.sidebar.selectbox("Experience Level", exp_level_options)
    
    # Apply Filtering
    df_filtered = df_jobs.copy()
    
    if selected_country != "All":
        df_filtered = df_filtered[df_filtered["country"] == selected_country]
        
    if selected_category != "All":
        df_filtered = df_filtered[df_filtered["job_category"] == selected_category]
        
    if selected_city != "All":
        df_filtered = df_filtered[df_filtered["city"] == selected_city]
        
    if selected_work_mode != "All":
        df_filtered = df_filtered[df_filtered["is_remote"] == selected_work_mode]
        
    if selected_exp_level == "Entry Level (< 2 yrs)":
        df_filtered = df_filtered[df_filtered["experience_min"] < 2]
    elif selected_exp_level == "Mid Level (2-5 yrs)":
        df_filtered = df_filtered[(df_filtered["experience_min"] >= 2) & (df_filtered["experience_min"] <= 5)]
    elif selected_exp_level == "Senior Level (> 5 yrs)":
        df_filtered = df_filtered[df_filtered["experience_min"] > 5]
        
    # App Tabs
    tab_overview, tab_skills, tab_salaries, tab_search, tab_predictor = st.tabs([
        "📊 Market Overview", 
        "🛠️ Skills Analysis", 
        "💰 Salary Insights", 
        "🔍 Search Postings",
        "🔮 ML Predictor"
    ])

    # ----------------- TAB 1: OVERVIEW -----------------
    with tab_overview:
        # Calculate KPIs
        total_postings = len(df_filtered)
        active_companies = df_filtered["company_name"].nunique()
        
        # Midpoint salary calculations (USD)
        df_salaries_valid = df_filtered[df_filtered["salary_mid_usd"].notna()]
        avg_salary = df_salaries_valid["salary_mid_usd"].mean() if not df_salaries_valid.empty else None
        
        # Remote Ratio
        remote_count = len(df_filtered[df_filtered["is_remote"] == "Remote"])
        remote_ratio = (remote_count / total_postings * 100) if total_postings > 0 else 0
        
        # Render KPIs
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"""
                <div class="kpi-card">
                    <div class="kpi-value">{total_postings}</div>
                    <div class="kpi-label">Total Job Postings</div>
                </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
                <div class="kpi-card">
                    <div class="kpi-value">{active_companies}</div>
                    <div class="kpi-label">Active Companies</div>
                </div>
            """, unsafe_allow_html=True)
        with col3:
            salary_str = f"${avg_salary:,.0f}" if avg_salary else "N/A"
            st.markdown(f"""
                <div class="kpi-card">
                    <div class="kpi-value">{salary_str}</div>
                    <div class="kpi-label">Average Midpoint (USD)</div>
                </div>
            """, unsafe_allow_html=True)
        with col4:
            st.markdown(f"""
                <div class="kpi-card">
                    <div class="kpi-value">{remote_ratio:.1f}%</div>
                    <div class="kpi-label">Remote Postings Ratio</div>
                </div>
            """, unsafe_allow_html=True)
            
        st.write("")
        st.write("")
        
        # Layout: Category and Work Mode Distributions
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            st.markdown('<div class="chart-container">', unsafe_allow_html=True)
            st.subheader("Job Postings by Category")
            category_counts = df_filtered["job_category"].value_counts().reset_index()
            category_counts.columns = ["Category", "Postings"]
            fig_cat = px.bar(
                category_counts, 
                x="Postings", 
                y="Category", 
                orientation="h",
                color="Postings",
                color_continuous_scale="Viridis",
                template="plotly_dark"
            )
            fig_cat.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(l=0, r=0, t=30, b=0), height=350)
            st.plotly_chart(fig_cat, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        with chart_col2:
            st.markdown('<div class="chart-container">', unsafe_allow_html=True)
            st.subheader("Distribution of Work Modes")
            mode_counts = df_filtered["is_remote"].value_counts().reset_index()
            mode_counts.columns = ["Work Mode", "Count"]
            fig_mode = px.pie(
                mode_counts, 
                names="Work Mode", 
                values="Count", 
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Pastel,
                template="plotly_dark"
            )
            fig_mode.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=350)
            st.plotly_chart(fig_mode, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        # Geographic analysis
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("Job Postings by Location")
        location_counts = df_filtered["city"].value_counts().reset_index().head(15)
        location_counts.columns = ["City", "Postings"]
        fig_loc = px.bar(
            location_counts,
            x="City",
            y="Postings",
            color="Postings",
            color_continuous_scale="Purples",
            template="plotly_dark"
        )
        fig_loc.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=350)
        st.plotly_chart(fig_loc, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ----------------- TAB 2: SKILLS ANALYSIS -----------------
    with tab_skills:
        st.subheader("🛠️ Most Demanded Skills in the Market")
        st.write("Understand what capabilities recruiters are actively looking for across technical stack and soft skill criteria.")
        
        # Filter skills based on filtered jobs
        filtered_job_ids = df_filtered["job_id"].tolist()
        df_skills_filtered = df_skills[df_skills["job_id"].isin(filtered_job_ids)]
        
        if df_skills_filtered.empty:
            st.info("No skills data matches your current search filters.")
        else:
            col_tech, col_soft = st.columns(2)
            
            with col_tech:
                st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                st.subheader("Top 15 Technical Skills")
                tech_skills = df_skills_filtered[df_skills_filtered["skill_category"] == "technical"]
                tech_counts = tech_skills["skill_name"].value_counts().reset_index().head(15)
                tech_counts.columns = ["Skill", "Frequency"]
                
                fig_tech = px.bar(
                    tech_counts,
                    x="Frequency",
                    y="Skill",
                    orientation="h",
                    color="Frequency",
                    color_continuous_scale="Blues",
                    template="plotly_dark"
                )
                fig_tech.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(l=0, r=0, t=30, b=0), height=400)
                st.plotly_chart(fig_tech, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
            with col_soft:
                st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                st.subheader("Top Soft Skills & Methodologies")
                soft_skills = df_skills_filtered[df_skills_filtered["skill_category"] == "soft"]
                soft_counts = soft_skills["skill_name"].value_counts().reset_index().head(15)
                soft_counts.columns = ["Skill", "Frequency"]
                
                fig_soft = px.bar(
                    soft_counts,
                    x="Frequency",
                    y="Skill",
                    orientation="h",
                    color="Frequency",
                    color_continuous_scale="Reds",
                    template="plotly_dark"
                )
                fig_soft.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(l=0, r=0, t=30, b=0), height=400)
                st.plotly_chart(fig_soft, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)

    # ----------------- TAB 3: SALARY INSIGHTS -----------------
    with tab_salaries:
        st.subheader("💰 Market Compensation Analytics")
        
        if df_salaries_valid.empty:
            st.warning("⚠️ No listings with salary data matched your current filter criteria. Try expanding filters (e.g. set Country to 'All' or 'United Kingdom').")
        else:
            sal_col1, sal_col2 = st.columns(2)
            
            with sal_col1:
                st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                st.subheader("Salary Distribution (USD)")
                fig_dist = px.histogram(
                    df_salaries_valid,
                    x="salary_mid_usd",
                    nbins=20,
                    labels={"salary_mid_usd": "Midpoint Salary (USD)"},
                    color_discrete_sequence=["#10B981"],
                    opacity=0.75,
                    marginal="rug",
                    template="plotly_dark"
                )
                fig_dist.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=400)
                st.plotly_chart(fig_dist, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
            with sal_col2:
                st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                st.subheader("Salary Range by Job Category (USD)")
                fig_box = px.box(
                    df_salaries_valid,
                    x="job_category",
                    y="salary_mid_usd",
                    color="job_category",
                    labels={"job_category": "Job Category", "salary_mid_usd": "Midpoint Salary (USD)"},
                    template="plotly_dark"
                )
                fig_box.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=400, showlegend=False)
                st.plotly_chart(fig_box, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
            # Experience vs Salary scatter plot
            st.markdown('<div class="chart-container">', unsafe_allow_html=True)
            st.subheader("Midpoint Salary vs Minimum Experience Required")
            df_scatter = df_salaries_valid[df_salaries_valid["experience_min"].notna()]
            
            if df_scatter.empty:
                st.info("No postings have both experience and salary fields populated for a scatter plot.")
            else:
                fig_scatter = px.scatter(
                    df_scatter,
                    x="experience_min",
                    y="salary_mid_usd",
                    color="job_category",
                    size=df_scatter["experience_max"].fillna(df_scatter["experience_min"] + 2),
                    hover_name="title",
                    hover_data=["company_name", "city", "country"],
                    labels={"experience_min": "Min Experience Required (Years)", "salary_mid_usd": "Midpoint Salary (USD)"},
                    template="plotly_dark"
                )
                fig_scatter.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=400)
                st.plotly_chart(fig_scatter, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # ----------------- TAB 4: SEARCH LISTINGS -----------------
    with tab_search:
        st.subheader("🔍 Explore Filtered Job Listings")
        st.write("Query the entire dataset using titles, skills, descriptions, or locations.")
        
        search_query = st.text_input("Enter search keywords (e.g. Python, remote, London, persistent):", "")
        
        df_search = df_filtered.copy()
        if search_query:
            q = search_query.lower()
            mask = (
                df_search["title"].str.lower().str.contains(q, na=False) |
                df_search["description"].str.lower().str.contains(q, na=False) |
                df_search["company_name"].str.lower().str.contains(q, na=False) |
                df_search["city"].str.lower().str.contains(q, na=False)
            )
            df_search = df_search[mask]
            
        st.write(f"Showing {len(df_search)} postings matching your criteria:")
        
        # Display clean columns
        display_cols = ["title", "company_name", "city", "country", "job_category", "is_remote", "experience_min", "salary_currency", "salary_min", "salary_max", "posted_date"]
        
        st.dataframe(
            df_search[display_cols].rename(columns={
                "title": "Job Title",
                "company_name": "Company",
                "city": "City",
                "country": "Country",
                "job_category": "Category",
                "is_remote": "Mode",
                "experience_min": "Min Exp (Yrs)",
                "salary_currency": "Currency",
                "salary_min": "Min Salary",
                "salary_max": "Max Salary",
                "posted_date": "Posted Date"
            }),
            use_container_width=True
        )
        
        # Download filtered data button
        csv_data = df_search.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Filtered Data as CSV",
            data=csv_data,
            file_name="filtered_job_postings.csv",
            mime="text/csv"
        )

    # ----------------- TAB 5: ML PREDICTOR -----------------
    with tab_predictor:
        st.subheader("🔮 Predictive Career intelligence")
        st.write("Using our trained models, predict the category of any job, estimate its salary range in USD, and see recommended skills.")
        
        if not cat_model and not sal_model:
            st.info("🚀 Machine Learning models are currently not loaded. Once you run the ML Pipeline, they will be serialized and become interactive here.")
            st.markdown("""
                To train the models:
                1. Make sure you run the scraper to fetch enough data.
                2. Run the pipeline in the terminal:
                ```bash
                python src/ml_pipeline.py
                ```
                3. Refresh this page to activate the predictor!
            """)
        else:
            col_in, col_res = st.columns([1, 1])
            
            with col_in:
                st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                st.subheader("Job Details Input")
                
                input_title = st.text_input("Job Title:", "Python Backend Developer")
                input_desc = st.text_area("Job Description:", "We are looking for a Python Developer to join our team. Must be experienced with Django, SQL, PostgreSQL, and building RESTful APIs. Agile workflow, Git, and Docker knowledge are highly valued. Experience with AWS is a big plus.")
                
                input_country = st.selectbox("Job Location Country:", ["United Kingdom", "India", "United States", "Canada"])
                input_mode = st.selectbox("Work Mode:", ["Remote", "Hybrid", "Onsite"])
                input_min_exp = st.slider("Min Experience (Years):", 0.0, 15.0, 3.0, 0.5)
                input_max_exp = st.slider("Max Experience (Years):", 0.0, 20.0, 6.0, 0.5)
                
                predict_btn = st.button("🔮 Analyze & Predict")
                st.markdown('</div>', unsafe_allow_html=True)
                
            with col_res:
                if predict_btn:
                    st.markdown('<div class="prediction-box">', unsafe_allow_html=True)
                    
                    # 1. Predict Category
                    pred_category = "Other"
                    if cat_model:
                        combined_text = input_title + " " + input_desc
                        pred_category = cat_model.predict([combined_text])[0]
                    
                    st.markdown(f'<div class="prediction-title">Predicted Job Category</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="prediction-highlight">{pred_category}</div>', unsafe_allow_html=True)
                    
                    # 2. Predict Salary
                    if sal_model:
                        # Extract components from model
                        pipeline_sal = sal_model['pipeline']
                        features = sal_model['features']
                        top_skills = sal_model['top_skills']
                        
                        # Prepare input row dict
                        input_row = {
                            'job_category': pred_category,
                            'country': input_country,
                            'is_remote': input_mode,
                            'experience_min': input_min_exp,
                            'experience_max': input_max_exp
                        }
                        
                        # Set skill columns based on description matching
                        input_text_lower = (input_title + " " + input_desc).lower()
                        for skill in top_skills:
                            has_skill = 1 if re.search(rf'\b{re.escape(skill.lower())}\b', input_text_lower) else 0
                            input_row[f'skill_{skill}'] = has_skill
                            
                        # Build DataFrame matching training features order
                        df_input = pd.DataFrame([input_row])[features]
                        
                        # Predict
                        try:
                            predicted_val = pipeline_sal.predict(df_input)[0]
                            # Create a salary range window of +/- 15%
                            sal_lower = predicted_val * 0.85
                            sal_upper = predicted_val * 1.15
                            
                            st.markdown(f'<div class="prediction-title">Estimated Salary Range (USD / Year)</div>', unsafe_allow_html=True)
                            st.markdown(f'<div class="prediction-highlight">${sal_lower:,.0f} - ${sal_upper:,.0f}</div>', unsafe_allow_html=True)
                            st.write(f"*Predicted Midpoint: **${predicted_val:,.0f}***")
                        except Exception as e:
                            st.error(f"Error predicting salary: {e}")
                    else:
                        st.warning("Salary Predictor model is not available.")
                        
                    # 3. Recommendations
                    st.write("---")
                    st.markdown("##### Recommended Core Skills to Highlight/Learn:")
                    # Look at database to find skills most associated with this category
                    engine = create_engine(DB_URL)
                    query_rec_skills = f"""
                        SELECT s.skill_name, COUNT(*) as freq
                        FROM job_skills js
                        JOIN skills s ON js.skill_id = s.skill_id
                        JOIN job_postings jp ON js.job_id = jp.job_id
                        WHERE jp.job_category = '{pred_category}'
                        GROUP BY s.skill_name
                        ORDER BY freq DESC
                        LIMIT 8
                    """
                    try:
                        df_rec = pd.read_sql(query_rec_skills, engine)
                        if not df_rec.empty:
                            rec_skills_str = ", ".join([f"**{r['skill_name']}**" for _, r in df_rec.iterrows()])
                            st.markdown(f"For **{pred_category}** roles, recruiters frequently request: {rec_skills_str}")
                        else:
                            st.markdown("No recommendations available for this category yet. Build up your data lake for richer recommendations!")
                    except Exception as e:
                        st.write("Could not retrieve skill recommendations.")
                    finally:
                        engine.dispose()
                        
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.info("Enter job details on the left and click 'Analyze & Predict' to view the machine learning outputs.")
