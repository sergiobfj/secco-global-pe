"""Build allowlisted e determinístico do executor 07C. Nenhuma rede/credencial."""
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'artifacts/stage07c/cloud-shell-v3'
NAME='secco-drive-07c-cloud-shell-v3.zip'
SA='global-pe-drive@exemplo-global-pe.iam.gserviceaccount.com'
SOURCES=(
    'app/core/drive_config.py','app/core/test_database.py','app/core/storage_paths.py',
    'app/db/connection.py','app/services/storage_contracts.py','app/services/drive_credentials.py',
    'app/services/google_drive_storage.py','app/services/drive_supervised.py','app/services/drive_probe.py',
)
REQUIREMENTS='''httpx==0.28.1
httpcore==1.0.9
anyio==4.15.1
certifi==2026.7.22
idna==3.18
h11==0.16.0
typing_extensions==4.16.0
'''


def dump(value):
    return (json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode()


def payload():
    files={}
    policy=None
    for name in SOURCES:
        text=(ROOT/name).read_text(encoding='utf-8')
        if name=='app/core/drive_config.py':
            tree=ast.parse(text)
            for node in tree.body:
                if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='READERS' for t in node.targets):
                    # Atribuição original usa SERVICE_ACCOUNT como nome, não literal: avalia só
                    # a árvore de dados conhecida, sem executar/importar configuração operacional.
                    policy={}
                    for key,call in zip(node.value.keys,node.value.values):
                        members=[]
                        for element in call.args[0].elts:
                            members.append(SA if isinstance(element,ast.Name) and element.id=='SERVICE_ACCOUNT'
                                           else ast.literal_eval(element))
                        policy[ast.literal_eval(key)]=sorted(members)
                    node.value=ast.Dict(keys=[],values=[])
            text=ast.unparse(tree)+'\n'
        if name=='app/services/google_drive_storage.py':
            original=('from app.services.receipt_storage import MAX_FILE, validate_file\n'
                      'from app.services.itinerary import InvalidActivity')
            replacement='from app.services.probe_synthetic import MAX_FILE, validate_file, InvalidActivity'
            if text.count(original)!=1: raise ValueError('contrato_imports_alterado_revisar_build')
            text=text.replace(original,replacement,1)
        files[name]=text.replace('\r\n','\n').encode()
    if policy is None: raise ValueError('politica_ausente')
    for name in ('app/__init__.py','app/core/__init__.py','app/db/__init__.py','app/services/__init__.py'):
        files[name]=b''
    for source,target in (('probe.py','probe.py'),('verify_package.py','verify_package.py'),
                          ('probe_synthetic.py','app/services/probe_synthetic.py'),('README.txt','README.txt')):
        files[target]=(ROOT/'tools/drive_cloud_shell'/source).read_text(encoding='utf-8').replace('\r\n','\n').encode()
    files['requirements.txt']=REQUIREMENTS.encode()
    original=json.loads((ROOT/'artifacts/stage07c/offline-plan.json').read_text(encoding='utf-8-sig'))
    plan={key:original[key] for key in ('mapping_sha256','plan_sha256','items')}
    files['plan.json']=dump(plan)
    files['folders.json']=(ROOT/'artifacts/stage07b/mapping/folders.json').read_bytes()
    with zipfile.ZipFile(ROOT/'artifacts/stage07c/probe-prepared.zip') as source:
        for mission,item in plan['items'].items():
            content=source.read(mission+'.png')
            if len(content)!=69 or hashlib.sha256(content).hexdigest()!=item['checksum']:
                raise ValueError('integridade_do_png')
            files['payload/'+mission+'.png']=content
    commitment=hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    files['policy-contract.json']=dump({'policy_sha256':commitment,'human_members_per_mission':2,
        'purpose':'compromisso agregado; membros pessoais fornecidos apenas no ambiente de execucao'})
    files['approval.template.json']=dump({'reference':'NOVA-APROVACAO-CLOUD-SHELL-NECESSARIA',
        'operator_account':'','expires_at':'','approved':False,'synthetic_only':True,'backup_verified':False,
        'mapping_sha256':plan['mapping_sha256'],'plan_sha256':plan['plan_sha256'],
        'scopes':['https://www.googleapis.com/auth/drive.file','https://www.googleapis.com/auth/drive.metadata.readonly'],
        'cleanup':'retain','environment':'google-cloud-shell','package_manifest_sha256':'',
        'policy_sha256':commitment})
    for name,content in files.items():
        if (name.startswith(('/','../')) or '\\' in name or '..' in Path(name).parts
                or Path(name).suffix in ('.sqlite3','.db','.pem','.key') or '.env' in Path(name).parts):
            raise ValueError('arquivo_nao_permitido')
        if name.endswith(('.py','.json','.txt')):
            emails=set(re.findall(rb'[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+',content))
            if emails-{SA.encode()}: raise ValueError('identificador_pessoal_no_pacote')
            if b'BEGIN PRIVATE KEY' in content or b'C:\\Users\\' in content:
                raise ValueError('dado_sensivel_no_pacote')
    manifest={'format':'secco-drive-cloud-shell-07c-v3','minimum_python':'3.11',
        'files':{name:{'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
                 for name,content in sorted(files.items())}}
    files['MANIFEST.json']=dump(manifest)
    return files


def build(output=OUTPUT):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    files=payload()
    target=output/NAME
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,content in sorted(files.items()):
            entry=zipfile.ZipInfo(name,date_time=(2020,1,1,0,0,0))
            entry.create_system=3
            entry.external_attr=0o100644<<16
            entry.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(entry,content)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(f'{digest}  {NAME}\n',encoding='ascii')
    (output/'package-inventory.json').write_bytes(dump({'archive':NAME,'sha256':digest,'bytes':target.stat().st_size,
        'file_count':len(files),'files':sorted(files),'approval':'renewal_required','personal_email_addresses':0,
        'operational_data':False,'runtime_dependency':'httpx and pinned transitive dependencies'}))
    return target,digest


if __name__=='__main__':
    path,digest=build()
    print(json.dumps({'zip':str(path),'sha256':digest,'bytes':path.stat().st_size}))
