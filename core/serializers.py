from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers
from .models import Device, RepairRequest, RepairStatusHistory, Payment

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "phone", "address", "role"]
        read_only_fields = ["id", "role"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})
    password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "phone", "address", "password", "password_confirm"]
        read_only_fields = ["id"]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        # Public registration always creates a customer; users cannot self-register as staff.
        validated_data["role"] = User.Role.CUSTOMER
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class DeviceSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.get_full_name", read_only=True)

    class Meta:
        model = Device
        fields = ["id", "owner", "owner_name", "device_type", "brand", "model_name",
                  "serial_number", "description", "created_at"]
        read_only_fields = ["id", "owner", "owner_name", "created_at"]


class RepairStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source="changed_by.username", read_only=True)

    class Meta:
        model = RepairStatusHistory
        fields = ["id", "repair", "previous_status", "new_status", "note", "changed_by", "changed_by_name", "created_at"]
        read_only_fields = fields


class RepairRequestSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.get_full_name", read_only=True)
    device_details = serializers.CharField(source="device.__str__", read_only=True)
    technician_name = serializers.CharField(source="assigned_technician.get_full_name", read_only=True)
    status_history = RepairStatusHistorySerializer(many=True, read_only=True)
    amount_paid = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()

    class Meta:
        model = RepairRequest
        fields = [
            "id", "ticket_number", "customer", "customer_name", "device", "device_details",
            "problem_description", "diagnosis", "estimated_cost", "final_cost", "priority",
            "status", "assigned_technician", "technician_name", "admin_notes", "submitted_at",
            "updated_at", "completed_at", "status_history", "amount_paid", "balance_due",
        ]
        read_only_fields = ["id", "ticket_number", "customer", "status", "assigned_technician",
                            "admin_notes", "submitted_at", "updated_at", "completed_at",
                            "status_history", "amount_paid", "balance_due"]

    def get_amount_paid(self, obj):
        from django.db.models import Sum
        result = obj.payments.filter(status=Payment.Status.PAID).aggregate(total=Sum("amount"))["total"]
        return result or 0

    def get_balance_due(self, obj):
        from django.db.models import Sum
        total = obj.final_cost if obj.final_cost is not None else obj.estimated_cost
        paid = obj.payments.filter(status=Payment.Status.PAID).aggregate(total=Sum("amount"))["total"] or 0
        return max((total or 0) - paid, 0)


class RepairAdminUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepairRequest
        fields = ["diagnosis", "estimated_cost", "final_cost", "priority", "status",
                  "assigned_technician", "admin_notes", "completed_at"]

    def validate_assigned_technician(self, value):
        if value and value.role != User.Role.TECHNICIAN:
            raise serializers.ValidationError("Select an account with the technician role.")
        return value


class RepairStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=RepairRequest.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True)


class PaymentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="repair.customer.get_full_name", read_only=True)
    ticket_number = serializers.UUIDField(source="repair.ticket_number", read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "repair", "ticket_number", "customer_name", "amount", "method",
                  "status", "reference", "recorded_by", "paid_at", "created_at", "notes"]
        read_only_fields = ["id", "ticket_number", "customer_name", "recorded_by", "paid_at", "created_at"]

    def validate_repair(self, repair):
        user = self.context["request"].user
        if not (user.is_superuser or user.role == "admin") and repair.customer_id != user.id:
            raise serializers.ValidationError("You can only make payments for your own repair requests.")
        return repair

    def validate(self, attrs):
        user = self.context["request"].user
        is_admin = user.is_superuser or user.role == "admin"
        requested_status = attrs.get("status", getattr(self.instance, "status", Payment.Status.PENDING))

        # Customers can submit payment intents/records as pending, but cannot
        # mark their own payments as paid or refunded.
        if not is_admin and requested_status in (Payment.Status.PAID, Payment.Status.REFUNDED):
            raise serializers.ValidationError({
                "status": "Only an administrator can confirm a payment or record a refund."
            })

        if requested_status == Payment.Status.PAID and not attrs.get("reference", getattr(self.instance, "reference", None)):
            # Manual cash payments may not have an external reference.
            method = attrs.get("method", getattr(self.instance, "method", Payment.Method.CASH))
            if method not in (Payment.Method.CASH, Payment.Method.OTHER):
                raise serializers.ValidationError({"reference": "A reference is required for this payment method."})
        return attrs
