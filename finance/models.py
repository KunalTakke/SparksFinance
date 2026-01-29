"""
Enhanced Models for SparksFinance Application
Includes proper field types, validation, and audit trails
"""
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, EmailValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal


class BankAccount(models.Model):
    """
    Enhanced User Account Model with proper field types and validation
    Replaces the original CreateUser model
    """
    # User relationship
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='bank_account'
    )
    
    # Account details
    account_number = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text="Unique account number"
    )
    
    branch = models.CharField(
        max_length=100,
        help_text="Bank branch name"
    )
    
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Current account balance"
    )
    
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
        ('N', 'Prefer not to say'),
    ]
    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        default='N'
    )
    
    # Status and limits
    is_active = models.BooleanField(default=True)
    daily_transfer_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('100000.00'),
        help_text="Maximum amount that can be transferred per day"
    )
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'bank_accounts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account_number']),
            models.Index(fields=['user']),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.account_number}"
    
    def clean(self):
        """Validate model data"""
        if self.balance < 0:
            raise ValidationError("Balance cannot be negative")
        if self.daily_transfer_limit < 0:
            raise ValidationError("Daily transfer limit cannot be negative")
    
    def has_sufficient_balance(self, amount):
        """Check if account has sufficient balance"""
        return self.balance >= amount
    
    def get_daily_transfer_total(self):
        """Get total amount transferred today"""
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_transfers = self.sent_transactions.filter(
            status='completed',
            created_at__gte=today_start
        ).aggregate(total=models.Sum('amount'))
        return today_transfers['total'] or Decimal('0.00')
    
    def can_transfer(self, amount):
        """Check if transfer is allowed"""
        if not self.is_active:
            return False, "Account is not active"
        
        if amount <= 0:
            return False, "Transfer amount must be positive"
        
        if not self.has_sufficient_balance(amount):
            return False, "Insufficient balance"
        
        daily_total = self.get_daily_transfer_total()
        if daily_total + amount > self.daily_transfer_limit:
            return False, f"Daily transfer limit exceeded. Limit: {self.daily_transfer_limit}, Used: {daily_total}"
        
        return True, "Transfer allowed"


class Transaction(models.Model):
    """
    Enhanced Transaction Model with status tracking and audit trail
    Replaces the original TransferMoney model
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Transaction details
    transaction_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        editable=False
    )
    
    sender = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name='sent_transactions',
        help_text="Account sending money"
    )
    
    receiver = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name='received_transactions',
        help_text="Account receiving money"
    )
    
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Transfer amount"
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Transaction description or note"
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True, null=True)
    
    # Balance snapshots (for audit trail)
    sender_balance_before = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True
    )
    sender_balance_after = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True
    )
    receiver_balance_before = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True
    )
    receiver_balance_after = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True
    )
    
    class Meta:
        db_table = 'transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['sender', 'created_at']),
            models.Index(fields=['receiver', 'created_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.transaction_id}: {self.sender} → {self.receiver} ({self.amount})"
    
    def clean(self):
        """Validate transaction data"""
        if self.sender == self.receiver:
            raise ValidationError("Cannot transfer money to the same account")
        
        if self.amount <= 0:
            raise ValidationError("Transfer amount must be positive")
    
    def save(self, *args, **kwargs):
        # Generate transaction ID if not exists
        if not self.transaction_id:
            import uuid
            self.transaction_id = f"TXN{timezone.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:8].upper()}"
        
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    """
    Audit log for all important actions in the system
    """
    ACTION_CHOICES = [
        ('account_created', 'Account Created'),
        ('account_updated', 'Account Updated'),
        ('transaction_initiated', 'Transaction Initiated'),
        ('transaction_completed', 'Transaction Completed'),
        ('transaction_failed', 'Transaction Failed'),
        ('login', 'User Login'),
        ('logout', 'User Logout'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs'
    )
    
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    
    # Related objects
    related_transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    related_account = models.ForeignKey(
        BankAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.action} by {self.user} at {self.created_at}"
