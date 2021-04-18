from django.contrib import admin

# Register your models here.
from  .models import CreateUser,TransferMoney

admin.site.register(CreateUser)
admin.site.register(TransferMoney)