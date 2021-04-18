from django.db import models
from django.utils import timezone
# Create your models here.
class CreateUser(models.Model):
    user_id=models.AutoField
    email=models.CharField(max_length=30,default="")
    name=models.CharField(max_length=30)
    branch=models.CharField(max_length=30)
    balance=models.IntegerField(default=2000)
    account=models.IntegerField(default=0)
    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
    )
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    
    def __str__(self):
        return self.name
    
class TransferMoney(models.Model):
    name=models.CharField(max_length=30)
    amount=models.IntegerField(default=2000)
    receiver=models.CharField(max_length=30)
    date=models.DateField(default=timezone.now)
    time=models.TimeField(default=timezone.now)
    def __str__(self):
        return self.name

