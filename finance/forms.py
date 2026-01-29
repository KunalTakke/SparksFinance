"""
Forms for SparksFinance Application
Includes validation and security measures
"""
from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from decimal import Decimal

from .models import BankAccount, Transaction
from .services import AccountService


class LoginForm(forms.Form):
    """User login form"""
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Username',
            'autocomplete': 'username'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password',
            'autocomplete': 'current-password'
        })
    )


class UserRegistrationForm(forms.ModelForm):
    """User registration form"""
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        }),
        min_length=8,
        help_text='Password must be at least 8 characters long'
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm Password'
        }),
        label='Confirm Password'
    )
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Username'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email Address'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First Name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last Name'
            }),
        }
    
    def clean_username(self):
        """Validate username uniqueness"""
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise ValidationError('This username is already taken')
        return username
    
    def clean_email(self):
        """Validate email uniqueness"""
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError('This email is already registered')
        return email
    
    def clean(self):
        """Validate password confirmation"""
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if password and confirm_password and password != confirm_password:
            raise ValidationError('Passwords do not match')
        
        return cleaned_data


class BankAccountForm(forms.ModelForm):
    """Bank account creation/update form"""
    
    class Meta:
        model = BankAccount
        fields = ['branch', 'gender', 'balance']
        widgets = {
            'branch': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Branch Name'
            }),
            'gender': forms.Select(attrs={
                'class': 'form-control'
            }),
            'balance': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Initial Balance',
                'min': '0',
                'step': '0.01'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Generate account number for new accounts
        if not self.instance.pk:
            self.instance.account_number = AccountService.generate_account_number()
    
    def clean_balance(self):
        """Validate initial balance"""
        balance = self.cleaned_data.get('balance')
        if balance < 0:
            raise ValidationError('Initial balance cannot be negative')
        if balance > 1000000:
            raise ValidationError('Initial balance cannot exceed 1,000,000')
        return balance


class TransferMoneyForm(forms.Form):
    """Money transfer form with validation"""
    receiver_account_number = forms.CharField(
        max_length=20,
        label='Receiver Account Number',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter account number',
            'autocomplete': 'off'
        })
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
        label='Amount',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter amount',
            'min': '0.01',
            'step': '0.01'
        })
    )
    description = forms.CharField(
        required=False,
        max_length=500,
        label='Description (Optional)',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Add a note for this transfer',
            'rows': 3
        })
    )
    confirm = forms.BooleanField(
        required=True,
        label='I confirm this transfer',
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    def __init__(self, *args, **kwargs):
        self.sender = kwargs.pop('sender', None)
        super().__init__(*args, **kwargs)
    
    def clean_receiver_account_number(self):
        """Validate receiver account"""
        account_number = self.cleaned_data.get('receiver_account_number')
        
        # Check if account exists and is active
        try:
            receiver = BankAccount.objects.get(
                account_number=account_number,
                is_active=True
            )
        except BankAccount.DoesNotExist:
            raise ValidationError('Receiver account not found or inactive')
        
        # Check if trying to transfer to own account
        if self.sender and receiver == self.sender:
            raise ValidationError('Cannot transfer money to your own account')
        
        # Store receiver for later use
        self.cleaned_data['receiver'] = receiver
        return account_number
    
    def clean_amount(self):
        """Validate transfer amount"""
        amount = self.cleaned_data.get('amount')
        
        if not self.sender:
            return amount
        
        # Check if sender has sufficient balance
        if not self.sender.has_sufficient_balance(amount):
            raise ValidationError(
                f'Insufficient balance. Your current balance is {self.sender.balance}'
            )
        
        # Check daily limit
        daily_total = self.sender.get_daily_transfer_total()
        if daily_total + amount > self.sender.daily_transfer_limit:
            remaining = self.sender.daily_transfer_limit - daily_total
            raise ValidationError(
                f'Daily transfer limit exceeded. You can transfer up to {remaining} more today.'
            )
        
        return amount
    
    def clean(self):
        """Additional validation"""
        cleaned_data = super().clean()
        
        if not cleaned_data.get('confirm'):
            raise ValidationError('Please confirm the transfer')
        
        return cleaned_data


class AccountUpdateForm(forms.ModelForm):
    """Form for updating account details"""
    
    class Meta:
        model = BankAccount
        fields = ['branch', 'daily_transfer_limit']
        widgets = {
            'branch': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Branch Name'
            }),
            'daily_transfer_limit': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Daily Transfer Limit',
                'min': '0',
                'step': '0.01'
            }),
        }
    
    def clean_daily_transfer_limit(self):
        """Validate daily transfer limit"""
        limit = self.cleaned_data.get('daily_transfer_limit')
        if limit < 1000:
            raise ValidationError('Daily transfer limit must be at least 1,000')
        if limit > 10000000:
            raise ValidationError('Daily transfer limit cannot exceed 10,000,000')
        return limit


class TransactionSearchForm(forms.Form):
    """Form for searching/filtering transactions"""
    TRANSACTION_TYPE_CHOICES = [
        ('all', 'All Transactions'),
        ('sent', 'Sent'),
        ('received', 'Received'),
    ]
    
    STATUS_CHOICES = [
        ('all', 'All Statuses'),
        ('completed', 'Completed'),
        ('pending', 'Pending'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    transaction_type = forms.ChoiceField(
        choices=TRANSACTION_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    def clean(self):
        """Validate date range"""
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        
        if date_from and date_to and date_from > date_to:
            raise ValidationError('Start date must be before end date')
        
        return cleaned_data
