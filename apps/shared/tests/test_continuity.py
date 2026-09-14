import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from tools.continuity import backup, restore, verify


class ContinuityTests(SimpleTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.database = self.root / 'source.sqlite3'
        with sqlite3.connect(self.database) as db:
            db.execute('CREATE TABLE expediente (id INTEGER, folio TEXT)')
            db.execute("INSERT INTO expediente VALUES (1, 'PRUEBA-001')")
        self.media = self.root / 'media'
        self.media.mkdir()
        (self.media / 'evidencia.txt').write_text('Documento de prueba')
        self.copy = self.root / 'backup'

    def create(self):
        backup('sqlite', str(self.database), self.media, self.copy)

    def test_backup_verify_restore_database_and_media_in_new_target(self):
        self.create()
        self.assertEqual(verify(self.copy)['engine'], 'sqlite')
        restored = self.root / 'restored'
        restore(self.copy, restored)
        with sqlite3.connect(restored / 'database.sqlite3') as db:
            self.assertEqual(db.execute('SELECT folio FROM expediente').fetchone()[0], 'PRUEBA-001')
        self.assertEqual((restored / 'media/evidencia.txt').read_text(), 'Documento de prueba')

    def test_corrupt_media_prevents_restoration(self):
        self.create()
        (self.copy / 'media/evidencia.txt').write_text('Alterado')
        with self.assertRaises(ValueError):
            restore(self.copy, self.root / 'restored')
        self.assertFalse((self.root / 'restored').exists())

    def test_existing_destination_never_overwritten(self):
        self.create()
        with self.assertRaises(FileExistsError):
            self.create()
        with self.assertRaises(FileExistsError):
            restore(self.copy, self.media)
        self.assertEqual((self.media / 'evidencia.txt').read_text(), 'Documento de prueba')

    def test_symlink_in_media_rejected(self):
        (self.media / 'link').symlink_to(self.database)
        with self.assertRaises(ValueError):
            self.create()
        self.assertFalse(self.copy.exists())

    def test_extra_file_invalidates_inventory(self):
        self.create()
        (self.copy / 'unexpected').write_text('extra')
        with self.assertRaises(ValueError):
            verify(self.copy)
