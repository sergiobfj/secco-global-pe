"""Limites do diretório privado, antes de criar ou abrir qualquer objeto."""
import os
from pathlib import Path
import stat
from app.core.test_database import enforce_database_policy, testing_enabled, assert_temporary_database

PROJECT=Path(__file__).resolve().parents[2]


def reject_links(candidate):
    candidate=Path(candidate)
    for component in [candidate,*candidate.parents]:
        if component.is_symlink() or (component.exists() and getattr(component,'is_junction',lambda:False)()):
            raise OSError('Links não são permitidos no armazenamento privado.')
        if component.exists() and getattr(component.stat(),'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024):
            raise OSError('Ponto de redirecionamento não permitido.')


def validate_private_directory(directory,database_path):
    enforce_database_policy(database_path)
    folder=Path(directory)
    if not folder.is_absolute() or folder==Path(folder.anchor) or '..' in folder.parts:
        raise RuntimeError('Configure um diretório privado absoluto e específico.')
    reject_links(folder)
    resolved=folder.resolve()
    if resolved.is_relative_to(PROJECT.resolve()) or PROJECT.resolve().is_relative_to(resolved):
        raise RuntimeError('O diretório privado deve ficar fora do projeto e dos assets.')
    if Path(database_path).resolve().is_relative_to(resolved):
        raise RuntimeError('O banco deve ficar fora do volume de comprovantes.')
    if testing_enabled(): assert_temporary_database(resolved/'__storage_lease_check__.sqlite3')
    if resolved.exists() and not resolved.is_dir(): raise RuntimeError('O armazenamento exige um diretório privado.')
    if os.name!='nt' and resolved.exists():
        info=resolved.stat()
        if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)&0o077:
            raise RuntimeError('O diretório privado deve pertencer ao processo e ter permissão 0700.')
    return resolved
