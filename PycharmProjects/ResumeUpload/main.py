import streamlit as st
import stripe
import json
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from docx import Document

# === Stripe setup === #
stripe.api_key = st.secrets["stripe"]["secret_key"]

# === URL param to unlock Pro === #
query_params = st.experimental_get_query_params()
if query_params.get("pro", ["0"])[0] == "1":
    st.session_state["pro_user"] = True

# === Title === #
st.title("📊 Resume Checkup")
st.caption("Match your resume to top jobs and get feedback — instantly.")

# === Resume Upload === #
uploaded_file = st.file_uploader("Upload your resume (PDF or Word)", type=["pdf", "docx"])

# === Load static job feed === #
with open("static_job_feed.json") as f:
    job_feed = json.load(f)

# === Extract text from uploaded resume === #
def extract_text(file):
    if file.name.endswith(".pdf"):
        from PyPDF2 import PdfReader
        reader = PdfReader(file)
        return " ".join(page.extract_text() for page in reader.pages if page.extract_text())
    elif file.name.endswith(".docx"):
        doc = Document(file)
        return " ".join(p.text for p in doc.paragraphs)
    else:
        return ""

# === Basic keyword matching === #
def extract_skills(text):
    common_skills = [
        "python", "sql", "tableau", "power bi", "excel", "statistics", "machine learning",
        "data visualization", "dashboards", "etl", "bigquery", "aws", "azure"
    ]
    text_lower = text.lower()
    return [skill for skill in common_skills if skill in text_lower]

def get_top_matches_with_feedback(resume_skills, job_feed, pro_user=False):
    matches = []
    for job in job_feed:
        match_count = len(set(resume_skills) & set(job["keywords"]))
        suggestions = []
        if pro_user:
            for kw in job["keywords"]:
                if kw not in resume_skills:
                    suggestions.append(f"💡 Consider adding '{kw}' to highlight relevance for '{job['title']}'")
        matches.append({
            "title": job["title"],
            "company": job["company"],
            "match_score": match_count,
            "suggestions": suggestions
        })
    return sorted(matches, key=lambda x: x["match_score"], reverse=True)[:3]

# === PDF generation === #
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
    c.drawString(50, y, "Top Matching Jobs:")
    y -= 20
    for job in matches:
        c.drawString(70, y, f"{job['title']} at {job['company']} ({job['match_score']} matches)")
        y -= 15
        if y < 100:
            c.showPage()
            y = height - 50

    y -= 10
    c.drawString(50, y, "Suggestions to Improve Your Resume:")
    y -= 20
    for s in suggestions[:5]:
        c.drawString(70, y, f"• {s.replace('💡 ', '')}")
        y -= 15
        if y < 100:
            c.showPage()
            y = height - 50

    c.save()
    buffer.seek(0)
    return buffer

# === Main logic === #
if uploaded_file:
    text = extract_text(uploaded_file)
    resume_skills = extract_skills(text)
    matches = get_top_matches_with_feedback(resume_skills, job_feed, pro_user=st.session_state.get("pro_user", False))

    st.subheader("📌 Extracted Skills")
    st.write(", ".join(resume_skills))

    st.subheader("🏆 Top Matching Jobs")
    for job in matches:
        st.markdown(f"**{job['title']} at {job['company']}**")
        st.caption(f"Skill match: {job['match_score']} out of {len(job_feed[0]['keywords'])}")
        if st.session_state.get("pro_user", False):
            for suggestion in job["suggestions"]:
                st.markdown(suggestion)

    if st.session_state.get("pro_user", False):
        pdf_buffer = generate_resume_pdf(resume_skills, matches, [s for job in matches for s in job['suggestions']])
        st.download_button(
            label="📄 Download Match Report (PDF)",
            data=pdf_buffer,
            file_name="resume_match_report.pdf",
            mime="application/pdf"
        )

# === Upgrade to Pro === #
st.divider()
st.subheader("🔓 Want better results?")
if not st.session_state.get("pro_user", False):
    if st.button("Upgrade to Resume Checkup Pro"):
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
                window.open("{session.url}", "_blank");
            </script>
            """,
            height=0,
        )
else:
    st.success("✅ You have Pro access! Enjoy full features.")
