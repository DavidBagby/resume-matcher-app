import streamlit as st
import fitz
from docx import Document
import json
import os
from datetime import datetime
import stripe
from io import BytesIO
from reportlab.lib.pagesizes import letter as PAGE_SIZE
from reportlab.pdfgen import canvas
import re
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.textlabels import Label
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from reportlab.lib import colors
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

stripe.api_key = st.secrets["stripe"]["secret_key"]

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
PASSIVE_PATTERNS = [r"\bwas\b.*\bby\b", r"\bwas responsible for\b", r"\bwas tasked with\b", r"\bwere involved in\b"]

REWRITE_MAP = {
    "helped": "contributed to",
    "worked on": "executed",
    "assisted": "supported delivery of",
    "involved in": "participated in executing",
    "supported": "enabled",
    "participated": "collaborated on"
}

def send_email_with_attachment(to_email, subject, body_text, attachment_data, filename):
    msg = MIMEMultipart()
    msg["From"] = f"{st.secrets['email']['from_name']} <{st.secrets['email']['username']}>"
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body_text, "plain"))

    part = MIMEApplication(attachment_data.read(), Name=filename)
    part["Content-Disposition"] = f'attachment; filename="{filename}"'
    msg.attach(part)

    with smtplib.SMTP(st.secrets["email"]["smtp_host"], st.secrets["email"]["smtp_port"]) as server:
        server.starttls()
        server.login(st.secrets["email"]["username"], st.secrets["email"]["password"])
        server.send_message(msg)

def generate_cover_letter(name: str, skills: list, job: dict) -> str:
    skill_list = ", ".join(skills)
    return f"""
Dear {job['company']} Hiring Team,

I'm excited to apply for the {job['title']} position at {job['company']}. With a strong background in {skill_list}, I believe I can make a meaningful contribution to your team.

In my previous roles, I have successfully applied these skills to solve real-world business challenges, automate workflows, and deliver actionable insights. I’m especially drawn to your mission and the opportunity to work on impactful projects in {job['location']}.

I’ve attached my resume for your review and would welcome the chance to discuss how I can support {job['company']}'s goals. Thank you for considering my application.

Sincerely,  
{name if name else "Your Name"}
""".strip()

def rewrite_bullet(bullet):
    rewritten = bullet
    for weak, strong in REWRITE_MAP.items():
        rewritten = re.sub(rf"\b{weak}\b", strong, rewritten, flags=re.IGNORECASE)
    if not re.search(r"\d", rewritten):
        rewritten += " (add metric)"
    if len(rewritten.split()) < 5:
        rewritten += " (expand with detail)"
    return rewritten.strip()

def generate_rewritten_bullets(bullets):
    rewrites = []
    for b in bullets:
        if any(w in b.lower() for w in WEAK_VERBS) or not re.search(r"\d", b) or len(b.split()) < 5:
            rewritten = rewrite_bullet(b)
            rewrites.append((b, rewritten))
    return rewrites

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
        if any(re.search(pat, b.lower()) for pat in PASSIVE_PATTERNS):
            s += "🔁 Consider rephrasing into active voice.\n"
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
            "matched_skills": list(matched),
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

def generate_resume_pdf(resume_skills, matches, suggestions, full_text="", feedback=None):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    width, height = float(PAGE_SIZE[0]), float(PAGE_SIZE[1])

    if resume_skills:
        from collections import Counter
        c.setFont("Helvetica-Bold", 18)
        c.drawCentredString(width / 2, height - 50, "Skill Breakdown (Pie Chart)")

        # Count skill frequencies
        skill_counts = Counter()
        for line in full_text.splitlines():
            for skill in resume_skills:
                if re.search(rf"\b{re.escape(skill)}\b", line, re.IGNORECASE):
                    skill_counts[skill] += 1

        for skill in resume_skills:
            skill_counts[skill] = max(skill_counts[skill], 1)

        sorted_skills = list(skill_counts.keys())
        skill_data = [skill_counts[skill] for skill in sorted_skills]

        # Setup large centered pie chart
        drawing = Drawing(width, height - 100)
        pie = Pie()
        pie.x = (width - 300) / 2  # center horizontally
        pie.y = (height - 300) / 2 - 30  # center vertically
        pie.width = 300
        pie.height = 300
        pie.data = skill_data
        pie.labels = [f"{skill} ({skill_counts[skill]})" for skill in sorted_skills]
        pie.slices.popout = 4
        pie.slices.strokeWidth = 0.5

        slice_colors = [
            colors.blue, colors.green, colors.orange, colors.purple,
            colors.red, colors.pink, colors.cyan, colors.violet,
            colors.gray, colors.lightgreen
        ]
        for i in range(len(skill_data)):
            pie.slices[i].fillColor = slice_colors[i % len(slice_colors)]

        drawing.add(pie)
        renderPDF.draw(drawing, c, 0, 0)

        c.showPage()  # move to next page for rest of report

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
        c.setFont("Helvetica", 10)
        c.drawString(80, y, f"Matched: {', '.join(job['matched_skills'])}")
        y -= 12
        c.drawString(80, y, f"Missing: {', '.join(job['missing_skills'])}")
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

    if full_text:
        c.showPage()
        y = height - 50
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, "Full Resume Text:")
        y -= 20
        c.setFont("Helvetica", 10)
        for line in full_text.splitlines():
            c.drawString(50, y, line[:100])
            y -= 12
            if y < 50:
                c.showPage()
                y = height - 50

    if feedback:
        c.showPage()
        y = height - 50
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, "Rewritten Bullet Feedback:")
        y -= 20
        for original, tip in feedback:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(50, y, f"• {original[:90]}")
            y -= 12
            c.setFont("Helvetica", 10)
            for line in tip.splitlines():
                c.drawString(60, y, line[:90])
                y -= 12
            y -= 6
            if y < 50:
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

#email = st.text_input("📬 Enter your email to receive future resume upgrades (optional):", "")
uploaded_file = st.file_uploader("Upload your resume (PDF or DOCX)", type=["pdf", "docx"])
#if email:
#    log_path = os.path.join(base_dir, "email_log.txt")
#    with open(log_path, "a") as log:
#        log.write(f"{datetime.now().isoformat()} | {email} | {uploaded_file.name if uploaded_file else 'no file'}\n")

if uploaded_file:
    if has_uploaded_today():
        st.warning("⚠️ You’ve already scanned a resume today. Upgrade to Pro for unlimited scans.")
    else:
        text = extract_text(uploaded_file)
        bullets = extract_bullet_points(text)
        feedback = analyze_bullets(bullets)

        resume_skills = extract_skills(text)
        skill_score = len(resume_skills)
        feedback_score = max(0, 15 - len(feedback))
        total_score = min(100, int((skill_score * 3 + feedback_score * 5)))

        st.markdown(f"### 🧪 Resume Strength: {total_score}%")
        st.progress(total_score)

        # Resume score badge
        if total_score >= 85:
            st.success("🟢 **Excellent Resume** – You're highly competitive for data jobs!")
        elif total_score >= 70:
            st.info("🟡 **Good Resume** – A few tweaks could take this to the next level.")
        elif total_score >= 50:
            st.warning("🟠 **Fair Resume** – You’re on the right track, but there’s room to improve.")
        else:
            st.error("🔴 **Needs Work** – Add detail, metrics, and stronger skills to boost your match.")

        if st.session_state.get("pro_user", False):
            if feedback:
                with st.expander("🧠 Resume Rewrite Suggestions"):
                    for original, tip in feedback:
                        st.markdown(f"🔍 **Original:** {original}")
                        st.markdown(tip)
                        st.markdown("---")
            else:
                st.markdown("✅ Your bullet points look strong!")
            if st.session_state.get("pro_user", False):
                st.subheader("✍️ Build Your Improved Resume Bullets")

                rewritten_bullets = generate_rewritten_bullets(bullets)

                if rewritten_bullets:
                    selected = []
                    with st.form("rewrite_selector_form"):
                        for i, (original, rewritten) in enumerate(rewritten_bullets):
                            st.markdown(f"**🔹 Original:** {original}")
                            accepted = st.checkbox(f"✅ Use this rewrite:", key=f"accept_{i}")
                            if accepted:
                                selected.append(rewritten)
                            st.markdown(f"**🔁 Suggested Rewrite:** {rewritten}")
                            st.markdown("---")

                        submitted = st.form_submit_button("📄 Generate New Resume Section")

                    if submitted and selected:
                        new_resume_text = "\n".join(f"• {line}" for line in selected)
                        st.success("✅ Your improved bullet section is ready!")

                        st.code(new_resume_text, language="text")

                        st.download_button(
                            label="⬇️ Download Rewritten Bullets (TXT)",
                            data=new_resume_text,
                            file_name="improved_resume_bullets.txt",
                            mime="text/plain"
                        )
                    elif submitted and not selected:
                        st.warning("⚠️ You didn’t select any rewrites.")
                else:
                    st.info("✅ No weak bullets found — your resume already looks strong.")

        else:
            st.markdown("🔒 Upgrade to Pro to see smart resume rewrite tips.")

        st.success("✅ Resume uploaded! Checking job matches...")
        mark_upload_today()

        if st.session_state.get("pro_user", False):
            st.subheader("✍️ Resume Rewrite Mode")

            rewritten_bullets = generate_rewritten_bullets(bullets)
            if rewritten_bullets:
                for original, rewrite in rewritten_bullets:
                    with st.container():
                        st.markdown(f"**📝 Original:** {original}")
                        st.markdown(f"**✅ Suggested Rewrite:** {rewrite}")
                        st.markdown("---")

                rewritten_text = "\n".join([r for _, r in rewritten_bullets])
                st.download_button(
                    label="📄 Download Rewritten Bullets (TXT)",
                    data=rewritten_text,
                    file_name="rewritten_resume_bullets.txt",
                    mime="text/plain"
                )
            else:
                st.success("🎉 No rewrite suggestions needed — your bullets already look strong!")
        else:
            st.info("🔒 Upgrade to Pro to unlock full bullet point rewrites.")

        st.markdown("🧠 **Extracted Skills:**")
        if resume_skills:
            st.code(", ".join(resume_skills), language="text")
        else:
            st.warning("No recognized skills found. Try a more detailed resume.")

        st.subheader("🔧 Filter Job Matches")
        location_filter = st.selectbox("📍 Location", options=["Any", "Remote", "On-site"])
        skill_filter = st.multiselect("🛠️ Must Include Skills", options=SKILLS)

        matches = get_top_matches_with_feedback(resume_skills, job_feed, pro_user=st.session_state.get("pro_user", False))
        # Apply filters
        filtered_matches = []
        for job in matches:
            if location_filter != "Any" and location_filter.lower() not in job["location"].lower():
                continue
            if skill_filter and not all(skill.lower() in [s.lower() for s in job["skills"]] for skill in skill_filter):
                continue
            filtered_matches.append(job)

        matches = filtered_matches

        if all(job["match_score"] == 0 for job in matches):
            st.warning("Your resume didn’t match any of the top job listings. Try adding more technical skills or uploading a more detailed version.")

        st.subheader("🔍 Top Matching Jobs")
        for job in matches:
            match_bar = "🟩" * job["match_score"] + "⬜" * (5 - job["match_score"])
            with st.container():
                st.markdown(f"""
                ### {job['title']} at {job['company']}
                📍 {job['location']}   
                ✅ **Match Score:** {job['match_score']} {match_bar}  
                ✅ **Matched Skills:** {', '.join(job['matched_skills']) if job['matched_skills'] else 'None'}  
                ❌ **Missing Skills:** {', '.join(job['missing_skills']) if job['missing_skills'] else 'None'}  
                """)
                if job['suggestions']:
                    with st.expander("💡 Suggestions to Improve Your Resume"):
                        for s in job['suggestions']:
                            st.markdown(s)
                st.markdown("---")

        if st.session_state.get("pro_user", False) and resume_skills and matches:
            st.subheader("📝 Generate Cover Letter")

            name_input = st.text_input("Your name (for closing):", placeholder="Jane Doe")

            job_titles = [f"{job['title']} at {job['company']}" for job in matches]
            job_map = {f"{job['title']} at {job['company']}": job for job in matches}

            selected_title = st.selectbox("🎯 Select a job to generate your cover letter for:", job_titles)
            selected_job = job_map[selected_title]

            if st.button("✍️ Generate AI Cover Letter"):
                cover_letter_text = generate_cover_letter(name_input, resume_skills, selected_job)
                st.success("✅ Cover letter generated:")
                st.code(cover_letter_text, language="text")

                st.download_button(
                    label="📄 Download Cover Letter (TXT)",
                    data=cover_letter_text,
                    file_name="cover_letter.txt",
                    mime="text/plain"
                )

        if st.session_state.get("pro_user", False):
            pdf_buffer = generate_resume_pdf(resume_skills, matches, [s for job in matches for s in job['suggestions']], full_text=text, feedback=feedback)
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
