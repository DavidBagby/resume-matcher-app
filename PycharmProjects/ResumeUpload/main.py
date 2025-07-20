import streamlit as st
import fitz
from docx import Document
import json
import os
from datetime import datetime


if st.sidebar.button("🧹 Reset usage"):
    st.cache_data.clear()
    st.session_state.clear()
    st.success("Usage limit reset for testing.")

st.sidebar.write("🔐 Stripe key:", st.secrets["stripe"]["secret_key"][:10] + "...")
st.sidebar.write("💵 Price ID:", st.secrets["stripe"]["price_id"])


# --- Load job feed ---
base_dir = os.path.dirname(__file__)
json_path = os.path.join(base_dir, "static_job_feed.json")
with open(json_path, "r") as f:
    job_feed = json.load(f)

SKILLS = [
    "Python", "SQL", "Tableau", "Power BI", "Excel", "R", "Machine Learning",
    "Spark", "Redshift", "Azure", "BigQuery", "Snowflake", "D3.js", "JavaScript"
]

# --- Resume parsing ---
def extract_text(file):
    if file.name.endswith(".pdf"):
        doc = fitz.open(stream=file.read(), filetype="pdf")
        return "".join(p.get_text() for p in doc)
    elif file.name.endswith(".docx"):
        docx = Document(file)
        return "\n".join([p.text for p in docx.paragraphs])
    return ""

def extract_skills(text):
    return [s for s in SKILLS if s.lower() in text.lower()]

def suggest_resume_improvements(missing_skills):
    return [
        f"💡 _Consider adding a bullet point or project showing experience with **{skill}**._"
        for skill in missing_skills
    ]

def get_top_matches_with_feedback(resume_skills, job_feed, pro_user=False, top_n=5):
    results = []
    resume_set = set(s.lower() for s in resume_skills)

    for job in job_feed:
        job_set = set(s.lower() for s in job["skills"])
        matched = resume_set & job_set
        missing = list(job_set - resume_set)
        all_suggestions = suggest_resume_improvements(missing)

        results.append({
            **job,
            "match_score": len(matched),
            "missing_skills": missing,
            "suggestions": all_suggestions if pro_user else all_suggestions[:2]
        })

    return sorted(results, key=lambda x: x["match_score"], reverse=True)[:top_n]

# --- Persistent usage tracking with st.cache_data ---
@st.cache_data
def get_usage_date():
    return st.session_state.get("last_upload_date", None)

def has_uploaded_today():
    today = datetime.now().strftime("%Y-%m-%d")
    return get_usage_date() == today

def mark_upload_today():
    st.session_state["last_upload_date"] = datetime.now().strftime("%Y-%m-%d")

# --- App Start ---
st.title("🎯 Resume Matcher for Data Jobs")
st.subheader("📄 See how your resume matches real data jobs — and get tips to improve it.")

# --- Optional email capture ---
email = st.text_input("📬 Enter your email to receive future resume upgrades (optional):", "")

uploaded_file = st.file_uploader("Upload your resume (PDF or DOCX)", type=["pdf", "docx"])

if uploaded_file:
    if has_uploaded_today():
        st.warning("⚠️ You’ve already scanned a resume today. Upgrade to Pro for unlimited scans.")
    else:
        text = extract_text(uploaded_file)
        resume_skills = extract_skills(text)

        st.success("✅ Resume uploaded! Checking job matches...")
        mark_upload_today()

        st.markdown("🧠 **Extracted Skills:**")
        if resume_skills:
            st.code(", ".join(resume_skills), language="text")
        else:
            st.warning("No recognized skills found. Try a more detailed resume.")

        matches = get_top_matches_with_feedback(resume_skills, job_feed, pro_user=False)

        if all(job["match_score"] == 0 for job in matches):
            st.warning("Your resume didn’t match any of the top job listings. Try adding more technical skills or uploading a more detailed version.")

        st.subheader("🔍 Top Matching Jobs")
        for job in matches:
            with st.container():
                st.markdown(f"""
                ### {job['title']} at {job['company']}
                📍 {job['location']}  
                🔗 [View Job Posting]({job['url']})  
                ✅ **Match Score:** {job['match_score']}  
                ❌ **Missing Skills:** {', '.join(job['missing_skills']) if job['missing_skills'] else 'None'}  
                """)

                if job['suggestions']:
                    with st.expander("💡 Suggestions to Improve Your Resume"):
                        for s in job['suggestions']:
                            st.markdown(s)
                        if len(job['suggestions']) >= 2:
                            st.markdown("*🔒 Unlock full AI suggestions with Resume Checkup Pro*")

                st.markdown("---")

        st.markdown("🚀 Want unlimited scans and full resume rewrite tips?")
        st.button("🔓 Upgrade to Resume Checkup Pro", disabled=True)

    st.caption("🔍 This tool compares your resume to a sample of current data roles from major employers.")
