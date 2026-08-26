from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import date
from decimal import Decimal
import random
import string

User = get_user_model()


class Command(BaseCommand):
    help = 'Seeds RawaRent with realistic demo data'

    def handle(self, *args, **kwargs):
        self.stdout.write('\n=== RawaRent Demo Data Seeder ===\n')

        from organizations.models import Organization
        from properties.models import Property, HouseType, Unit
        from tenants.models import Tenant
        from tenants.services import create_tenant_with_portal_account
        from tenancies.models import Tenancy
        from finance.models import (
            Charge, Payment, PaymentAllocation,
            DepositAccount, DepositMovement
        )
        from receipts.models import Receipt

        def receipt_number(prop_code):
            chars = string.ascii_uppercase + string.digits
            suffix = ''.join(random.choices(chars, k=6))
            return f'REC-{prop_code}-{suffix}'

        with transaction.atomic():

            # ── Organization ──────────────────────────────
            org = Organization.objects.first()
            if not org:
                self.stdout.write('ERROR: No organization found.')
                return
            self.stdout.write(f'Organization: {org.name}')

            admin = User.objects.filter(role='AGENCY_OWNER').first()
            if not admin:
                self.stdout.write('ERROR: No Agency Owner found.')
                return
            self.stdout.write(f'Admin: {admin.email}')

            # ── Properties ────────────────────────────────
            self.stdout.write('\n-- Properties --')

            prop1, _ = Property.objects.get_or_create(
                organization=org,
                name='Anju Apartments',
                defaults={
                    'code':    'ANJU',
                    'address': 'Kimathi Street, Nyeri',
                    'city':    'Nyeri',
                    'county':  'Nyeri',
                    'status':  'ACTIVE',
                }
            )
            self.stdout.write(f'  OK {prop1.name}')

            prop2, _ = Property.objects.get_or_create(
                organization=org,
                name='Rawa Heights',
                defaults={
                    'code':    'RAWH',
                    'address': 'Gakere Road, Nyeri',
                    'city':    'Nyeri',
                    'county':  'Nyeri',
                    'status':  'ACTIVE',
                }
            )
            self.stdout.write(f'  OK {prop2.name}')

            # ── House Types ───────────────────────────────
            self.stdout.write('\n-- House Types --')

            ht_data = [
                ('Bedsitter',  6000,  6000),
                ('1 Bedroom',  8000,  8000),
                ('2 Bedroom', 12000, 12000),
            ]

            house_types = {}
            for prop in [prop1, prop2]:
                house_types[prop.pk] = []
                for name, rent, deposit in ht_data:
                    ht, _ = HouseType.objects.get_or_create(
                        prop=prop,
                        name=name,
                        defaults={
                            'default_rent':    Decimal(rent),
                            'default_deposit': Decimal(deposit),
                        }
                    )
                    house_types[prop.pk].append(ht)
                    self.stdout.write(f'  OK {prop.name} - {ht.name}')

            # ── Units ─────────────────────────────────────
            self.stdout.write('\n-- Units --')

            def make_units(prop, prefix, ht_list):
                configs = [
                    (f'{prefix}101', 'Ground', 0, 6000,  6000),
                    (f'{prefix}102', 'Ground', 0, 6000,  6000),
                    (f'{prefix}103', 'Ground', 1, 8000,  8000),
                    (f'{prefix}104', 'Ground', 1, 8000,  8000),
                    (f'{prefix}201', '1st',    1, 8000,  8000),
                    (f'{prefix}202', '1st',    1, 8500,  8500),
                    (f'{prefix}203', '1st',    2, 12000, 12000),
                    (f'{prefix}204', '1st',    2, 12000, 12000),
                    (f'{prefix}301', '2nd',    2, 13000, 13000),
                    (f'{prefix}302', '2nd',    2, 13000, 13000),
                ]
                units = []
                for unit_number, floor, ht_idx, rent, deposit in configs:
                    unit, _ = Unit.objects.get_or_create(
                        prop=prop,
                        unit_number=unit_number,
                        defaults={
                            'house_type':     ht_list[ht_idx],
                            'floor':          floor,
                            'rent_amount':    Decimal(rent),
                            'deposit_amount': Decimal(deposit),
                            'status':         'VACANT',
                        }
                    )
                    units.append(unit)
                    self.stdout.write(f'  OK {prop.name} - {unit.unit_number}')
                return units

            units_p1 = make_units(prop1, 'A', house_types[prop1.pk])
            units_p2 = make_units(prop2, 'B', house_types[prop2.pk])

            # ── Tenants ───────────────────────────────────
            self.stdout.write('\n-- Tenants --')

            tenant_data = [
                {
                    'full_name':          'John Mwangi Kamau',
                    'phone':              '0712345601',
                    'email':              'john.mwangi@demo.rawarent.co.ke',
                    'national_id':        '12345601',
                    'emergency_contact':  'Mary Kamau',
                    'emergency_phone':    '0712345699',
                    'emergency_relation': 'Spouse',
                },
                {
                    'full_name':          'Grace Wanjiru Njoroge',
                    'phone':              '0712345602',
                    'email':              'grace.wanjiru@demo.rawarent.co.ke',
                    'national_id':        '12345602',
                    'emergency_contact':  'Peter Njoroge',
                    'emergency_phone':    '0712345698',
                    'emergency_relation': 'Brother',
                },
                {
                    'full_name':          'David Kimani Mugo',
                    'phone':              '0712345603',
                    'email':              'david.kimani@demo.rawarent.co.ke',
                    'national_id':        '12345603',
                    'emergency_contact':  'Alice Mugo',
                    'emergency_phone':    '0712345697',
                    'emergency_relation': 'Sister',
                },
                {
                    'full_name':          'Faith Akinyi Otieno',
                    'phone':              '0712345604',
                    'email':              'faith.akinyi@demo.rawarent.co.ke',
                    'national_id':        '12345604',
                    'emergency_contact':  'James Otieno',
                    'emergency_phone':    '0712345696',
                    'emergency_relation': 'Father',
                },
                {
                    'full_name':          'Samuel Kariuki Gitau',
                    'phone':              '0712345605',
                    'email':              'samuel.kariuki@demo.rawarent.co.ke',
                    'national_id':        '12345605',
                    'emergency_contact':  'Ruth Gitau',
                    'emergency_phone':    '0712345695',
                    'emergency_relation': 'Mother',
                },
                {
                    'full_name':          'Esther Wairimu Ngugi',
                    'phone':              '0712345606',
                    'email':              'esther.wairimu@demo.rawarent.co.ke',
                    'national_id':        '12345606',
                    'emergency_contact':  'Paul Ngugi',
                    'emergency_phone':    '0712345694',
                    'emergency_relation': 'Husband',
                },
                {
                    'full_name':          'Peter Njuguna Waweru',
                    'phone':              '0712345607',
                    'email':              'peter.njuguna@demo.rawarent.co.ke',
                    'national_id':        '12345607',
                    'emergency_contact':  'Ann Waweru',
                    'emergency_phone':    '0712345693',
                    'emergency_relation': 'Wife',
                },
                {
                    'full_name':          'Lucy Muthoni Kiragu',
                    'phone':              '0712345608',
                    'email':              'lucy.muthoni@demo.rawarent.co.ke',
                    'national_id':        '12345608',
                    'emergency_contact':  'Joseph Kiragu',
                    'emergency_phone':    '0712345692',
                    'emergency_relation': 'Father',
                },
            ]

            tenants = []
            for data in tenant_data:
                existing = Tenant.objects.filter(
                    organization=org,
                    phone=data['phone']
                ).first()

                if existing:
                    tenants.append(existing)
                    self.stdout.write(f'  SKIP {existing.full_name} (exists)')
                    continue

                tenant, user, portal_created = create_tenant_with_portal_account(
                    organization=org,
                    created_by=admin,
                    **data
                )
                tenants.append(tenant)
                portal = 'portal OK' if portal_created else 'no portal'
                self.stdout.write(
                    f'  OK {tenant.full_name} [{tenant.tenant_number}] {portal}'
                )

            # ── Tenancies ─────────────────────────────────
            self.stdout.write('\n-- Tenancies --')

            tenancy_configs = [
                (tenants[0], units_p1[0], date(2026, 1, 1),
                 Decimal('6000'),  Decimal('6000')),
                (tenants[1], units_p1[2], date(2026, 1, 1),
                 Decimal('8000'),  Decimal('8000')),
                (tenants[2], units_p1[4], date(2026, 2, 1),
                 Decimal('8000'),  Decimal('8000')),
                (tenants[3], units_p1[6], date(2026, 2, 1),
                 Decimal('12000'), Decimal('12000')),
                (tenants[4], units_p1[8], date(2026, 3, 1),
                 Decimal('13000'), Decimal('13000')),
                (tenants[5], units_p2[1], date(2026, 1, 1),
                 Decimal('6000'),  Decimal('6000')),
                (tenants[6], units_p2[3], date(2026, 2, 1),
                 Decimal('8000'),  Decimal('8000')),
                (tenants[7], units_p2[5], date(2026, 3, 1),
                 Decimal('8500'),  Decimal('8500')),
            ]

            tenancy_objects = []
            for tenant, unit, start, rent, deposit in tenancy_configs:
                existing = Tenancy.objects.filter(
                    tenant=tenant, unit=unit, status='ACTIVE'
                ).first()

                if existing:
                    tenancy_objects.append(existing)
                    self.stdout.write(
                        f'  SKIP {tenant.full_name} -> {unit.unit_number} (exists)'
                    )
                    continue

                tenancy = Tenancy.objects.create(
                    organization=org,
                    tenant=tenant,
                    unit=unit,
                    start_date=start,
                    monthly_rent=rent,
                    required_deposit=deposit,
                    billing_day=1,
                    status='ACTIVE',
                    created_by=admin,
                )
                unit.status = 'OCCUPIED'
                unit.save(update_fields=['status'])
                tenancy_objects.append(tenancy)
                self.stdout.write(
                    f'  OK {tenant.full_name} -> {unit.unit_number} KSh {rent}/mo'
                )

            # ── Deposit Accounts ──────────────────────────
            self.stdout.write('\n-- Deposit Accounts --')

            for tenancy in tenancy_objects:
                dep_acc, created = DepositAccount.objects.get_or_create(
                    tenancy=tenancy,
                    defaults={
                        'organization':   org,
                        'required_amount': tenancy.required_deposit,
                    }
                )
                if created:
                    DepositMovement.objects.create(
                        deposit_account=dep_acc,
                        movement_type='RECEIVED',
                        amount=tenancy.required_deposit,
                        reason='Initial deposit received on move-in',
                        created_by=admin,
                    )
                    self.stdout.write(
                        f'  OK {tenancy.tenant.full_name} '
                        f'deposit KSh {tenancy.required_deposit}'
                    )
                else:
                    self.stdout.write(
                        f'  SKIP {tenancy.tenant.full_name} deposit (exists)'
                    )

            # ── Rent Charges ──────────────────────────────
            self.stdout.write('\n-- Rent Charges --')

            charge_months = [
                (date(2026, 6, 1), date(2026, 6, 30)),
                (date(2026, 7, 1), date(2026, 7, 31)),
                (date(2026, 8, 1), date(2026, 8, 31)),
            ]

            all_charges = {}
            for tenancy in tenancy_objects:
                all_charges[tenancy.pk] = []
                for period_start, period_end in charge_months:
                    if tenancy.start_date > period_start:
                        continue
                    charge, created = Charge.objects.get_or_create(
                        tenancy=tenancy,
                        charge_type='RENT',
                        period_start=period_start,
                        defaults={
                            'organization': org,
                            'description':  (
                                f'{period_start.strftime("%B %Y")} Rent - '
                                f'{tenancy.unit.unit_number}'
                            ),
                            'period_end':  period_end,
                            'amount':      tenancy.monthly_rent,
                            'due_date':    period_start,
                            'created_by':  admin,
                        }
                    )
                    all_charges[tenancy.pk].append(charge)
                    if created:
                        self.stdout.write(
                            f'  OK {tenancy.tenant.full_name} '
                            f'{period_start.strftime("%b %Y")} '
                            f'KSh {tenancy.monthly_rent}'
                        )

            # ── Payments ──────────────────────────────────
            self.stdout.write('\n-- Payments --')

            def make_payment(tenancy, amount, pay_date, method, charges_list):
                existing = Payment.objects.filter(
                    tenancy=tenancy,
                    amount=amount,
                    payment_date=pay_date,
                    method=method,
                ).first()
                if existing:
                    self.stdout.write(
                        f'  SKIP {tenancy.tenant.full_name} {pay_date} (exists)'
                    )
                    return existing

                payment = Payment.objects.create(
                    organization=org,
                    tenant=tenancy.tenant,
                    tenancy=tenancy,
                    amount=amount,
                    payment_date=pay_date,
                    method=method,
                    status='VERIFIED',
                    verified_by=admin,
                    verified_at=timezone.now(),
                    created_by=admin,
                )

                remaining = amount
                for charge in charges_list:
                    if remaining <= 0:
                        break
                    allocate = min(remaining, charge.balance)
                    if allocate > 0:
                        PaymentAllocation.objects.create(
                            payment=payment,
                            charge=charge,
                            amount=allocate,
                        )
                        remaining -= allocate

                Receipt.objects.get_or_create(
                    payment=payment,
                    defaults={
                        'organization':   org,
                        'receipt_number': receipt_number(tenancy.unit.prop.code),
                        'issued_by':      admin,
                    }
                )

                self.stdout.write(
                    f'  OK {tenancy.tenant.full_name} '
                    f'KSh {amount} on {pay_date} [{method}]'
                )
                return payment

            # Tenant 0 - fully paid all 3 months
            t = tenancy_objects[0]
            c = all_charges[t.pk]
            if len(c) >= 3:
                make_payment(t, c[0].amount, date(2026, 6, 3), 'MPESA', [c[0]])
                make_payment(t, c[1].amount, date(2026, 7, 2), 'MPESA', [c[1]])
                make_payment(t, c[2].amount, date(2026, 8, 4), 'MPESA', [c[2]])

            # Tenant 1 - fully paid all 3 months
            t = tenancy_objects[1]
            c = all_charges[t.pk]
            if len(c) >= 3:
                make_payment(t, c[0].amount, date(2026, 6, 2), 'BANK', [c[0]])
                make_payment(t, c[1].amount, date(2026, 7, 1), 'BANK', [c[1]])
                make_payment(t, c[2].amount, date(2026, 8, 2), 'BANK', [c[2]])

            # Tenant 2 - paid June + July, August outstanding
            t = tenancy_objects[2]
            c = all_charges[t.pk]
            if len(c) >= 2:
                make_payment(t, c[0].amount, date(2026, 6, 5), 'MPESA', [c[0]])
                make_payment(t, c[1].amount, date(2026, 7, 3), 'CASH',  [c[1]])

            # Tenant 3 - paid June + July, August outstanding
            t = tenancy_objects[3]
            c = all_charges[t.pk]
            if len(c) >= 2:
                make_payment(t, c[0].amount, date(2026, 6, 4), 'MPESA', [c[0]])
                make_payment(t, c[1].amount, date(2026, 7, 5), 'MPESA', [c[1]])

            # Tenant 4 - paid June only
            t = tenancy_objects[4]
            c = all_charges[t.pk]
            if len(c) >= 1:
                make_payment(t, c[0].amount, date(2026, 6, 6), 'MPESA', [c[0]])

            # Tenant 5 - partial payment on June only
            t = tenancy_objects[5]
            c = all_charges[t.pk]
            if len(c) >= 1:
                partial = c[0].amount / 2
                make_payment(t, partial, date(2026, 6, 8), 'MPESA', [c[0]])

            # Tenant 6 - no payments
            self.stdout.write(
                f'  NOTE {tenancy_objects[6].tenant.full_name} - no payments (arrears)'
            )

            # Tenant 7 - no payments
            self.stdout.write(
                f'  NOTE {tenancy_objects[7].tenant.full_name} - no payments (arrears)'
            )

            # ── Summary ───────────────────────────────────
            self.stdout.write('\n=== Seed Complete ===')
            self.stdout.write(
                f'  Properties : {Property.objects.filter(organization=org).count()}'
            )
            self.stdout.write(
                f'  Units      : {Unit.objects.filter(prop__organization=org).count()}'
            )
            self.stdout.write(
                f'  Tenants    : {Tenant.objects.filter(organization=org).count()}'
            )
            self.stdout.write(
                f'  Tenancies  : {Tenancy.objects.filter(organization=org).count()}'
            )
            self.stdout.write(
                f'  Charges    : {Charge.objects.filter(organization=org).count()}'
            )
            self.stdout.write(
                f'  Payments   : {Payment.objects.filter(organization=org).count()}'
            )
            self.stdout.write(
                f'  Receipts   : {Receipt.objects.filter(organization=org).count()}'
            )
            self.stdout.write(
                f'  Portal users: {User.objects.filter(role="TENANT").count()}'
            )
            self.stdout.write('\nTest tenant login:')
            self.stdout.write('  Email    : john.mwangi@demo.rawarent.co.ke')
            self.stdout.write(
                '  Password : 0712345601 (phone - must change on first login)')
            self.stdout.write('===================\n')
