from django.shortcuts import render,redirect
from django.http import HttpResponse
from .models import CreateUser,TransferMoney
from django.db.models import F

# Create your views here.
def index(request):
    return render(request,'finance/index.html')

def users(request):
    users=CreateUser.objects.all()
    params={"users":users}
    return render(request,'finance/users.html',params)

def createUser(request):
    if request.method=="POST":
        name=request.POST.get('name','')
        email=request.POST.get('email','')
        balance=request.POST.get('balance','')
        branch=request.POST.get('branch','')
        account=request.POST.get('account','')
        gender=request.POST.get('gender','')
        createUser=CreateUser(name=name,branch=branch,email=email,balance=balance,account=account,gender=gender)
        createUser.save()
    return render(request,'finance/createUser.html')

def transferMoney(request):
    if request.method=="POST":
        name=request.POST.get('name','')
        receiver=request.POST.get('receiver','')
        amount=request.POST.get('amount','')
        transferMoney=TransferMoney(name=name,receiver=receiver,amount=amount)
        transferMoney.save()
        # increment logic implementation
        users=CreateUser.objects.all()
        q1=CreateUser.objects.get(name= receiver)
        q1.balance=F('balance')+amount
        q1.save()
        q2=CreateUser.objects.get(name= name)
        q2.balance=F('balance')- amount
        q2.save()
        return redirect('Users')
    users=CreateUser.objects.all()
    params={"users":users}
    return render(request,'finance/transferMoney.html',params)

def transferHistory(request):
    transfer=TransferMoney.objects.all()
    params={"transfer":transfer}
    return render(request,'finance/transferHistory.html',params)

