import uuid
from django.db import models


class Receipt(models.Model):
    """
    A receipt issued for a VERIFIED payment. The receipt number is the
    tenant-facing identifier; internal IDs and the M-Pesa transaction code
    are never printed on it (spec §24).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.PROTECT,
        related_name='receipts')
    payment = models.OneToOneField(
        'finance.Payment', on_delete=models.PROTECT, related_name='receipt')

    receipt_number = models.CharField(max_length=32, unique=True)

    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='receipts_issued', null=True, blank=True)

    class Meta:
        verbose_name = 'Receipt'
        verbose_name_plural = 'Receipts'
        ordering = ['-issued_at']
        indexes = [
            models.Index(fields=['organization', '-issued_at']),
        ]

    def __str__(self):
        return self.receipt_number
