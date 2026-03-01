import os
import io
from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages

# AI
from groq import Groq
from openai import OpenAI

# PDF
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT

# Models
from .models import AdvocateProfile, Notice


# ================= HOME =================
def home(request):
    return render(request, "home.html")


# ================= CREATE NOTICE =================
@login_required
def create_notice(request):

    profile = get_object_or_404(AdvocateProfile, user=request.user)
    notice_text = ""

    if request.method == "POST":

        # ---------- FORM DATA ----------
        client_name = request.POST.get("client")
        opposite = request.POST.get("opposite")
        opposite_address = request.POST.get("opposite_address")
        case_type = request.POST.get("case")
        description = request.POST.get("description")

        # ---------- INTEREST CALCULATION ----------
        amount = request.POST.get("amount")
        interest = request.POST.get("interest")
        date = request.POST.get("date")

        interest_text = ""

        if amount and interest and date:
            try:
                amount = float(amount)
                interest = float(interest)

                start_date = datetime.strptime(date, "%Y-%m-%d")
                today = datetime.today()

                days = (today - start_date).days
                years = days / 365

                interest_amount = (amount * interest * years) / 100
                total_amount = amount + interest_amount

                interest_text = f"""
Outstanding Amount: Rs. {amount:,.0f}
Interest (@{interest}% p.a.): Rs. {interest_amount:,.0f}
Total Amount Due: Rs. {total_amount:,.0f}
"""

            except:
                interest_text = ""

        # ---------- CASE INSTRUCTIONS ----------
        case_instruction = {
            "Payment Due": "This is a civil recovery legal notice for non-payment of money.",
            "Cheque Bounce": "This is a legal notice under Section 138 Negotiable Instruments Act for cheque dishonour.",
            "Property Dispute": "This is a notice regarding illegal interference in possession of property.",
            "Agreement Violation": "This is a breach of contract legal notice demanding compliance."
        }.get(case_type, "Draft a general legal notice.")

        # =====================================================
        # 1️⃣ GROQ → STRUCTURE FACTS
        # =====================================================

        groq_client = Groq(api_key=settings.GROQ_API_KEY)

        groq_prompt = f"""
You are a legal assistant.

Convert the following client complaint into clear legal facts.

Case Type: {case_type}
Instruction: {case_instruction}

Client Name: {client_name}
Opposite Party: {opposite}
Opposite Address: {opposite_address}
Facts: {description}

Return:
- clean facts
- bullet points
- no legal language
"""

        groq_response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": groq_prompt}],
            temperature=0.3,
        )

        structured_facts = groq_response.choices[0].message.content

        # =====================================================
        # 2️⃣ DEEPSEEK → FINAL LEGAL NOTICE
        # =====================================================

        deepseek = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com"
        )

        final_prompt = f"""
You are a senior Indian advocate with 20 years experience.

Draft a professional Indian legal notice using the structured facts below.

STRUCTURED FACTS:
{structured_facts}

FINANCIAL DETAILS:
{interest_text}

ADVOCATE DETAILS:
Name: {profile.name}
Office Address: {profile.address}
Phone: {profile.phone}
Email: {profile.email}

RULES:
- Proper legal paragraphs
- Formal language
- 15 day compliance demand
- Do not cite random laws
- Realistic court usable notice
- Address the opposite party first
- End with advocate signature block
"""

        deepseek_response = deepseek.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": final_prompt}],
            temperature=0.4,
        )

        notice_text = deepseek_response.choices[0].message.content

        # SAVE NOTICE
        Notice.objects.create(
            advocate=profile,
            client_name=client_name,
            opposite_party=opposite,
            opposite_address=opposite_address,
            case_type=case_type,
            notice_text=notice_text
        )

        request.session["latest_notice"] = notice_text

    return render(request, "create_notice.html", {
        "notice": notice_text,
        "profile": profile
    })


# ================= PDF DOWNLOAD =================
@login_required
def download_pdf(request):

    text = request.session.get("latest_notice", "")
    if not text:
        return HttpResponse("No notice found")

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(buffer, pagesize=A4)

    title_style = ParagraphStyle(name="Title", fontSize=14, alignment=TA_CENTER)
    body_style = ParagraphStyle(name="Body", fontSize=11, alignment=TA_JUSTIFY)
    sign_style = ParagraphStyle(name="Sign", fontSize=11, alignment=TA_RIGHT)

    story = []

    for line in text.split("\n"):
        line = line.strip()

        if not line:
            story.append(Spacer(1, 12))
            continue

        if "LEGAL NOTICE" in line.upper():
            story.append(Paragraph(line, title_style))
        elif "Advocate" in line or "Phone" in line or "Email" in line:
            story.append(Paragraph(line, sign_style))
        else:
            story.append(Paragraph(line, body_style))

    doc.build(story)
    buffer.seek(0)

    return HttpResponse(buffer, content_type="application/pdf")


# ================= HISTORY =================
@login_required
def notice_history(request):
    profile = get_object_or_404(AdvocateProfile, user=request.user)
    notices = Notice.objects.filter(advocate=profile).order_by('-created_at')
    return render(request, "history.html", {"notices": notices})


# ================= VIEW NOTICE =================
@login_required
def view_notice(request, id):
    notice = get_object_or_404(Notice, id=id)
    request.session["latest_notice"] = notice.notice_text
    return render(request, "create_notice.html", {"notice": notice.notice_text})