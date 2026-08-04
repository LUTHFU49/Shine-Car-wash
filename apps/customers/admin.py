from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('customer_code', 'full_name', 'phone_number', 'email', 'is_active', 'is_linked_account', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('first_name', 'last_name', 'phone_number', 'email')
    readonly_fields = ('public_id', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    autocomplete_fields = ()

    fieldsets = (
        (None, {'fields': ('first_name', 'last_name', 'email', 'phone_number')}),
        ('Profile', {'fields': ('date_of_birth', 'address', 'notes')}),
        ('Account Link', {'fields': ('user', 'created_by')}),
        ('Status', {'fields': ('is_active', 'deactivated_at')}),
        ('Metadata', {'fields': ('public_id', 'created_at', 'updated_at')}),
    )

    def is_linked_account(self, obj):
        return obj.is_linked_account
    is_linked_account.boolean = True
    is_linked_account.short_description = 'Has Login'
