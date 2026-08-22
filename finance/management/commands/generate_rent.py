"""
Generate monthly rent charges for all active tenancies in an organization.

Usage:
    python manage.py generate_rent 2026 9
    python manage.py generate_rent            # current month, all orgs
"""
from datetime import date
from django.core.management.base import BaseCommand
from organizations.models import Organization
from finance.services import rent_service


class Command(BaseCommand):
    help = 'Generate rent charges for active tenancies (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('year', nargs='?', type=int, default=None)
        parser.add_argument('month', nargs='?', type=int, default=None)
        parser.add_argument('--org', dest='org', default=None,
                            help='Organization slug (default: all orgs)')

    def handle(self, *args, **options):
        today = date.today()
        year = options['year'] or today.year
        month = options['month'] or today.month

        orgs = Organization.objects.all()
        if options['org']:
            orgs = orgs.filter(slug=options['org'])

        total = 0
        for org in orgs:
            created = rent_service.generate_rent_charges(org, year, month)
            total += created
            self.stdout.write(
                f'{org.name}: {created} rent charge(s) for {year}-{month:02d}')

        self.stdout.write(self.style.SUCCESS(
            f'Done — {total} charge(s) created for {year}-{month:02d}.'))
