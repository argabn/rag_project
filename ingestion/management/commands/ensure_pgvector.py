from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Create the pgvector extension if it does not already exist."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        self.stdout.write(self.style.SUCCESS("pgvector extension is ready"))
