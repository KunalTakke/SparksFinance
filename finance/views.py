"""
Complete Views for SparksFinance Application
Compatible with enhanced templates
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.utils import timezone
from decimal import Decimal, InvalidOperation
import logging

from .models import BankAccount, Transaction, AuditLog
from .forms import (
    UserRegistrationForm, BankAccountForm, 
    TransferMoneyForm, LoginForm
)
from .services import TransactionService, AuditService

logger = logging.getLogger(__name__)


# ==================== Authentication Views ====================

def login_view(request):
    """User login view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                auth_login(request, user)
                AuditService.log_action(
                    user=user,
                    action='login',
                    description=f'User {username} logged in',
                    request=request
                )
                messages.success(request, f'Welcome back, {user.first_name}!')
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid username or password')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = LoginForm()
    
    return render(request, 'finance/login.html', {'form': form})


@login_required
def logout_view(request):
    """User logout view"""
    AuditService.log_action(
        user=request.user,
        action='logout',
        description=f'User {request.user.username} logged out',
        request=request
    )
    auth_logout(request)
    messages.info(request, 'You have been logged out successfully')
    return redirect('login')


def register_view(request):
    """User registration view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        user_form = UserRegistrationForm(request.POST)
        account_form = BankAccountForm(request.POST)
        
        if user_form.is_valid() and account_form.is_valid():
            try:
                with db_transaction.atomic():
                    # Create user
                    user = user_form.save(commit=False)
                    user.set_password(user_form.cleaned_data['password'])
                    user.save()
                    
                    # Create bank account
                    account = account_form.save(commit=False)
                    account.user = user
                    account.save()
                    
                    # Log the action
                    AuditService.log_action(
                        user=user,
                        action='account_created',
                        description=f'Account created for {user.get_full_name()}',
                        related_account=account,
                        request=request
                    )
                    
                    messages.success(
                        request,
                        f'Account created successfully! Your account number is {account.account_number}'
                    )
                    return redirect('login')
            
            except Exception as e:
                logger.error(f"Registration error: {str(e)}")
                messages.error(request, 'An error occurred during registration. Please try again.')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        user_form = UserRegistrationForm()
        account_form = BankAccountForm()
    
    return render(request, 'finance/register.html', {
        'user_form': user_form,
        'account_form': account_form
    })


# ==================== Main Views ====================

def index(request):
    """Home page view"""
    return render(request, 'finance/index.html')


@login_required
def dashboard(request):
    """User dashboard with account overview"""
    try:
        account = request.user.bank_account
    except BankAccount.DoesNotExist:
        messages.error(request, 'No bank account found. Please contact support.')
        return redirect('index')
    
    # Get recent transactions
    sent_transactions = account.sent_transactions.filter(
        status='completed'
    ).select_related('receiver', 'receiver__user').order_by('-created_at')[:5]
    
    received_transactions = account.received_transactions.filter(
        status='completed'
    ).select_related('sender', 'sender__user').order_by('-created_at')[:5]
    
    # Calculate statistics
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sent = account.sent_transactions.filter(
        status='completed',
        created_at__gte=today_start
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    today_received = account.received_transactions.filter(
        status='completed',
        created_at__gte=today_start
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    context = {
        'account': account,
        'sent_transactions': sent_transactions,
        'received_transactions': received_transactions,
        'today_sent': today_sent,
        'today_received': today_received,
        'remaining_daily_limit': account.daily_transfer_limit - today_sent,
    }
    
    return render(request, 'finance/dashboard.html', context)


@login_required
def users_list(request):
    """List all active bank accounts with pagination"""
    accounts = BankAccount.objects.filter(
        is_active=True
    ).select_related('user').order_by('-created_at')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        accounts = accounts.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(account_number__icontains=search_query) |
            Q(branch__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(accounts, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
    }
    
    return render(request, 'finance/users.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def transfer_money(request):
    """Transfer money between accounts with validation"""
    try:
        sender_account = request.user.bank_account
    except BankAccount.DoesNotExist:
        messages.error(request, 'No bank account found')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = TransferMoneyForm(request.POST, sender=sender_account)
        
        if form.is_valid():
            receiver_account = form.cleaned_data['receiver']
            amount = form.cleaned_data['amount']
            description = form.cleaned_data.get('description', '')
            
            # Use TransactionService to handle the transfer
            success, message, transaction_obj = TransactionService.transfer_money(
                sender=sender_account,
                receiver=receiver_account,
                amount=amount,
                description=description,
                request=request
            )
            
            if success:
                messages.success(request, message)
                return redirect('transaction_history')  # Redirect to history instead
            else:
                messages.error(request, message)
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = TransferMoneyForm(sender=sender_account)
    
    context = {
        'form': form,
        'account': sender_account,
    }
    
    return render(request, 'finance/transfer_money.html', context)


@login_required
def transaction_history(request):
    """View transaction history with filters"""
    try:
        account = request.user.bank_account
    except BankAccount.DoesNotExist:
        messages.error(request, 'No bank account found')
        return redirect('index')
    
    # Get all transactions (sent and received)
    transactions = Transaction.objects.filter(
        Q(sender=account) | Q(receiver=account)
    ).select_related('sender', 'receiver', 'sender__user', 'receiver__user').order_by('-created_at')
    
    # Filter by type
    filter_type = request.GET.get('type', 'all')
    if filter_type == 'sent':
        transactions = transactions.filter(sender=account)
    elif filter_type == 'received':
        transactions = transactions.filter(receiver=account)
    
    # Filter by status
    filter_status = request.GET.get('status', 'all')
    if filter_status != 'all':
        transactions = transactions.filter(status=filter_status)
    
    # Date range filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        transactions = transactions.filter(created_at__gte=date_from)
    if date_to:
        transactions = transactions.filter(created_at__lte=date_to)
    
    # Pagination
    paginator = Paginator(transactions, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'filter_type': filter_type,
        'filter_status': filter_status,
        'date_from': date_from,
        'date_to': date_to,
        'account': account,
    }
    
    return render(request, 'finance/transaction_history.html', context)


@login_required
def transaction_detail(request, transaction_id):
    """View detailed information about a specific transaction"""
    try:
        account = request.user.bank_account
    except BankAccount.DoesNotExist:
        messages.error(request, 'No bank account found')
        return redirect('index')
    
    # Get transaction and verify user has access
    transaction_obj = get_object_or_404(Transaction, transaction_id=transaction_id)
    
    if transaction_obj.sender != account and transaction_obj.receiver != account:
        return HttpResponseForbidden("You don't have permission to view this transaction")
    
    # For now, redirect to history (can create detail template later)
    return redirect('transaction_history')


# ==================== AJAX/API Views ====================

@login_required
@require_http_methods(["GET"])
def check_balance_ajax(request):
    """AJAX endpoint to check current balance"""
    try:
        account = request.user.bank_account
        return JsonResponse({
            'success': True,
            'balance': float(account.balance),
            'account_number': account.account_number
        })
    except BankAccount.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'No bank account found'
        }, status=404)


@login_required
@require_http_methods(["POST"])
def validate_transfer_ajax(request):
    """AJAX endpoint to validate transfer before submission"""
    try:
        sender_account = request.user.bank_account
        receiver_account_number = request.POST.get('receiver_account')
        amount = request.POST.get('amount')
        
        # Validate inputs
        if not receiver_account_number or not amount:
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields'
            }, status=400)
        
        try:
            amount = Decimal(amount)
        except (InvalidOperation, ValueError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid amount format'
            }, status=400)
        
        # Get receiver account
        try:
            receiver_account = BankAccount.objects.get(
                account_number=receiver_account_number,
                is_active=True
            )
        except BankAccount.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Receiver account not found'
            }, status=404)
        
        # Validate transfer
        can_transfer, reason = sender_account.can_transfer(amount)
        
        if can_transfer:
            return JsonResponse({
                'success': True,
                'message': 'Transfer can proceed',
                'receiver_name': receiver_account.user.get_full_name(),
                'amount': float(amount),
                'new_balance': float(sender_account.balance - amount)
            })
        else:
            return JsonResponse({
                'success': False,
                'error': reason
            }, status=400)
    
    except Exception as e:
        logger.error(f"Validation error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'An error occurred during validation'
        }, status=500)