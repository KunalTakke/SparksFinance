"""
Service Layer for SparksFinance Application
Encapsulates business logic and ensures transaction integrity
"""
from django.db import transaction as db_transaction
from django.utils import timezone
from decimal import Decimal
import logging

from .models import BankAccount, Transaction, AuditLog

logger = logging.getLogger(__name__)


class TransactionService:
    """Service for handling money transfers with ACID properties"""
    
    @staticmethod
    @db_transaction.atomic
    def transfer_money(sender, receiver, amount, description='', request=None):
        """
        Transfer money between accounts with full transaction support
        
        Args:
            sender (BankAccount): Sending account
            receiver (BankAccount): Receiving account
            amount (Decimal): Amount to transfer
            description (str): Transaction description
            request (HttpRequest): HTTP request object for audit logging
        
        Returns:
            tuple: (success: bool, message: str, transaction: Transaction or None)
        """
        try:
            # Validation
            if sender == receiver:
                return False, "Cannot transfer money to the same account", None
            
            if amount <= 0:
                return False, "Transfer amount must be positive", None
            
            # Check if sender can make the transfer
            can_transfer, reason = sender.can_transfer(amount)
            if not can_transfer:
                return False, reason, None
            
            # Lock accounts to prevent race conditions
            sender = BankAccount.objects.select_for_update().get(pk=sender.pk)
            receiver = BankAccount.objects.select_for_update().get(pk=receiver.pk)
            
            # Double-check balance after locking (in case of concurrent transactions)
            if sender.balance < amount:
                return False, "Insufficient balance", None
            
            # Create transaction record
            transaction_obj = Transaction.objects.create(
                sender=sender,
                receiver=receiver,
                amount=amount,
                description=description,
                status='pending',
                sender_balance_before=sender.balance,
                receiver_balance_before=receiver.balance
            )
            
            try:
                # Perform the transfer
                sender.balance -= amount
                receiver.balance += amount
                
                # Update transaction record
                transaction_obj.sender_balance_after = sender.balance
                transaction_obj.receiver_balance_after = receiver.balance
                transaction_obj.status = 'completed'
                transaction_obj.completed_at = timezone.now()
                
                # Save changes
                sender.save()
                receiver.save()
                transaction_obj.save()
                
                # Log the action
                AuditService.log_action(
                    user=sender.user,
                    action='transaction_completed',
                    description=f'Transfer of {amount} from {sender.account_number} to {receiver.account_number}',
                    related_transaction=transaction_obj,
                    request=request
                )
                
                logger.info(
                    f"Transfer completed: {transaction_obj.transaction_id} - "
                    f"{amount} from {sender.account_number} to {receiver.account_number}"
                )
                
                return True, f"Transfer successful! Transaction ID: {transaction_obj.transaction_id}", transaction_obj
            
            except Exception as e:
                # Mark transaction as failed
                transaction_obj.status = 'failed'
                transaction_obj.failure_reason = str(e)
                transaction_obj.save()
                
                logger.error(f"Transfer failed: {str(e)}")
                raise
        
        except Exception as e:
            logger.error(f"Transfer error: {str(e)}")
            return False, f"Transfer failed: {str(e)}", None
    
    @staticmethod
    def get_account_statement(account, date_from=None, date_to=None):
        """
        Generate account statement for a given period
        
        Args:
            account (BankAccount): Account to generate statement for
            date_from (datetime): Start date
            date_to (datetime): End date
        
        Returns:
            dict: Statement data with transactions and balance information
        """
        transactions = Transaction.objects.filter(
            db_transaction.Q(sender=account) | db_transaction.Q(receiver=account),
            status='completed'
        ).order_by('created_at')
        
        if date_from:
            transactions = transactions.filter(created_at__gte=date_from)
        if date_to:
            transactions = transactions.filter(created_at__lte=date_to)
        
        # Calculate totals
        sent_total = sum(
            t.amount for t in transactions if t.sender == account
        )
        received_total = sum(
            t.amount for t in transactions if t.receiver == account
        )
        
        return {
            'account': account,
            'transactions': transactions,
            'sent_total': sent_total,
            'received_total': received_total,
            'net_change': received_total - sent_total,
            'opening_balance': account.balance - (received_total - sent_total),
            'closing_balance': account.balance,
            'date_from': date_from,
            'date_to': date_to,
        }
    
    @staticmethod
    def cancel_transaction(transaction_obj, reason=''):
        """
        Cancel a pending transaction
        
        Args:
            transaction_obj (Transaction): Transaction to cancel
            reason (str): Cancellation reason
        
        Returns:
            tuple: (success: bool, message: str)
        """
        if transaction_obj.status != 'pending':
            return False, "Only pending transactions can be cancelled"
        
        try:
            transaction_obj.status = 'cancelled'
            transaction_obj.failure_reason = reason
            transaction_obj.save()
            
            logger.info(f"Transaction cancelled: {transaction_obj.transaction_id}")
            return True, "Transaction cancelled successfully"
        
        except Exception as e:
            logger.error(f"Cancellation error: {str(e)}")
            return False, f"Failed to cancel transaction: {str(e)}"


class AuditService:
    """Service for audit logging"""
    
    @staticmethod
    def log_action(user, action, description, related_transaction=None, 
                   related_account=None, request=None):
        """
        Log an action to the audit log
        
        Args:
            user (User): User performing the action
            action (str): Action type
            description (str): Action description
            related_transaction (Transaction): Related transaction object
            related_account (BankAccount): Related account object
            request (HttpRequest): HTTP request object
        
        Returns:
            AuditLog: Created audit log entry
        """
        try:
            ip_address = None
            user_agent = None
            
            if request:
                # Get IP address
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    ip_address = x_forwarded_for.split(',')[0]
                else:
                    ip_address = request.META.get('REMOTE_ADDR')
                
                # Get user agent
                user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            audit_log = AuditLog.objects.create(
                user=user,
                action=action,
                description=description,
                ip_address=ip_address,
                user_agent=user_agent,
                related_transaction=related_transaction,
                related_account=related_account
            )
            
            return audit_log
        
        except Exception as e:
            logger.error(f"Audit logging error: {str(e)}")
            return None
    
    @staticmethod
    def get_user_activity(user, limit=50):
        """
        Get recent activity for a user
        
        Args:
            user (User): User to get activity for
            limit (int): Maximum number of records to return
        
        Returns:
            QuerySet: Audit log entries
        """
        return AuditLog.objects.filter(user=user).order_by('-created_at')[:limit]


class AccountService:
    """Service for account management operations"""
    
    @staticmethod
    def generate_account_number():
        """
        Generate a unique account number
        
        Returns:
            str: Unique account number
        """
        import random
        import string
        
        while True:
            # Format: SPFYYMMDD + 8 random digits
            date_part = timezone.now().strftime('%y%m%d')
            random_part = ''.join(random.choices(string.digits, k=8))
            account_number = f"SPF{date_part}{random_part}"
            
            # Check if unique
            if not BankAccount.objects.filter(account_number=account_number).exists():
                return account_number
    
    @staticmethod
    def deactivate_account(account, reason=''):
        """
        Deactivate an account
        
        Args:
            account (BankAccount): Account to deactivate
            reason (str): Deactivation reason
        
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            account.is_active = False
            account.save()
            
            AuditService.log_action(
                user=account.user,
                action='account_updated',
                description=f'Account deactivated. Reason: {reason}',
                related_account=account
            )
            
            logger.info(f"Account deactivated: {account.account_number}")
            return True, "Account deactivated successfully"
        
        except Exception as e:
            logger.error(f"Deactivation error: {str(e)}")
            return False, f"Failed to deactivate account: {str(e)}"
    
    @staticmethod
    def update_daily_limit(account, new_limit):
        """
        Update daily transfer limit for an account
        
        Args:
            account (BankAccount): Account to update
            new_limit (Decimal): New daily limit
        
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            old_limit = account.daily_transfer_limit
            account.daily_transfer_limit = new_limit
            account.save()
            
            AuditService.log_action(
                user=account.user,
                action='account_updated',
                description=f'Daily limit updated from {old_limit} to {new_limit}',
                related_account=account
            )
            
            logger.info(f"Daily limit updated for {account.account_number}: {new_limit}")
            return True, "Daily limit updated successfully"
        
        except Exception as e:
            logger.error(f"Limit update error: {str(e)}")
            return False, f"Failed to update daily limit: {str(e)}"
