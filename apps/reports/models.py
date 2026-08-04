import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class ExpenseCategory(models.Model):
    """A lightweight category for manual operating expenses (rent,
    utilities, salaries, etc.) -- separate from apps.inventory.Purchase,
    which already tracks stock-buying spend on its own. Reports fold
    both together into one Expenses/Profit picture."""
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expense_categories_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reports_expense_category'
        ordering = ['name']
        verbose_name_plural = 'Expense categories'

    def __str__(self):
        return self.name


class Expense(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='expenses')

    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(1)])
    expense_date = models.DateField(default=timezone.localdate, db_index=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reports_expense'
        ordering = ['-expense_date', '-created_at']
        indexes = [models.Index(fields=['expense_date'])]

    def __str__(self):
        return f'{self.reference_code} — {self.description} (KSh {self.amount})'

    @property
    def reference_code(self):
        return f'EXP-{self.pk:06d}' if self.pk else 'EXP-PENDING'
