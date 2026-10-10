from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User, Device, RepairRequest, RepairStatusHistory, Payment


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Repair service profile", {"fields": ("role", "phone", "address")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Repair service profile", {"fields": ("email", "role", "phone", "address")}),
    )
    list_display = ("username", "email", "first_name", "last_name", "role", "is_staff")
    list_filter = ("role", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")


class RepairStatusHistoryInline(admin.TabularInline):
    model = RepairStatusHistory
    extra = 0
    readonly_fields = ("previous_status", "new_status", "note", "changed_by", "created_at")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "device_type", "brand", "model_name", "serial_number", "created_at")
    search_fields = ("owner__username", "brand", "model_name", "serial_number")
    list_filter = ("device_type",)


@admin.register(RepairRequest)
class RepairRequestAdmin(admin.ModelAdmin):
    list_display = ("ticket_number", "customer", "device", "status", "priority", "assigned_technician", "submitted_at")
    list_filter = ("status", "priority", "submitted_at")
    search_fields = ("ticket_number", "customer__username", "device__brand", "problem_description")
    readonly_fields = ("ticket_number", "submitted_at", "updated_at")
    inlines = [RepairStatusHistoryInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "repair", "amount", "method", "status", "reference", "paid_at")
    list_filter = ("status", "method", "created_at")
    search_fields = ("reference", "repair__ticket_number", "repair__customer__username")
