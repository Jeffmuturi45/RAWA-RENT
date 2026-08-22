from datetime import date
from decimal import Decimal

from django.test import TestCase, Client
from django.db import IntegrityError, transaction

from organizations.models import Organization
from accounts.models import User
from properties.models import Property, Unit
from tenants.models import Tenant
from tenancies.models import Tenancy
from finance.models import Charge, Payment, DepositMovement
from finance.services import (
    rent_service, payment_service, statement_service, arrears_service,
)
from finance.services.payment_service import DuplicatePaymentError


class FinanceTestBase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Test Agency', slug='test-agency')
        self.prop = Property.objects.create(
            organization=self.org, name='Anju Apartments', code='ANJU')
        self.unit = Unit.objects.create(
            prop=self.prop, unit_number='A101',
            rent_amount=Decimal('8000'), deposit_amount=Decimal('8000'),
            status=Unit.Status.OCCUPIED)
        self.tenant = Tenant.objects.create(
            organization=self.org, full_name='John Mwangi',
            phone='0700000000', status=Tenant.Status.ACTIVE)
        self.tenancy = Tenancy.objects.create(
            organization=self.org, tenant=self.tenant, unit=self.unit,
            start_date=date(2026, 8, 1), monthly_rent=Decimal('8000'),
            required_deposit=Decimal('8000'), billing_day=1,
            status=Tenancy.Status.ACTIVE)


class RentGenerationTests(FinanceTestBase):
    def test_generates_one_charge_per_period(self):
        created = rent_service.generate_rent_charges(self.org, 2026, 8)
        self.assertEqual(created, 1)
        charge = Charge.objects.get(tenancy=self.tenancy, period_start=date(2026, 8, 1))
        self.assertEqual(charge.amount, Decimal('8000'))
        self.assertEqual(charge.charge_type, Charge.Type.RENT)

    def test_generation_is_idempotent(self):
        rent_service.generate_rent_charges(self.org, 2026, 8)
        again = rent_service.generate_rent_charges(self.org, 2026, 8)
        self.assertEqual(again, 0)
        self.assertEqual(
            Charge.objects.filter(tenancy=self.tenancy,
                                  period_start=date(2026, 8, 1)).count(), 1)

    def test_unique_constraint_blocks_duplicate_rent(self):
        rent_service.generate_rent_charges(self.org, 2026, 8)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Charge.objects.create(
                    organization=self.org, tenancy=self.tenancy,
                    charge_type=Charge.Type.RENT, period_start=date(2026, 8, 1),
                    amount=Decimal('8000'), due_date=date(2026, 8, 1))


class AllocationTests(FinanceTestBase):
    def setUp(self):
        super().setUp()
        rent_service.generate_rent_charges(self.org, 2026, 8)
        rent_service.generate_rent_charges(self.org, 2026, 9)
        self.aug = Charge.objects.get(tenancy=self.tenancy, period_start=date(2026, 8, 1))
        self.sep = Charge.objects.get(tenancy=self.tenancy, period_start=date(2026, 9, 1))

    def _pay(self, amount, ref=None):
        return payment_service.record_payment(
            organization=self.org, tenant=self.tenant, amount=Decimal(amount),
            payment_date=date(2026, 8, 5), method=Payment.Method.MPESA,
            reference=ref, tenancy=self.tenancy)

    def test_partial_payment(self):
        self._pay('5000')
        self.aug.refresh_from_db()
        self.assertEqual(self.aug.balance, Decimal('3000'))
        self.assertEqual(self.aug.status, Charge.Status.PARTIAL)

    def test_oldest_charge_settled_first(self):
        self._pay('8000')  # exactly clears August, nothing to September
        self.assertEqual(self.aug.status, Charge.Status.PAID)
        self.assertEqual(self.sep.status, Charge.Status.UNPAID)

    def test_overpayment_becomes_credit(self):
        payment = self._pay('20000')  # 8000 + 8000 charges = 16000; 4000 credit
        self.assertEqual(self.aug.status, Charge.Status.PAID)
        self.assertEqual(self.sep.status, Charge.Status.PAID)
        self.assertEqual(payment.unallocated, Decimal('4000'))


class DuplicatePaymentTests(FinanceTestBase):
    def test_duplicate_reference_rejected_by_service(self):
        payment_service.record_payment(
            organization=self.org, tenant=self.tenant, amount=Decimal('1000'),
            payment_date=date(2026, 8, 5), method=Payment.Method.MPESA,
            reference='QK82ABC91X', tenancy=self.tenancy)
        with self.assertRaises(DuplicatePaymentError):
            payment_service.record_payment(
                organization=self.org, tenant=self.tenant, amount=Decimal('1000'),
                payment_date=date(2026, 8, 6), method=Payment.Method.MPESA,
                reference='QK82ABC91X', tenancy=self.tenancy)
        self.assertEqual(Payment.objects.filter(reference='QK82ABC91X').count(), 1)

    def test_blank_references_allow_multiple(self):
        for _ in range(3):
            payment_service.record_payment(
                organization=self.org, tenant=self.tenant, amount=Decimal('500'),
                payment_date=date(2026, 8, 5), method=Payment.Method.CASH,
                reference='', tenancy=self.tenancy)
        self.assertEqual(Payment.objects.filter(tenant=self.tenant).count(), 3)


class DepositTests(FinanceTestBase):
    def test_deposit_split_kept_separate_from_rent(self):
        rent_service.generate_rent_charges(self.org, 2026, 8)
        payment = payment_service.record_payment(
            organization=self.org, tenant=self.tenant, amount=Decimal('16000'),
            payment_date=date(2026, 8, 5), method=Payment.Method.MPESA,
            reference='DEP1', tenancy=self.tenancy, deposit_amount=Decimal('8000'))
        # 8000 to deposit, 8000 to the August rent charge.
        self.tenancy.refresh_from_db()
        self.assertEqual(self.tenancy.deposit_account.balance, Decimal('8000'))
        aug = Charge.objects.get(tenancy=self.tenancy, period_start=date(2026, 8, 1))
        self.assertEqual(aug.status, Charge.Status.PAID)
        self.assertEqual(payment.deposit_allocated, Decimal('8000'))
        self.assertEqual(payment.unallocated, Decimal('0'))


class StatementTests(FinanceTestBase):
    def test_running_balance_and_credit(self):
        rent_service.generate_rent_charges(self.org, 2026, 8)  # +8000 owed
        payment_service.record_payment(
            organization=self.org, tenant=self.tenant, amount=Decimal('10000'),
            payment_date=date(2026, 8, 5), method=Payment.Method.CASH,
            tenancy=self.tenancy)  # pays 8000, 2000 credit
        rows = statement_service.build_statement(self.tenancy)
        self.assertEqual(rows[-1]['balance'], Decimal('-2000'))  # 2000 credit
        summary = statement_service.account_summary(self.tenancy)
        self.assertEqual(summary['outstanding'], Decimal('0'))

    def test_balance_not_stored_on_tenancy(self):
        field_names = {f.name for f in Tenancy._meta.get_fields()}
        self.assertNotIn('balance', field_names)


class CollectionStatsTests(FinanceTestBase):
    def test_stats_derived_from_ledger(self):
        rent_service.generate_rent_charges(self.org, 2026, 8)
        payment_service.record_payment(
            organization=self.org, tenant=self.tenant, amount=Decimal('5000'),
            payment_date=date(2026, 8, 5), method=Payment.Method.CASH,
            tenancy=self.tenancy)
        stats = arrears_service.collection_stats(self.org)
        self.assertEqual(stats['expected'], Decimal('8000'))
        self.assertEqual(stats['collected'], Decimal('5000'))
        self.assertEqual(stats['outstanding'], Decimal('3000'))


class FinanceRBACTests(FinanceTestBase):
    def _user(self, role, email):
        return User.objects.create_user(
            email=email, password='Pw!23456xy', full_name=role,
            role=role, organization=self.org, must_change_password=False)

    def test_receptionist_cannot_record_payment(self):
        u = self._user(User.Role.RECEPTIONIST, 'rec@t.co')
        c = Client(); c.force_login(u)
        r = c.get('/finance/payments/record/', SERVER_NAME='localhost')
        self.assertEqual(r.status_code, 403)

    def test_accounts_officer_can_record_payment(self):
        u = self._user(User.Role.ACCOUNTS_OFFICER, 'acct@t.co')
        c = Client(); c.force_login(u)
        r = c.get('/finance/payments/record/', SERVER_NAME='localhost')
        self.assertEqual(r.status_code, 200)

    def test_receptionist_can_view_payments(self):
        u = self._user(User.Role.RECEPTIONIST, 'rec2@t.co')
        c = Client(); c.force_login(u)
        r = c.get('/finance/', SERVER_NAME='localhost')
        self.assertEqual(r.status_code, 200)
