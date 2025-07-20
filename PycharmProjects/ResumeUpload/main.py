import streamlit as st
import fitz
from docx import Document
import json
import os
from datetime import datetime
import stripe
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import re

st.session_state["pro_user"] = True

stripe.api_key = st.secrets["stripe"]["secret_key"]

if st.sidebar.button("🪩 Reset usage"):
    st.cache_data.clear()
    st.session_state.clear()
    st.success("Usage limit reset for testing.")

# --- Load job feed ---
base_dir = os.path.dirname(__file__)
json_path = os.path.join(base_dir, "static_job_feed.json")
with open(json_path, "r") as f:
    job_feed = json.load(f)

SKILLS = [
    "Python", "SQL", "Tableau", "Power BI", "Excel", "R", "Machine Learning",
    "Spark", "Redshift", "Azure", "BigQuery", "Snowflake", "D3.js", "JavaScript"
]
WEAK_VERBS = ["helped", "worked on", "assisted", "involved in", "supported", "participated"]
STRONG_VERBS = ["developed", "led", "analyzed", "designed", "optimized", "implemented", "engineered"]

def analyze_bullets(bullets):
    suggestions = []
    for b in bullets:
        s = ""
        if any(verb in b.lower() for verb in WEAK_VERBS):
            s += "⚠️ Try using a stronger verb.\n"
        if not re.search(r"\d", b):
            s += "📏 Add metrics or results (e.g. 'increased efficiency by 20%').\n"
        if len(b.split()) < 5:
            s += "✏️ Expand with more detail.\n"
        if s:
            suggestions.append((b, s.strip()))
    return suggestions

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

@st.cache_data
def get_usage_date():
    return st.session_state.get("last_upload_date", None)

def has_uploaded_today():
    today = datetime.now().strftime("%Y-%m-%d")
    return get_usage_date() == today

def mark_upload_today():
    st.session_state["last_upload_date"] = datetime.now().strftime("%Y-%m-%d")

def generate_resume_pdf(resume_skills, matches, suggestions):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "Resume Match Report")

    c.setFont("Helvetica", 12)
    c.drawString(50, height - 90, "Extracted Skills:")
    y = height - 110
    for skill in resume_skills:
        c.drawString(70, y, f"• {skill}")
        y -= 15

    y -= 10
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Top Job Matches:")
    y -= 20
    for job in matches:
        c.setFont("Helvetica", 12)
        c.drawString(70, y, f"{job['title']} at {job['company']} ({job['match_score']} matches)")
        y -= 15
        if y < 100:
            c.showPage()
            y = height - 50

    y -= 10
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Suggestions to Improve Your Resume:")
    y -= 20
    for s in suggestions[:5]:
        c.setFont("Helvetica", 12)
        c.drawString(70, y, f"• {s.replace('💡 ', '')}")
        y -= 15
        if y < 100:
            c.showPage()
            y = height - 50

    c.save()
    buffer.seek(0)
    return buffer

def extract_bullet_points(text):
    lines = text.splitlines()
    bullets = [line.strip() for line in lines if re.match(r"^[-•●*]\s+", line.strip()) or line.strip().startswith("•")]
    return bullets[:15]

# --- App UI ---
st.title("🎯 Resume Matcher for Data Jobs")
st.subheader("📄 See how your resume matches real data jobs — and get tips to improve it.")

email = st.text_input("📬 Enter your email to receive future resume upgrades (optional):", "")
uploaded_file = st.file_uploader("Upload your resume (PDF or DOCX)", type=["pdf", "docx"])

if uploaded_file:
    if has_uploaded_today():
        st.warning("⚠️ You’ve already scanned a resume today. Upgrade to Pro for unlimited scans.")
    else:
        text = extract_text(uploaded_file)
        bullets = extract_bullet_points(text)
        feedback = analyze_bullets(bullets)

        if st.session_state.get("pro_user", False):
            if feedback:
                with st.expander("🧠 Resume Rewrite Suggestions"):
                    for original, tip in feedback:
                        st.markdown(f"🔍 **Original:** {original}")
                        st.markdown(tip)
                        st.markdown("---")
            else:
                st.markdown("✅ Your bullet points look strong!")
        else:
            st.markdown("🔒 Upgrade to Pro to see smart resume rewrite tips.")

        resume_skills = extract_skills(text)

        st.success("✅ Resume uploaded! Checking job matches...")
        mark_upload_today()

        st.markdown("🧠 **Extracted Skills:**")
        if resume_skills:
            st.code(", ".join(resume_skills), language="text")
        else:
            st.warning("No recognized skills found. Try a more detailed resume.")

        matches = get_top_matches_with_feedback(resume_skills, job_feed, pro_user=st.session_state.get("pro_user", False))

        if all(job["match_score"] == 0 for job in matches):
            st.warning("Your resume didn’t match any of the top job listings. Try adding more technical skills or uploading a more detailed version.")

        st.subheader("🔍 Top Matching Jobs")
        for job in matches:
            match_bar = "🟩" * job["match_score"] + "⬜" * (5 - job["match_score"])
            with st.container():
                st.markdown(f"""
                ### {job['title']} at {job['company']}
                📍 {job['location']}  
                🔗 [View Job Posting]({job['url']})  
                ✅ **Match Score:** {job['match_score']} {match_bar}  
                ❌ **Missing Skills:** {', '.join(job['missing_skills']) if job['missing_skills'] else 'None'}  
                """)
                if job['suggestions']:
                    with st.expander("💡 Suggestions to Improve Your Resume"):
                        for s in job['suggestions']:
                            st.markdown(s)
                st.markdown("---")

        if st.session_state.get("pro_user", False):
            pdf_buffer = generate_resume_pdf(resume_skills, matches, [s for job in matches for s in job['suggestions']])
            st.download_button(
                label="📄 Download Match Report (PDF)",
                data=pdf_buffer,
                file_name="resume_match_report.pdf",
                mime="application/pdf"
            )

        if not st.session_state.get("pro_user", False):
            st.divider()
            if st.button("🔓 Want better results? Upgrade to Pro"):
                session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    line_items=[{
                        "price": st.secrets["stripe"]["price_id"],
                        "quantity": 1,
                    }],
                    mode="payment",
                    success_url="https://resume-checkup.streamlit.app/?pro=1",
                    cancel_url="https://resume-checkup.streamlit.app/",
                )
                st.components.v1.html(
                    f"""
                    <script>
                        window.open(\"{session.url}\", \"_blank\");
                    </script>
                    """,
                    height=0,
                )
        else:
            st.success("✅ Pro access unlocked.")

    st.caption("🔍 This tool compares your resume to a sample of current data roles from major employers.")
