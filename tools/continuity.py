"""Respaldo y restauración en destinos nuevos. Ejecutar sin escritores concurrentes."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import sqlite3
import subprocess


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def files(root):
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('No se admiten enlaces simbólicos.')
        if path.is_file():
            yield path


def postgres(command):
    # Credenciales por variables PG* o .pgpass; nunca imprimir errores con secretos.
    result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode:
        raise ValueError('Falló una herramienta PostgreSQL. Revisar conexión y permisos en el servidor.')


def verify(root):
    root = Path(root)
    if root.is_symlink():
        raise ValueError('El respaldo no puede ser un enlace.')
    inventory = {p.relative_to(root).as_posix(): p for p in files(root)}
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest.get('version') != 1 or manifest.get('engine') not in {'sqlite', 'postgresql'}:
        raise ValueError('Formato de respaldo no soportado.')
    declared = manifest['files']
    if set(inventory) - {'manifest.json'} != set(declared):
        raise ValueError('Inventario del respaldo incompleto o alterado.')
    for name, expected in declared.items():
        if digest(inventory[name]) != expected:
            raise ValueError('Falló la verificación SHA256 del respaldo.')
    database_file = 'database.sqlite3' if manifest['engine'] == 'sqlite' else 'database.dump'
    if database_file not in declared or any(name != database_file and not name.startswith('media/') for name in declared):
        raise ValueError('Contenido de respaldo no permitido.')
    if manifest['engine'] == 'sqlite':
        with sqlite3.connect((root / database_file).resolve().as_uri() + '?mode=ro', uri=True) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('SQLite no superó integrity_check.')
    return manifest


def database_name(value):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,62}', value):
        raise ValueError('Usar un nombre simple de base; credenciales exclusivamente por PG* o .pgpass.')
    return value


def backup(engine, database, media, destination):
    media, destination = Path(media).resolve(), Path(destination).absolute()
    if not media.is_dir() or media == destination or media in destination.parents:
        raise ValueError('Media debe existir y el respaldo quedar fuera de ella.')
    source_files = list(files(media))  # Rechazar enlaces antes de copiar.
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        if engine == 'sqlite':
            source = Path(database).resolve()
            if not source.is_file():
                raise ValueError('No existe la base SQLite de origen.')
            with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
                with sqlite3.connect(destination / 'database.sqlite3') as dst:
                    src.backup(dst)
        elif engine == 'postgresql':
            database_name(database)
            postgres(['pg_dump', '--format=custom', '--no-owner', '--no-acl', '--file', str(destination / 'database.dump'), '--dbname', database])
        else:
            raise ValueError('Motor no soportado.')
        (destination / 'media').mkdir(mode=0o700)
        for path in source_files:
            target = destination / 'media' / path.relative_to(media)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target, follow_symlinks=False)
        inventory = {}
        for path in files(destination):
            path.chmod(0o600)
            inventory[path.relative_to(destination).as_posix()] = digest(path)
        manifest = {'version': 1, 'engine': engine, 'files': inventory}
        (destination / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2))
        (destination / 'manifest.json').chmod(0o600)
        verify(destination)
    except Exception:
        # Directorio creado por esta ejecución; jamás borrar el origen.
        shutil.rmtree(destination)
        raise


def restore(source, destination, database=None):
    source, destination = Path(source).absolute(), Path(destination).absolute()
    manifest = verify(source)
    if source == destination or source in destination.parents:
        raise ValueError('La restauración debe quedar fuera del respaldo.')
    if manifest['engine'] == 'postgresql' and not database:
        raise ValueError('Se requiere el nombre de una base PostgreSQL NUEVA.')
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    # Si la restauración falla, conservar el destino parcial para diagnosticarlo.
    if manifest['engine'] == 'postgresql':
        database_name(database)
        postgres(['createdb', '--', database])  # Falla si existe; no se usa --clean.
        postgres(['pg_restore', '--exit-on-error', '--single-transaction', '--no-owner', '--no-acl', '--dbname', database, str(source / 'database.dump')])
    else:
        shutil.copyfile(source / 'database.sqlite3', destination / 'database.sqlite3')
        (destination / 'database.sqlite3').chmod(0o600)
    shutil.copytree(source / 'media', destination / 'media')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('backup')
    create.add_argument('--engine', choices=['sqlite', 'postgresql'], required=True)
    create.add_argument('--database', required=True)
    create.add_argument('--media', required=True)
    create.add_argument('--destination', required=True)
    check = commands.add_parser('verify')
    check.add_argument('source')
    recover = commands.add_parser('restore')
    recover.add_argument('source')
    recover.add_argument('--destination', required=True)
    recover.add_argument('--database', help='Nombre de una base PostgreSQL nueva; nunca la base activa.')
    args = vars(parser.parse_args())
    command = args.pop('command')
    try:
        {'backup': backup, 'verify': lambda source: verify(source), 'restore': restore}[command](**args)
    except Exception:
        parser.exit(1, 'Operación fallida. Revisar rutas, permisos, integridad y herramientas del motor; no se sustituyen destinos existentes.\n')
    print(json.dumps({'operation': command, 'status': 'ok'}))


if __name__ == '__main__':
    main()
