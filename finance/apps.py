from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'finance'
    verbose_name = 'Finance & Banking'
    
    def ready(self):
        """Import signal handlers when app is ready"""
        # import finance.signals  # Uncomment if using signals
        pass
