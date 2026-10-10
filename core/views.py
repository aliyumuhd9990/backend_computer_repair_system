from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from .models import Device, RepairRequest, RepairStatusHistory, Payment
from .serializers import (
    RegisterSerializer, UserSerializer, DeviceSerializer, RepairRequestSerializer,
    RepairAdminUpdateSerializer, RepairStatusUpdateSerializer, PaymentSerializer,
    RepairStatusHistorySerializer,
)
from .permissions import IsAdminRole, IsTechnicianOrAdmin

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class DeviceViewSet(viewsets.ModelViewSet):
    serializer_class = DeviceSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["brand", "model_name", "serial_number"]
    filterset_fields = ["device_type", "owner"]

    def get_queryset(self):
        user = self.request.user
        qs = Device.objects.select_related("owner")
        if user.is_superuser or user.role == User.Role.ADMIN:
            return qs
        if user.role == User.Role.TECHNICIAN:
            return qs.filter(repair_requests__assigned_technician=user).distinct()
        return qs.filter(owner=user)

    def perform_create(self, serializer):
        user = self.request.user
        if user.role != User.Role.CUSTOMER and not (user.is_superuser or user.role == User.Role.ADMIN):
            raise PermissionDenied("Only customers or administrators can register devices.")
        if user.is_superuser or user.role == User.Role.ADMIN:
            owner_id = self.request.data.get("owner")
            if not owner_id:
                raise ValidationError({"owner": "Administrators must provide an owner ID."})
            try:
                owner = User.objects.get(pk=owner_id, role=User.Role.CUSTOMER)
            except User.DoesNotExist:
                raise ValidationError({"owner": "Choose an existing customer account."})
            serializer.save(owner=owner)
        else:
            serializer.save(owner=user)

    def perform_update(self, serializer):
        obj = self.get_object()
        user = self.request.user
        if obj.owner_id != user.id and not (user.is_superuser or user.role == User.Role.ADMIN):
            raise PermissionDenied("You cannot edit another customer's device.")
        serializer.save()


class RepairRequestViewSet(viewsets.ModelViewSet):
    serializer_class = RepairRequestSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "priority", "assigned_technician", "customer"]
    search_fields = ["problem_description", "device__brand", "device__model_name", "ticket_number"]
    ordering_fields = ["submitted_at", "updated_at", "priority", "status"]

    def get_queryset(self):
        user = self.request.user
        qs = RepairRequest.objects.select_related("customer", "device", "assigned_technician").prefetch_related("status_history", "payments")
        if user.is_superuser or user.role == User.Role.ADMIN:
            return qs
        if user.role == User.Role.TECHNICIAN:
            return qs.filter(assigned_technician=user)
        return qs.filter(customer=user)

    def get_serializer_class(self):
        if self.action in ("partial_update", "update") and (
            self.request.user.is_superuser or self.request.user.role == User.Role.ADMIN
        ):
            return RepairAdminUpdateSerializer
        return RepairRequestSerializer

    def create(self, request, *args, **kwargs):
        if request.user.role != User.Role.CUSTOMER and not (request.user.is_superuser or request.user.role == User.Role.ADMIN):
            raise PermissionDenied("Only customers can submit repair requests.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device_id = serializer.validated_data.get("device")
        if device_id.owner_id != request.user.id and not (request.user.is_superuser or request.user.role == User.Role.ADMIN):
            raise PermissionDenied("You can only submit a repair request for your own device.")
        repair = serializer.save(customer=request.user)
        RepairStatusHistory.objects.create(
            repair=repair, previous_status="", new_status=repair.status,
            note="Repair request submitted.", changed_by=request.user
        )
        return Response(RepairRequestSerializer(repair, context={"request": request}).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.role == User.Role.ADMIN):
            raise PermissionDenied("Only administrators can edit repair administration fields.")
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.role == User.Role.ADMIN):
            raise PermissionDenied("Only administrators can edit repair administration fields.")
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.role == User.Role.ADMIN):
            raise PermissionDenied("Only administrators can delete repair requests.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="update-status")
    def update_status(self, request, pk=None):
        repair = self.get_object()
        user = request.user
        is_admin = user.is_superuser or user.role == User.Role.ADMIN
        is_assigned_technician = user.role == User.Role.TECHNICIAN and repair.assigned_technician_id == user.id
        if not (is_admin or is_assigned_technician):
            raise PermissionDenied("Only an administrator or the assigned technician can update repair status.")
        serializer = RepairStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]
        note = serializer.validated_data.get("note", "")
        previous = repair.status
        repair.status = new_status
        if new_status == RepairRequest.Status.COMPLETED and not repair.completed_at:
            repair.completed_at = timezone.now()
        repair.save()
        RepairStatusHistory.objects.create(
            repair=repair, previous_status=previous, new_status=new_status,
            note=note, changed_by=user
        )
        return Response(RepairRequestSerializer(repair, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="assign-technician")
    def assign_technician(self, request, pk=None):
        if not (request.user.is_superuser or request.user.role == User.Role.ADMIN):
            raise PermissionDenied("Only administrators can assign technicians.")
        repair = self.get_object()
        technician_id = request.data.get("technician_id")
        try:
            technician = User.objects.get(pk=technician_id, role=User.Role.TECHNICIAN)
        except (User.DoesNotExist, TypeError, ValueError):
            raise ValidationError({"technician_id": "Provide a valid technician account ID."})
        repair.assigned_technician = technician
        repair.save(update_fields=["assigned_technician", "updated_at"])
        return Response(RepairRequestSerializer(repair, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        repair = self.get_object()
        if request.user.role != User.Role.CUSTOMER or repair.customer_id != request.user.id:
            raise PermissionDenied("Only the customer who submitted this request can cancel it.")
        if repair.status not in (RepairRequest.Status.SUBMITTED, RepairRequest.Status.DIAGNOSIS):
            raise ValidationError({"detail": "This repair can no longer be cancelled online. Contact the shop."})
        previous = repair.status
        repair.status = RepairRequest.Status.CANCELLED
        repair.save(update_fields=["status", "updated_at"])
        RepairStatusHistory.objects.create(
            repair=repair, previous_status=previous, new_status=repair.status,
            note="Cancelled by customer.", changed_by=request.user
        )
        return Response(RepairRequestSerializer(repair, context={"request": request}).data)


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "method", "repair"]
    search_fields = ["reference", "repair__ticket_number"]

    def get_queryset(self):
        user = self.request.user
        qs = Payment.objects.select_related("repair", "repair__customer", "recorded_by")
        if user.is_superuser or user.role == User.Role.ADMIN:
            return qs
        if user.role == User.Role.TECHNICIAN:
            return qs.none()
        return qs.filter(repair__customer=user)

    def perform_create(self, serializer):
        user = self.request.user
        payment = serializer.save(recorded_by=user)
        if payment.status == Payment.Status.PAID and not payment.paid_at:
            payment.paid_at = timezone.now()
            payment.save(update_fields=["paid_at"])

    def perform_update(self, serializer):
        payment = serializer.save()
        if payment.status == Payment.Status.PAID and not payment.paid_at:
            payment.paid_at = timezone.now()
            payment.save(update_fields=["paid_at"])

    def update(self, request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.role == User.Role.ADMIN):
            raise PermissionDenied("Only administrators can update payment records.")
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.role == User.Role.ADMIN):
            raise PermissionDenied("Only administrators can update payment records.")
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.role == User.Role.ADMIN):
            raise PermissionDenied("Only administrators can delete payment records.")
        return super().destroy(request, *args, **kwargs)


class TechnicianViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAdminRole]
    queryset = User.objects.filter(role=User.Role.TECHNICIAN).order_by("first_name", "last_name")
    search_fields = ["username", "first_name", "last_name", "email"]


class RepairStatusHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RepairStatusHistorySerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["repair", "new_status"]

    def get_queryset(self):
        user = self.request.user
        qs = RepairStatusHistory.objects.select_related("repair", "changed_by")
        if user.is_superuser or user.role == User.Role.ADMIN:
            return qs
        if user.role == User.Role.TECHNICIAN:
            return qs.filter(repair__assigned_technician=user)
        return qs.filter(repair__customer=user)


class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            repairs = RepairRequest.objects.all()
            payments = Payment.objects.filter(status=Payment.Status.PAID)
            data = {
                "role": "admin",
                "customers": User.objects.filter(role=User.Role.CUSTOMER).count(),
                "technicians": User.objects.filter(role=User.Role.TECHNICIAN).count(),
                "devices": Device.objects.count(),
                "total_repairs": repairs.count(),
                "open_repairs": repairs.exclude(status__in=["completed", "delivered", "cancelled"]).count(),
                "completed_repairs": repairs.filter(status__in=["completed", "ready_for_pickup", "delivered"]).count(),
                "paid_amount": payments.aggregate(total=Sum("amount"))["total"] or 0,
                "pending_payments": Payment.objects.filter(status=Payment.Status.PENDING).count(),
                "repairs_by_status": list(repairs.values("status").annotate(count=Count("id")).order_by("status")),
            }
        elif user.role == User.Role.TECHNICIAN:
            repairs = RepairRequest.objects.filter(assigned_technician=user)
            data = {
                "role": "technician",
                "assigned_repairs": repairs.count(),
                "open_repairs": repairs.exclude(status__in=["completed", "delivered", "cancelled"]).count(),
                "completed_repairs": repairs.filter(status__in=["completed", "ready_for_pickup", "delivered"]).count(),
            }
        else:
            repairs = RepairRequest.objects.filter(customer=user)
            data = {
                "role": "customer",
                "my_devices": Device.objects.filter(owner=user).count(),
                "my_repairs": repairs.count(),
                "open_repairs": repairs.exclude(status__in=["completed", "delivered", "cancelled"]).count(),
                "completed_repairs": repairs.filter(status__in=["completed", "ready_for_pickup", "delivered"]).count(),
            }
        return Response(data)
