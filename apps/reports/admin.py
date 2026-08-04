from django.contrib import admin

from .models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    readonly_fields = ('public_id', 'created_at', 'updated_at')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('description', 'category', 'amount', 'expense_date', 'recorded_by', 'is_active')
    list_filter = ('is_active', 'category', 'expense_date')
    search_fields = ('description', 'notes')
    autocomplete_fields = ('category', 'recorded_by')
    readonly_fields = ('public_id', 'created_at', 'updated_at')
    date_hierarchy = 'expense_date'
