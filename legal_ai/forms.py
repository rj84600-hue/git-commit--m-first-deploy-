from django import forms
from django.contrib.auth.models import User
from .models import AdvocateProfile

class AdvocateSignupForm(forms.ModelForm):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = AdvocateProfile
        fields = ['name', 'address', 'phone', 'email']