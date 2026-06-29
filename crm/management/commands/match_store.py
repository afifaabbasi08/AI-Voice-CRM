from django.core.management.base import BaseCommand

from crm.services.store_matching import find_store, match_store


class Command(BaseCommand):
    help = 'Test triple-key store matching (name + owner + area).'

    def add_arguments(self, parser):
        parser.add_argument('--name', required=True, help='Store name')
        parser.add_argument('--owner', default='', help='Owner name')
        parser.add_argument('--area', default='', help='Area / location')

    def handle(self, *args, **options):
        name = options['name']
        owner = options['owner']
        area = options['area']

        self.stdout.write(f'\nMatching: {name!r} | owner={owner!r} | area={area!r}\n')

        result = match_store(name, owner, area)
        if result.store:
            self.stdout.write(self.style.SUCCESS(f'MATCH: {result.store}'))
            return

        self.stdout.write(self.style.WARNING(f'NEEDS REVIEW: {result.reason}'))
        if result.candidates:
            self.stdout.write('\nCandidates:')
            for store in result.candidates:
                self.stdout.write(f'  - {store}')
        else:
            self.stdout.write('No candidates found — this would create a new store.')

        exact = find_store(name, owner, area)
        if exact:
            self.stdout.write(self.style.SUCCESS(f'\nExact lookup: {exact}'))
