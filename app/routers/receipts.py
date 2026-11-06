"""Captura sintética autenticada, com autorização e anexos privados por autor."""
import secrets
import sqlite3
from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from app.core.auth import actor_id, authorize_mission_route, can_edit
from app.core.receipt_upload import read_receipt_form
from app.core.forms import read_form
from app.repositories.itinerary import ActivityConflict
from app.routers.web import find_mission, render
from app.services.itinerary import InvalidActivity, mission_today
from app.services.receipts import CURRENCIES, STATUSES, load_rules, validate_expense
from app.services.receipt_storage import validate_file

router=APIRouter(dependencies=[Depends(authorize_mission_route)])


def require_capture(request: Request,codigo: str):
    if not getattr(request.state,'user',None): raise HTTPException(403,'Esta função exige uma sessão autenticada. O acesso local sem login não permite capturar comprovantes.')
    mission=find_mission(request,codigo)
    if not can_edit(request,mission.id): raise HTTPException(403,'Você não possui permissão para registrar comprovantes nesta missão.')
    if not request.app.state.settings.receipts_synthetic_enabled or not hasattr(request.app.state,'receipts'):
        raise HTTPException(503,'Captura sintética desativada. A ativação exige configuração local explícita. Não utilize comprovantes reais.')
    return mission


def current_entry(request,mission,entry_id):
    entry=request.app.state.receipts.get(mission.id,entry_id,actor_id(request))
    if not entry: raise HTTPException(404,'Comprovante não encontrado.')
    return entry


def form_page(request,mission,values,entry=None,errors=None,status_code=200):
    rules=load_rules()
    participant=next((p for p in mission.participantes if p.id==request.state.user['participant_id']),None)
    if not participant: raise HTTPException(403,'O participante autenticado não pertence a esta missão.')
    response=render(request,'receipt_form.html',title='Registrar comprovante' if not entry else 'Editar registro',active='prestacao-de-contas',mission=mission,
        values=values,entry=entry,errors=errors or {},rules=rules,currencies=CURRENCIES,participant=participant,
        persistent_storage=request.app.state.receipt_storage.persistent)
    response.status_code=status_code
    return response


@router.get('/missoes/{codigo}/comprovantes',name='receipts')
def receipts(request: Request,codigo: str):
    mission=require_capture(request,codigo)
    return render(request,'receipts.html',title='Meus comprovantes sintéticos',active='prestacao-de-contas',mission=mission,
        entries=request.app.state.receipts.list(mission.id,actor_id(request)),statuses=STATUSES,
        persistent_storage=request.app.state.receipt_storage.persistent)


@router.get('/missoes/{codigo}/comprovantes/novo',name='new_receipt')
def new_receipt(request: Request,codigo: str):
    if getattr(request.state,'user',None) and not request.app.state.settings.receipts_synthetic_enabled:
        mission=find_mission(request,codigo)
        response=render(request,'receipt_unavailable.html',title='Captura sintética desativada',active='prestacao-de-contas',mission=mission)
        response.status_code=503
        return response
    mission=require_capture(request,codigo)
    return form_page(request,mission,{'tipo':'aplicativo','participant_id':request.state.user['participant_id'],
        'data':mission_today(mission).isoformat(),'moeda':'EUR' if codigo=='portugal' else 'ARS','intent':'rascunho','request_key':secrets.token_urlsafe(24)})


@router.get('/missoes/{codigo}/comprovantes/{entry_id:int}',name='receipt_detail')
def receipt_detail(request: Request,codigo: str,entry_id: int):
    mission=require_capture(request,codigo)
    entry=current_entry(request,mission,entry_id)
    return render(request,'receipt_detail.html',title='Comprovante sintético',active='prestacao-de-contas',mission=mission,entry=entry,statuses=STATUSES,
        history=request.app.state.receipts.history(entry_id,actor_id(request)),
        storage_events=request.app.state.receipts.storage_events(entry_id,actor_id(request)),message=request.query_params.get('aviso')=='salvo')


@router.get('/missoes/{codigo}/comprovantes/{entry_id:int}/editar')
def edit_receipt(request: Request,codigo: str,entry_id: int):
    mission=require_capture(request,codigo)
    entry=current_entry(request,mission,entry_id)
    values={**entry,'valor':f"{entry['valor_centavos']/100:.2f}" if entry['valor_centavos'] is not None else '',
        'intent':'rascunho' if entry['status']=='rascunho' else 'revisao','request_key':secrets.token_urlsafe(24)}
    values.update({'extra_'+k:v for k,v in entry['complemento'].items()})
    values.update({('conditional_'+k.removeprefix('conditional_') if k.startswith('conditional_') else 'check_'+k):('on' if v is True else v) for k,v in entry['checklist']['answers'].items()})
    return form_page(request,mission,values,entry)


@router.post('/missoes/{codigo}/comprovantes/novo')
@router.post('/missoes/{codigo}/comprovantes/{entry_id:int}/editar')
async def save_receipt(request: Request,codigo: str,entry_id: int | None=None):
    mission=require_capture(request,codigo)
    entry=current_entry(request,mission,entry_id) if entry_id else None
    values,files=await read_receipt_form(request)
    selected_type=values.get('tipo','')
    definition=load_rules()['types'].get(selected_type,{})
    for field in definition.get('fields',{}):
        values['extra_'+field]=values.get('extra_'+selected_type+'_'+field,'')
    for i,_ in enumerate(definition.get('items',[])):
        values['check_'+str(i)]=values.get('check_'+selected_type+'_'+str(i),'')
    for i,_ in enumerate(definition.get('conditional',[])):
        values['conditional_'+str(i)]=values.get('conditional_'+selected_type+'_'+str(i),'pendente')
    try:
        data=validate_expense(values,mission,request.state.user['participant_id'],load_rules())
        key=values.get('request_key','')
        if not 20<=len(key)<=100: raise InvalidActivity({'form':'Reabra o formulário para obter uma identificação de envio válida.'})
        version=None
        if entry:
            try: version=int(values.get('version',''))
            except (ValueError,TypeError): raise InvalidActivity({'version':'Confira a versão atual do registro.'})
        validated=[await run_in_threadpool(validate_file,file) for file in files]
        item_id=await run_in_threadpool(request.app.state.receipts.save,mission,data,validated,actor_id(request),key,entry_id,version)
    except (InvalidActivity,ActivityConflict) as error:
        errors=error.errors if isinstance(error,InvalidActivity) else {'form':str(error)}
        status=422 if isinstance(error,InvalidActivity) else 409
        if 'application/json' in request.headers.get('accept',''): return JSONResponse({'errors':errors},status_code=status)
        errors['files_notice']='Os campos foram preservados. Por segurança do navegador, selecione os arquivos novamente.'
        return form_page(request,mission,values,entry,errors,status)
    except (sqlite3.Error,OSError):
        errors={'form':'Não foi possível confirmar o salvamento. Seus dados foram preservados. Tente novamente com o mesmo formulário.'}
        if 'application/json' in request.headers.get('accept',''): return JSONResponse({'errors':errors},status_code=503)
        errors['files_notice']='Selecione os arquivos novamente antes de reenviar.'
        return form_page(request,mission,values,entry,errors,503)
    url=f'/missoes/{codigo}/comprovantes/{item_id}?aviso=salvo'
    if 'application/json' in request.headers.get('accept',''): return JSONResponse({'redirect':url})
    return RedirectResponse(url,status_code=303)


@router.get('/missoes/{codigo}/comprovantes/{entry_id:int}/anexos/{attachment_id}')
def receipt_attachment(request: Request,codigo: str,entry_id: int,attachment_id: str):
    mission=require_capture(request,codigo)
    entry=current_entry(request,mission,entry_id)
    attachment=next((a for a in entry['attachments'] if a['id']==attachment_id),None)
    if not attachment: raise HTTPException(404,'Anexo não encontrado.')
    if not attachment['available']: raise HTTPException(410,'Este arquivo está indisponível. Confira o estado do armazenamento.')
    try: content=request.app.state.receipt_storage.read_attachment(attachment)
    except OSError: raise HTTPException(410,'O arquivo não passou na verificação de integridade. Reenvie o anexo.') from None
    extension=attachment['extension']
    return Response(content,media_type=attachment['mime'],headers={'Content-Disposition':f'attachment; filename="sintetico-{attachment_id}.{extension}"','Content-Security-Policy':"sandbox; default-src 'none'",'Cache-Control':'no-store'})


@router.post('/missoes/{codigo}/comprovantes/{entry_id:int}/anexos/{attachment_id}/excluir')
async def delete_receipt_attachment(request: Request,codigo: str,entry_id: int,attachment_id: str):
    mission=require_capture(request,codigo)
    entry=current_entry(request,mission,entry_id)
    values=await read_form(request)
    if values.get('confirm_delete')!='on': raise HTTPException(422,'Confirme a exclusão do anexo sintético.')
    try:
        version=int(values.get('version',''))
        await run_in_threadpool(request.app.state.receipts.delete_attachment,mission.id,entry_id,attachment_id,actor_id(request),version)
    except (ValueError,ActivityConflict) as error:
        raise HTTPException(409,'Confira a versão atual do registro antes de excluir.') from None
    except LookupError: raise HTTPException(404,'Anexo não encontrado.') from None
    except (OSError,sqlite3.Error): raise HTTPException(503,'Não foi possível confirmar a exclusão. Confira o registro antes de tentar novamente.') from None
    return RedirectResponse(f'/missoes/{codigo}/comprovantes/{entry_id}?aviso=salvo',status_code=303)
