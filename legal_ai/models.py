from django.db import models
from django.contrib.auth.models import User

# Create your models here.


class AdvocateProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    name = models.CharField(max_length=150)
    address = models.TextField()
    phone = models.CharField(max_length=20)
    email = models.EmailField()

    def __str__(self):
        return self.name
    

class Notice(models.Model):
    advocate = models.ForeignKey(AdvocateProfile, on_delete=models.CASCADE, null=True)
    client_name = models.CharField(max_length=200)
    opposite_party = models.CharField(max_length=200)
    opposite_address = models.TextField()
    case_type = models.CharField(max_length=100)
    notice_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.client_name} vs {self.opposite_party}"