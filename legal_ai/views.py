from django.shortcuts import render, redirect
from django.conf import settings
from groq import Groq
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from datetime import datetime
import io

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT

# WORD
from docx import Document
from docx.shared import Pt

from .models import AdvocateProfile, Notice
from .forms import AdvocateSignupForm

def home(request):
    return render(request, "home.html")


# ================= SIGNUP =================
def signup(request):

    if request.method == "POST":
        form = AdvocateSignupForm(request.POST)

        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            if User.objects.filter(username=username).exists():
                messages.error(request, "Username already exists")
                return render(request, 'signup.html', {'form': form})

            user = User.objects.create_user(username=username, password=password)

            # profile create
            AdvocateProfile.objects.create(
                user=user,
                name=form.cleaned_data['name'],
                address=form.cleaned_data['address'],
                phone=form.cleaned_data['phone'],
                email=form.cleaned_data['email'],
            )

            messages.success(request, "Account created! Please login.")
            return redirect('login')

    else:
        form = AdvocateSignupForm()

    return render(request, 'signup.html', {'form': form})


# ================= CREATE NOTICE =================
@login_required
def create_notice(request):

    profile = AdvocateProfile.objects.get(user=request.user)

    notice_text = ""

    if request.method == "POST":

        client = Groq(api_key=settings.GROQ_API_KEY)

        client_name = request.POST.get("client")
        opposite = request.POST.get("opposite")
        opposite_address = request.POST.get("opposite_address")
        case_type = request.POST.get("case")
        description = request.POST.get("description")

        # -------- INTEREST CALCULATION --------
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

        # -------- PROMPT --------
        prompt = f"""
You are an experienced Indian advocate.

Draft a COURT-USABLE legal notice in India.

STRICT RULES (Do not break):

1. Start with centered heading:

LEGAL NOTICE

2. Next line:
Through Advocate

3. Mention today's date.

4. Then:

To,
{opposite}
{opposite_address}

5. Subject line:
Subject: Legal Notice regarding {case_type}

6. Then write detailed paragraphs:
- brief facts
- legal liability
- payment/demand
- 15 days compliance period
- legal consequences

Financial Details (include if available):
{interest_text}

IMPORTANT BOTTOM FORMAT (MUST FOLLOW EXACTLY):

Kindly take notice accordingly.

A copy of this notice is retained in my office for record and future legal proceedings.

Sd/-
({profile.name})
Advocate

Address:
{profile.address}

Mobile: {profile.phone}
Email: {profile.email}

VERY IMPORTANT:
- Do NOT place advocate address in the "To" section
- Do NOT invent fake law sections
- Do NOT change the bottom signature structure
"""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )

        notice_text = response.choices[0].message.content

        # SAVE TO DATABASE
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


# ================= HISTORY =================
@login_required
def notice_history(request):

    profile = AdvocateProfile.objects.get(user=request.user)

    notices = Notice.objects.filter(advocate=profile).order_by('-created_at')

    return render(request, "history.html", {"notices": notices})


@login_required
def view_notice(request, id):

    profile = AdvocateProfile.objects.get(user=request.user)

    notice = Notice.objects.get(id=id, advocate=profile)

    request.session["latest_notice"] = notice.notice_text

    return render(request, "create_notice.html", {"notice": notice.notice_text})


# ================= PDF DOWNLOAD =================
@login_required
def download_pdf(request):

    text = request.session.get("latest_notice", "")
    if not text:
        return HttpResponse("No notice found.")

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=50, leftMargin=50,
                            topMargin=50, bottomMargin=50)

    title_style = ParagraphStyle(name="Title", fontSize=14, alignment=TA_CENTER, spaceAfter=20)
    body_style = ParagraphStyle(name="Body", fontSize=11, alignment=TA_JUSTIFY, spaceAfter=10)
    sign_style = ParagraphStyle(name="Sign", fontSize=11, alignment=TA_RIGHT, spaceAfter=8)

    story = []

    for line in text.split("\n"):
        line = line.strip()

        if not line:
            story.append(Spacer(1, 12))
            continue

        if "COURT" in line.upper():
            story.append(Paragraph(line, title_style))
        elif "Sd/-" in line or "Advocate" in line:
            story.append(Paragraph(line, sign_style))
        else:
            story.append(Paragraph(line, body_style))

    doc.build(story)
    buffer.seek(0)

    return HttpResponse(buffer, content_type="application/pdf")


# ================= WORD DOWNLOAD =================
@login_required
def download_word(request):

    text = request.session.get("latest_notice", "")
    if not text:
        return HttpResponse("No notice found.")

    document = Document()

    style = document.styles['Normal']
    font = style.font
    font.name = 'Times New Roman'
    font.size = Pt(12)

    for line in text.split("\n"):
        document.add_paragraph(line)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    response['Content-Disposition'] = 'attachment; filename="Legal_Notice.docx"'

    document.save(response)
    return response