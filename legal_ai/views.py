import os
import io
from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.contrib import messages

# AI
from groq import Groq
from openai import OpenAI

# Models & Forms
from .models import AdvocateProfile, Notice
from .forms import AdvocateSignupForm

# PDF
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT

# ================= HOME =================
def home(request):
    return render(request, "home.html")


# ================= SIGNUP =================
def signup(request):

    if request.method == "POST":
        form = AdvocateSignupForm(request.POST)

        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            user = User.objects.create_user(username=username, password=password)

            AdvocateProfile.objects.create(
                user=user,
                name=form.cleaned_data['name'],
                address=form.cleaned_data['address'],
                phone=form.cleaned_data['phone'],
                email=form.cleaned_data['email'],
            )

            login(request, user)
            return redirect('create_notice')

    else:
        form = AdvocateSignupForm()

    return render(request, "signup.html", {"form": form})


# ================= CREATE NOTICE =================
@login_required
def create_notice(request):

    profile = get_object_or_404(AdvocateProfile, user=request.user)
    notice_text = ""

    if request.method == "POST":

        client_name = request.POST.get("client")
        opposite = request.POST.get("opposite")
        opposite_address = request.POST.get("opposite_address")
        case_type = request.POST.get("case")
        description = request.POST.get("description")

        # ---------- INTEREST ----------
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
                pass

        # ==================================================
        # 1️⃣ GROQ (STRUCTURE FACTS)
        # ==================================================
        groq_client = Groq(api_key=settings.GROQ_API_KEY)

        groq_prompt = f"""
Convert this complaint into structured legal facts.

Case: {case_type}
Client: {client_name}
Opposite Party: {opposite}
Address: {opposite_address}
Facts: {description}

Return bullet points only.
"""

        groq_response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": groq_prompt}],
            temperature=0.3,
            max_tokens=1200,
        )

        structured_facts = groq_response.choices[0].message.content

        # ==================================================
        # 2️⃣ DEEPSEEK (FINAL NOTICE)
        # ==================================================
        deepseek = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com"
        )

        final_prompt = f"""
You are a senior Indian advocate.

Draft a professional legal notice using:

FACTS:
{structured_facts}

FINANCIAL:
{interest_text}

ADVOCATE DETAILS:
Name: {profile.name}
Address: {profile.address}
Phone: {profile.phone}
Email: {profile.email}

Rules:
- Formal legal tone
- 15 day demand
- Proper paragraphs
- Signature block
"""

        deepseek_response = deepseek.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": final_prompt}],
            temperature=0.4,
        )

        notice_text = deepseek_response.choices[0].message.content

        # SAVE
        Notice.objects.create(
            advocate=profile,
            client_name=client_name,
            opposite_party=opposite,
            opposite_address=opposite_address,
            case_type=case_type,
            notice_text=notice_text
        )

        request.session["latest_notice"] = notice_text

    return render(request, "create_notice.html", {"notice": notice_text, "profile": profile})


# ================= PDF DOWNLOAD =================
@login_required
def download_pdf(request):

    text = request.session.get("latest_notice", "")
    if not text:
        return HttpResponse("No notice found")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    body = ParagraphStyle(name="body", fontSize=11, alignment=TA_JUSTIFY)
    story = []

    for line in text.split("\n"):
        story.append(Paragraph(line, body))
        story.append(Spacer(1, 8))

    doc.build(story)
    buffer.seek(0)

    return HttpResponse(buffer, content_type="application/pdf")


# ================= WORD DOWNLOAD =================
@login_required
def download_word(request):

    from docx import Document
    from docx.shared import Pt

    text = request.session.get("latest_notice", "")
    if not text:
        return HttpResponse("No notice found")

    document = Document()
    style = document.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(12)

    for line in text.split("\n"):
        document.add_paragraph(line)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    response['Content-Disposition'] = 'attachment; filename="legal_notice.docx"'

    document.save(response)
    return response


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