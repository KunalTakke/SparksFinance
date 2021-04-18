from django.urls import path
from . import views

urlpatterns = [
    path("",views.index,name="financeHome"),
    path("users/",views.users,name="Users"),
    path("createUser/",views.createUser,name="CreateUser"),
    path("transferMoney",views.transferMoney,name="TransferMoney"),
    path("transferHistory/",views.transferHistory,name="TransferHistory")
]
