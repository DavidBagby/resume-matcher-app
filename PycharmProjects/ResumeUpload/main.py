import streamlit as st
import fitz  # PyMuPDF
from docx import Document
import json
import os

# --- Load job feed ---
base_dir = os.path.dirname(__file__)
json_path = os.path.join(base_dir, "static_job_feed.json")
with open(json_path, "r") as f:
    job_feed = json.load(f)

# --- Skill list (expandable) ---
SKILLS = ["Python", "SQL", "Tableau", "Power BI", "Excel", "R", "Machine Learning", "Spark", "Redshift", "Azure"]

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

# --- Match and feedback engine ---
def suggest_resume_improvements(missing_skills):
    return [
        f"Consider adding a bullet point or project showing experience with **{skill}**."
        for skill in missing_skills
    ]

def get_top_matches_with_feedback(resume_skills, job_feed, top_n=5):
    results = []
    resume_set = set(s.lower() for s in resume_skills)

    for job in job_feed:
        job_set = set(s.lower() for s in job["skills"])
        matched = resume_set & job_set
        missing = list(job_set - resume_set)

        results.append({
            **job,
            "match_score": len(matched),
            "missing_skills": missing,
            "suggestions": suggest_resume_improvements(missing)
        })

    return sorted(results, key=lambda x: x["match_score"], reverse=True)[:top_n]

# --- Streamlit UI ---
st.title("🎯 Resume Matcher for Data Jobs")
uploaded_file = st.file_uploader("Upload your resume (PDF or DOCX)", type=["pdf", "docx"])

if uploaded_file:
    text = extract_text(uploaded_file)
    resume_skills = extract_skills(text)

    st.success("Resume uploaded successfully!")
    st.write("🧠 **Extracted Skills:**", ", ".join(resume_skills))

    matches = get_top_matches_with_feedback(resume_skills, job_feed)

    st.subheader("🔍 Top Matching Jobs")
    for job in matches:
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
                    st.markdown(f"- {s}")
