"""
Comprehensive Test Suite for SparksFinance Application
Tests models, views, services, and business logic
"""
from django.test import TestCase, Client, TransactionTestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.db import transaction as db_transaction
from decimal import Decimal
from unittest.mock import patch
import threading
import time

from finance.models import BankAccount, Transaction, AuditLog
from finance.services import TransactionService, AccountService, AuditService
from finance.forms import TransferMoneyForm, BankAccountForm


class BankAccountModelTest(TestCase):
    """Test BankAccount model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        self.account = BankAccount.objects.create(
            user=self.user,
            account_number='SPF240101TEST001',
            branch='Test Branch',
            balance=Decimal('1000.00'),
            gender='M'
        )
    
    def test_account_creation(self):
        """Test account is created correctly"""
        self.assertEqual(self.account.user, self.user)
        self.assertEqual(self.account.balance, Decimal('1000.00'))
        self.assertTrue(self.account.is_active)
    
    def test_has_sufficient_balance(self):
        """Test balance checking"""
        self.assertTrue(self.account.has_sufficient_balance(Decimal('500.00')))
        self.assertFalse(self.account.has_sufficient_balance(Decimal('1500.00')))
    
    def test_can_transfer_validation(self):
        """Test transfer validation logic"""
        # Positive case
        can_transfer, msg = self.account.can_transfer(Decimal('500.00'))
        self.assertTrue(can_transfer)
        
        # Insufficient balance
        can_transfer, msg = self.account.can_transfer(Decimal('2000.00'))
        self.assertFalse(can_transfer)
        self.assertIn('Insufficient balance', msg)
        
        # Negative amount
        can_transfer, msg = self.account.can_transfer(Decimal('-100.00'))
        self.assertFalse(can_transfer)
        
        # Inactive account
        self.account.is_active = False
        self.account.save()
        can_transfer, msg = self.account.can_transfer(Decimal('100.00'))
        self.assertFalse(can_transfer)
        self.assertIn('not active', msg)
    
    def test_daily_limit_validation(self):
        """Test daily transfer limit"""
        self.account.daily_transfer_limit = Decimal('500.00')
        self.account.save()
        
        # Should fail if exceeds daily limit
        can_transfer, msg = self.account.can_transfer(Decimal('600.00'))
        self.assertFalse(can_transfer)
        self.assertIn('Daily transfer limit', msg)


class TransactionModelTest(TestCase):
    """Test Transaction model"""
    
    def setUp(self):
        self.sender_user = User.objects.create_user(
            username='sender',
            email='sender@example.com',
            password='pass123'
        )
        self.receiver_user = User.objects.create_user(
            username='receiver',
            email='receiver@example.com',
            password='pass123'
        )
        
        self.sender_account = BankAccount.objects.create(
            user=self.sender_user,
            account_number='SPF001',
            branch='Branch A',
            balance=Decimal('1000.00')
        )
        self.receiver_account = BankAccount.objects.create(
            user=self.receiver_user,
            account_number='SPF002',
            branch='Branch B',
            balance=Decimal('500.00')
        )
    
    def test_transaction_creation(self):
        """Test transaction is created with unique ID"""
        txn = Transaction.objects.create(
            sender=self.sender_account,
            receiver=self.receiver_account,
            amount=Decimal('100.00'),
            status='pending'
        )
        
        self.assertIsNotNone(txn.transaction_id)
        self.assertTrue(txn.transaction_id.startswith('TXN'))
        self.assertEqual(txn.status, 'pending')
    
    def test_self_transfer_validation(self):
        """Test cannot transfer to same account"""
        txn = Transaction(
            sender=self.sender_account,
            receiver=self.sender_account,
            amount=Decimal('100.00')
        )
        
        with self.assertRaises(Exception):
            txn.full_clean()


class TransactionServiceTest(TransactionTestCase):
    """Test TransactionService with database transactions"""
    
    def setUp(self):
        self.sender_user = User.objects.create_user(
            username='sender',
            email='sender@example.com',
            password='pass123',
            first_name='Sender',
            last_name='User'
        )
        self.receiver_user = User.objects.create_user(
            username='receiver',
            email='receiver@example.com',
            password='pass123',
            first_name='Receiver',
            last_name='User'
        )
        
        self.sender_account = BankAccount.objects.create(
            user=self.sender_user,
            account_number='SPF001',
            branch='Branch A',
            balance=Decimal('1000.00')
        )
        self.receiver_account = BankAccount.objects.create(
            user=self.receiver_user,
            account_number='SPF002',
            branch='Branch B',
            balance=Decimal('500.00')
        )
    
    def test_successful_transfer(self):
        """Test successful money transfer"""
        initial_sender_balance = self.sender_account.balance
        initial_receiver_balance = self.receiver_account.balance
        amount = Decimal('200.00')
        
        success, message, txn = TransactionService.transfer_money(
            sender=self.sender_account,
            receiver=self.receiver_account,
            amount=amount,
            description='Test transfer'
        )
        
        self.assertTrue(success)
        self.assertIsNotNone(txn)
        self.assertEqual(txn.status, 'completed')
        
        # Refresh from database
        self.sender_account.refresh_from_db()
        self.receiver_account.refresh_from_db()
        
        # Check balances
        self.assertEqual(
            self.sender_account.balance,
            initial_sender_balance - amount
        )
        self.assertEqual(
            self.receiver_account.balance,
            initial_receiver_balance + amount
        )
        
        # Check balance snapshots
        self.assertEqual(txn.sender_balance_before, initial_sender_balance)
        self.assertEqual(txn.sender_balance_after, self.sender_account.balance)
        self.assertEqual(txn.receiver_balance_before, initial_receiver_balance)
        self.assertEqual(txn.receiver_balance_after, self.receiver_account.balance)
    
    def test_insufficient_balance_transfer(self):
        """Test transfer fails with insufficient balance"""
        amount = Decimal('2000.00')
        
        success, message, txn = TransactionService.transfer_money(
            sender=self.sender_account,
            receiver=self.receiver_account,
            amount=amount
        )
        
        self.assertFalse(success)
        self.assertIn('balance', message.lower())
        self.assertIsNone(txn)
    
    def test_self_transfer_prevention(self):
        """Test cannot transfer to same account"""
        success, message, txn = TransactionService.transfer_money(
            sender=self.sender_account,
            receiver=self.sender_account,
            amount=Decimal('100.00')
        )
        
        self.assertFalse(success)
        self.assertIn('same account', message.lower())
    
    def test_negative_amount_transfer(self):
        """Test transfer fails with negative amount"""
        success, message, txn = TransactionService.transfer_money(
            sender=self.sender_account,
            receiver=self.receiver_account,
            amount=Decimal('-100.00')
        )
        
        self.assertFalse(success)
        self.assertIn('positive', message.lower())
    
    def test_atomic_transaction_rollback(self):
        """Test transaction rolls back on error"""
        initial_sender_balance = self.sender_account.balance
        initial_receiver_balance = self.receiver_account.balance
        
        # Force an error by patching the save method
        with patch.object(BankAccount, 'save', side_effect=Exception('Test error')):
            success, message, txn = TransactionService.transfer_money(
                sender=self.sender_account,
                receiver=self.receiver_account,
                amount=Decimal('100.00')
            )
        
        self.assertFalse(success)
        
        # Refresh and check balances haven't changed
        self.sender_account.refresh_from_db()
        self.receiver_account.refresh_from_db()
        
        self.assertEqual(self.sender_account.balance, initial_sender_balance)
        self.assertEqual(self.receiver_account.balance, initial_receiver_balance)
    
    def test_concurrent_transfers(self):
        """Test race condition handling with concurrent transfers"""
        # This is a simplified test - in production, you'd need more sophisticated testing
        amount = Decimal('100.00')
        results = []
        
        def make_transfer():
            success, message, txn = TransactionService.transfer_money(
                sender=self.sender_account,
                receiver=self.receiver_account,
                amount=amount
            )
            results.append((success, message, txn))
        
        # Create multiple threads trying to transfer simultaneously
        threads = [threading.Thread(target=make_transfer) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # Check that final balance is correct
        self.sender_account.refresh_from_db()
        successful_transfers = sum(1 for success, _, _ in results if success)
        expected_balance = Decimal('1000.00') - (amount * successful_transfers)
        self.assertEqual(self.sender_account.balance, expected_balance)


class AccountServiceTest(TestCase):
    """Test AccountService"""
    
    def test_generate_account_number(self):
        """Test account number generation"""
        account_number = AccountService.generate_account_number()
        
        self.assertTrue(account_number.startswith('SPF'))
        self.assertEqual(len(account_number), 17)  # SPF + 6 digits (date) + 8 digits (random)
    
    def test_unique_account_numbers(self):
        """Test that generated account numbers are unique"""
        numbers = set()
        for _ in range(100):
            number = AccountService.generate_account_number()
            self.assertNotIn(number, numbers)
            numbers.add(number)


class TransferMoneyFormTest(TestCase):
    """Test TransferMoneyForm validation"""
    
    def setUp(self):
        self.sender_user = User.objects.create_user(
            username='sender',
            email='sender@example.com',
            password='pass123'
        )
        self.receiver_user = User.objects.create_user(
            username='receiver',
            email='receiver@example.com',
            password='pass123'
        )
        
        self.sender_account = BankAccount.objects.create(
            user=self.sender_user,
            account_number='SPF001',
            branch='Branch A',
            balance=Decimal('1000.00')
        )
        self.receiver_account = BankAccount.objects.create(
            user=self.receiver_user,
            account_number='SPF002',
            branch='Branch B',
            balance=Decimal('500.00')
        )
    
    def test_valid_form(self):
        """Test form with valid data"""
        form_data = {
            'receiver_account_number': 'SPF002',
            'amount': '100.00',
            'description': 'Test transfer',
            'confirm': True
        }
        form = TransferMoneyForm(data=form_data, sender=self.sender_account)
        self.assertTrue(form.is_valid())
    
    def test_self_transfer_validation(self):
        """Test form rejects self-transfer"""
        form_data = {
            'receiver_account_number': 'SPF001',
            'amount': '100.00',
            'confirm': True
        }
        form = TransferMoneyForm(data=form_data, sender=self.sender_account)
        self.assertFalse(form.is_valid())
        self.assertIn('receiver_account_number', form.errors)
    
    def test_insufficient_balance_validation(self):
        """Test form rejects transfer with insufficient balance"""
        form_data = {
            'receiver_account_number': 'SPF002',
            'amount': '2000.00',
            'confirm': True
        }
        form = TransferMoneyForm(data=form_data, sender=self.sender_account)
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
    
    def test_confirmation_required(self):
        """Test form requires confirmation"""
        form_data = {
            'receiver_account_number': 'SPF002',
            'amount': '100.00',
            'confirm': False
        }
        form = TransferMoneyForm(data=form_data, sender=self.sender_account)
        self.assertFalse(form.is_valid())


class ViewsTest(TestCase):
    """Test views with authentication"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        self.account = BankAccount.objects.create(
            user=self.user,
            account_number='SPF001',
            branch='Test Branch',
            balance=Decimal('1000.00')
        )
    
    def test_index_view(self):
        """Test index page loads"""
        response = self.client.get(reverse('finance:index'))
        self.assertEqual(response.status_code, 200)
    
    def test_dashboard_requires_login(self):
        """Test dashboard requires authentication"""
        response = self.client.get(reverse('finance:dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_dashboard_with_login(self):
        """Test dashboard accessible when logged in"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('finance:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test User')
    
    def test_login_view(self):
        """Test login functionality"""
        response = self.client.post(reverse('finance:login'), {
            'username': 'testuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, 302)  # Redirect after login
    
    def test_transfer_money_requires_login(self):
        """Test transfer page requires authentication"""
        response = self.client.get(reverse('finance:transfer_money'))
        self.assertEqual(response.status_code, 302)


class AuditLogTest(TestCase):
    """Test audit logging"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_audit_log_creation(self):
        """Test audit log is created"""
        log = AuditService.log_action(
            user=self.user,
            action='login',
            description='Test login'
        )
        
        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.action, 'login')
    
    def test_get_user_activity(self):
        """Test retrieving user activity"""
        # Create multiple log entries
        for i in range(5):
            AuditService.log_action(
                user=self.user,
                action='login',
                description=f'Login {i}'
            )
        
        activity = AuditService.get_user_activity(self.user, limit=3)
        self.assertEqual(len(activity), 3)


# Performance tests would go here in a real application
# class PerformanceTest(TestCase):
#     """Test performance under load"""
#     pass
