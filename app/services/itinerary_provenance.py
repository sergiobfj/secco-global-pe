"""Small versioned provenance envelope in the existing creation-key column; no schema change."""
import hashlib,json,re

PREFIX='official-itinerary-v1:'
TIME_LABELS={'explicit':'Horário informado no documento','grid':'Horário estimado pela grade',
    'grid_window':'Horário a confirmar','missing':'Horário não informado','provisional':'Horário provisório',
    'conflict':'Horários divergentes — revisar','user':'Horário editado pela equipe'}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def encode(metadata):
    return PREFIX+json.dumps(metadata,sort_keys=True,separators=(',',':'),ensure_ascii=False)

def decode(value):
    if not isinstance(value,str) or not value.startswith(PREFIX):return None
    try:data=json.loads(value[len(PREFIX):])
    except (ValueError,TypeError):return None
    if not isinstance(data,dict):return None
    if not isinstance(data.get('key'),str) or not re.fullmatch(r'official:[a-f0-9]{64}',data['key']):return None
    if any(not isinstance(data.get(key),str) or not re.fullmatch(r'[a-f0-9]{64}',data[key]) for key in ('baseline','source_digest')):return None
    document=data.get('document')
    if not isinstance(document,dict) or any(not isinstance(document.get(key),str) or not document[key] for key in ('name','sha256','format')):return None
    if type(data.get('version')) is not int or data['version']<1:return None
    if data.get('time_kind') not in TIME_LABELS:return None
    if any(not isinstance(data.get(key),str) or not data[key] for key in ('source_key','locator')):return None
    if any(data.get(key) is not None and not isinstance(data[key],str) for key in ('grid_start','grid_end','source_start','source_end')):return None
    return data
