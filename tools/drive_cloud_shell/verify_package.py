"""Verificador stdlib, sem rede, sem credenciais e sem import da aplicação."""
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
RUNTIME={'.venv','.local','evidence','exports'}


def verify(root=ROOT,*,expected_format='secco-drive-cloud-shell-07c-v3'):
    if sys.version_info<(3,11): raise ValueError('python_3_11_necessario')
    root=Path(root)
    raw=(root/'MANIFEST.json').read_bytes()
    manifest=json.loads(raw)
    expected=manifest['files']
    actual=set()
    for folder,dirs,files in os.walk(root,followlinks=False):
        relative=Path(folder).relative_to(root)
        if relative==Path('.'):
            dirs[:]=[d for d in dirs if d not in RUNTIME]
        for name in dirs:
            if (Path(folder)/name).is_symlink(): raise ValueError('link_nao_permitido')
        for name in files:
            path=Path(folder)/name
            if path.is_symlink() or path.stat().st_nlink!=1: raise ValueError('link_nao_permitido')
            key=path.relative_to(root).as_posix()
            if key!='MANIFEST.json': actual.add(key)
    if actual!=set(expected): raise ValueError('inventario_divergente')
    for name,record in expected.items():
        content=(root/name).read_bytes()
        if len(content)!=record['bytes'] or hashlib.sha256(content).hexdigest()!=record['sha256']:
            raise ValueError('integridade_do_pacote')
    if manifest['format']!=expected_format: raise ValueError('formato_do_pacote')
    return hashlib.sha256(raw).hexdigest()


if __name__=='__main__':
    try:
        digest=verify()
        print(json.dumps({'package':'verified','manifest_sha256':digest}))
    except (OSError,ValueError,KeyError):
        print(json.dumps({'package':'rejected'}))
        raise SystemExit(2)
