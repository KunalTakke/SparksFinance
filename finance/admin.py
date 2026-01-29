"""
Admin interface configuration for finance app
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import BankAccount, Transaction, AuditLog


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ['account_number', 'user_full_name', 'balance', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at', 'gender']
    search_fields = ['account_number', 'user__username', 'user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Account Information', {
            'fields': ('user', 'account_number', 'branch', 'gender')
        }),
        ('Financial Details', {
            'fields': ('balance', 'daily_transfer_limit', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
    user_full_name.short_description = 'Account Holder'
    
    def has_delete_permission(self, request, obj=None):
        # Prevent accidental deletion of accounts
        return request.user.is_superuser


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_id', 'sender_name', 'receiver_name', 'amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['transaction_id', 'sender__account_number', 'receiver__account_number']
    readonly_fields = ['transaction_id', 'created_at', 'completed_at', 'sender_balance_before', 
                       'sender_balance_after', 'receiver_balance_before', 'receiver_balance_after']
    
    fieldsets = (
        ('Transaction Details', {
            'fields': ('transaction_id', 'sender', 'receiver', 'amount', 'description')
        }),
        ('Status', {
            'fields': ('status', 'failure_reason')
        }),
        ('Balance Snapshots', {
            'fields': ('sender_balance_before', 'sender_balance_after', 
                       'receiver_balance_before', 'receiver_balance_after'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'completed_at')
        }),
    )
    
    def sender_name(self, obj):
        return obj.sender.user.get_full_name() or obj.sender.user.username
    sender_name.short_description = 'Sender'
    
    def receiver_name(self, obj):
        return obj.receiver.user.get_full_name() or obj.receiver.user.username
    receiver_name.short_description = 'Receiver'
    
    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of completed transactions for audit purposes
        if obj and obj.status == 'completed':
            return False
        return request.user.is_superuser


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'user', 'created_at', 'ip_address']
    list_filter = ['action', 'created_at']
    search_fields = ['user__username', 'description', 'ip_address']
    readonly_fields = ['user', 'action', 'description', 'ip_address', 'user_agent', 
                       'created_at', 'related_transaction', 'related_account']
    
    def has_add_permission(self, request):
        # Audit logs are created programmatically only
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of audit logs
        return False
    
    def has_change_permission(self, request, obj=None):
        # Audit logs are immutable
        return False
