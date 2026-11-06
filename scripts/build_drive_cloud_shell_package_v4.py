"""Build v4 do executor 07C: deriva do build v3 e troca somente executor e política de ACL.

Nenhuma rede/credencial. As fontes v3 (tools/drive_cloud_shell) e o builder v3 ficam intactos,
e todo arquivo compartilhado precisa ser byte a byte igual ao ZIP v3 preservado.
"""
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.build_drive_cloud_shell_package import SA,dump,payload as v3_payload

OUTPUT=ROOT/'artifacts/stage07c/cloud-shell-v4'
NAME='secco-drive-07c-cloud-shell-v4.zip'
FORMAT='secco-drive-cloud-shell-07c-v4'
SOURCE=ROOT/'tools/drive_cloud_shell_v4'
V3_ARCHIVE=ROOT/'artifacts/stage07c/cloud-shell-v3/secco-drive-07c-cloud-shell-v3.zip'
V3_ZIP_SHA256='7655fb0d35ff91277c6b4112dcbb1b041631e14f5ec68a0242e729504616385c'
LEGACY_POLICY_SHA256='0532899c44715ac60733136237ebfa93d2bbdf5f073986238b90eb9ee92c16ee'
HUMAN_MEMBERS=5
# Únicos arquivos que a v4 pode alterar em relação ao ZIP v3.
CHANGED={'probe.py','verify_package.py','README.txt','policy-contract.json','approval.template.json','MANIFEST.json'}


def partner_accounts():
    """Cinco sócios confirmados (allowlist do Workspace), lidos por AST sem importar a aplicação."""
    tree=ast.parse((ROOT/'app/core/workspace_access.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SECCO_ACCOUNTS' for t in node.targets):
            emails=[ast.literal_eval(value)[0].casefold() for value in node.value.values]
            break
    else: raise ValueError('allowlist_ausente')
    if (len(emails)!=HUMAN_MEMBERS or len(set(emails))!=HUMAN_MEMBERS or SA in emails
            or any(not re.fullmatch(r'[a-z0-9._+-]+@secco\.example',e) for e in emails)):
        raise ValueError('allowlist_inesperada_revisar_politica')
    return sorted(emails)


def policy():
    members=sorted(partner_accounts()+[SA])
    return {'argentina':members,'portugal':list(members)}


def commitment(data):
    canonical={m:sorted(v) for m,v in data.items()}
    return hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def scan(files):
    for name,content in files.items():
        if (name.startswith(('/','../')) or '\\' in name or '..' in Path(name).parts
                or Path(name).suffix in ('.sqlite3','.db','.pem','.key') or '.env' in Path(name).parts):
            raise ValueError('arquivo_nao_permitido')
        if name.endswith(('.py','.json','.txt')):
            emails=set(re.findall(rb'[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+',content))
            if emails-{SA.encode()}: raise ValueError('identificador_pessoal_no_pacote')
            if b'BEGIN PRIVATE KEY' in content or b'C:\\Users\\' in content:
                raise ValueError('dado_sensivel_no_pacote')


def payload():
    if hashlib.sha256(V3_ARCHIVE.read_bytes()).hexdigest()!=V3_ZIP_SHA256: raise ValueError('zip_v3_alterado')
    files=v3_payload()
    with zipfile.ZipFile(V3_ARCHIVE) as v3:
        # Adaptador, journal, plano, mapa e PNGs precisam ser exatamente os mesmos do v3.
        if set(v3.namelist())!=set(files) or any(v3.read(n)!=c for n,c in files.items()):
            raise ValueError('fontes_compartilhadas_divergem_do_v3')
    legacy=json.loads(files['policy-contract.json'])
    if legacy['policy_sha256']!=LEGACY_POLICY_SHA256: raise ValueError('politica_anterior_divergente')
    del files['MANIFEST.json']
    for name in ('probe.py','verify_package.py','README.txt'):
        files[name]=(SOURCE/name).read_text(encoding='utf-8').replace('\r\n','\n').encode()
    current=commitment(policy())
    if current==LEGACY_POLICY_SHA256: raise ValueError('politica_nao_mudou')
    files['policy-contract.json']=dump({'policy_sha256':current,'human_members_per_mission':HUMAN_MEMBERS,
        'members_per_mission_including_service_account':HUMAN_MEMBERS+1,'same_members_all_missions':True,
        'previous_policy_sha256':LEGACY_POLICY_SHA256,
        'previous_policy_status':'substituida; preservada somente como historico de aceites v2/v3',
        'purpose':'compromisso agregado; membros pessoais fornecidos apenas no ambiente de execucao'})
    template=json.loads(files['approval.template.json'])
    template.update({'reference':'NOVO-ACEITE-V4-NECESSARIO','policy_sha256':current})
    files['approval.template.json']=dump(template)
    scan(files)
    manifest={'format':FORMAT,'minimum_python':'3.11',
        'files':{name:{'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
                 for name,content in sorted(files.items())}}
    files['MANIFEST.json']=dump(manifest)
    return files


def build(output=OUTPUT):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    files=payload()
    target=output/NAME
    if target.exists(): raise FileExistsError('zip_v4_existente_nao_sobrescrever')
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,content in sorted(files.items()):
            entry=zipfile.ZipInfo(name,date_time=(2020,1,1,0,0,0))
            entry.create_system=3
            entry.external_attr=0o100644<<16
            entry.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(entry,content)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(f'{digest}  {NAME}\n',encoding='ascii')
    contract=json.loads(files['policy-contract.json'])
    (output/'package-inventory.json').write_bytes(dump({'archive':NAME,'sha256':digest,'bytes':target.stat().st_size,
        'file_count':len(files),'files':sorted(files),'manifest_sha256':hashlib.sha256(files['MANIFEST.json']).hexdigest(),
        'derived_from_v3_zip_sha256':V3_ZIP_SHA256,'changed_from_v3':sorted(CHANGED),
        'policy_sha256':contract['policy_sha256'],'previous_policy_sha256':LEGACY_POLICY_SHA256,
        'members_per_mission':HUMAN_MEMBERS+1,'approval':'new_explicit_v4_approval_required',
        'personal_email_addresses':0,'operational_data':False,
        'runtime_dependency':'httpx and pinned transitive dependencies'}))
    return target,digest


if __name__=='__main__':
    path,digest=build()
    print(json.dumps({'zip':str(path),'sha256':digest,'bytes':path.stat().st_size}))
