import json
import uuid

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = 'Comprueba BD y caché; salida JSON y código no cero para monitoreo externo.'
    requires_system_checks = []

    def handle(self, *args, **options):
        status = {'database': False, 'cache': False}
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                status['database'] = cursor.fetchone()[0] == 1
        except Exception:
            pass
        key = 'axentra:health:' + uuid.uuid4().hex
        try:
            cache.set(key, 'ok', timeout=30)
            status['cache'] = cache.get(key) == 'ok'
        except Exception:
            pass
        finally:
            try:
                cache.delete(key)
            except Exception:
                status['cache'] = False
        self.stdout.write(json.dumps(status, sort_keys=True))
        if not all(status.values()):
            raise CommandError('Fallo de salud operativa. Revisar el servicio desde el servidor.')
