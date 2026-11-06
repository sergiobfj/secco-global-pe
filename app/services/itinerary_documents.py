"""Local document readers. No network, credentials, database, or built-in operational itineraries."""
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
import hashlib
import re
import unicodedata


class DocumentError(ValueError):
    pass


def normalized(text):
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(text))
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()).split())


def clean(text):
    return ' '.join(str(text or '').split())


def clock(value):
    if isinstance(value, (datetime, time)):
        return value.strftime('%H:%M')
    match = re.fullmatch(r'(\d{1,2})\s*[:h]\s*(\d{1,2})?', clean(value), re.I)
    if not match:
        return None
    hour, minute = int(match[1]), int(match[2] or 0)
    return f'{hour:02}:{minute:02}' if hour < 24 and minute < 60 else None


def explicit_interval(text):
    pattern = r'(?<!\d)(\d{1,2})(?:[:h](\d{1,2}))?\s*(?:às|as|até|ate|[-–])\s*(\d{1,2})(?:[:h](\d{1,2}))?(?!\d)'
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    first = clock(f'{match[1]}:{match[2] or 0}')
    last = clock(f'{match[3]}:{match[4] or 0}')
    if not first or not last or last <= first:
        raise DocumentError('Intervalo escrito inválido; revise o documento.')
    return first, last


def category(text):
    words = normalized(text)
    if re.match(r'^(deslocamento|retorno|transfer|viagem|check in|transporte)\b',words):
        return 'transporte'
    if re.search(r'\b(almoco|jantar|cafe|refeicao|breakfast|lunch|dinner)\b', words):
        return 'alimentacao'
    if re.search(r'\b(deslocamento|retorno|transfer|viagem|check in|transporte)\b', words):
        return 'transporte'
    if re.search(r'\b(evento|summit|congresso|simposio|feira|week|oficina|conferencia)\b', words):
        return 'evento'
    return 'institucional'


def details(text):
    lines = [clean(line) for line in text.splitlines() if clean(line)]
    first = lines[0] if lines else ''
    title = re.split(r'\b(?:Morada|Endere[cç]o)\s*:', first, maxsplit=1, flags=re.I)[0].strip()
    title = re.sub(r'\s*[-–]?\s*\d{1,2}(?:[:h]\d{1,2})?\s*(?:as|às|até|ate|[-–])\s*\d{1,2}(?:[:h]\d{1,2})?\s*$', '', title, flags=re.I)
    title = re.sub(r'\s*\([^)]*(?:confirmar|verificar|a definir)[^)]*\)', '', title, flags=re.I).strip(' -–')
    address_match = re.search(r'\b(?:Morada|Endere[cç]o)\s*:\s*(.+)', text, re.I)
    address = clean(address_match[1]) if address_match else ''
    if not address:
        address = next((line for line in lines[1:] if re.search(r'^.+,\s*\d+\b', line)), '')
    venue = ''
    paren = re.search(r'\(([^)]+)\)', title)
    if paren:
        venue = clean(paren[1]); title = clean(title[:paren.start()] + title[paren.end():])
    if not venue:
        match = re.search(r'\b(?:visita\s+(?:ao|a|à)|(?:na|no)\s+)\s*(.+)', first, re.I)
        if match:
            venue = clean(match[1])
    if not venue and len(lines) > 1 and lines[1]!=address and not re.search(r'\d\s*(?:as|às)', lines[1], re.I):
        venue = lines[1]
    return title.strip(' .;-–'), venue[:200], address


@dataclass
class SourceEvent:
    day: str
    title: str
    description: str
    category: str
    locator: str
    start: str | None = None
    end: str | None = None
    time_kind: str = 'missing'
    grid_start: str | None = None
    grid_end: str | None = None
    location: str = ''
    address: str = ''
    warnings: list = field(default_factory=list)
    occurrence: int = 0

    def identity(self):
        return f'{self.day}|{normalized(self.title)}|{self.occurrence}'


@dataclass
class ParsedDocument:
    format: str
    name: str
    sha256: str
    events: list
    free_windows: list = field(default_factory=list)
    contexts: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


def _finish(events):
    occurrences = defaultdict(int)
    for event in events:
        key = event.day, normalized(event.title)
        event.occurrence = occurrences[key]; occurrences[key] += 1
        if not event.title or len(event.title) > 160:
            raise DocumentError('Título ausente ou maior que 160 caracteres; revise a origem.')
        if len(event.description) > 4000 or len(event.address) > 400:
            raise DocumentError('Conteúdo excede os limites da agenda; revise sem truncar informações.')
    return events


def read_xlsx(path, *, context_labels=()):
    from openpyxl import load_workbook
    from openpyxl.cell.cell import MergedCell
    from openpyxl.utils import get_column_letter
    values = load_workbook(path, data_only=False, keep_links=False)
    cached = load_workbook(path, data_only=True, keep_links=False)
    events, free, contexts, warnings = [], [], [], []
    ignored = {normalized(x) for x in context_labels}
    for sheet in values:
        initial = sheet['C2'].value
        if isinstance(initial, datetime): initial = initial.date()
        if not isinstance(initial, date):
            raise DocumentError('A data inicial C2 deve ser uma data Excel válida.')
        times = {r: clock(sheet.cell(r, 2).value) for r in range(5, sheet.max_row + 1)}
        times = {r: t for r, t in times.items() if t}
        if not times:
            raise DocumentError('Não foram encontrados horários na coluna B.')
        if any(times[b] <= times[a] for a, b in zip(times, list(times)[1:])):
            raise DocumentError('A grade de horários não é crescente.')
        def body(row, col):
            cell = sheet.cell(row, col)
            if isinstance(cell, MergedCell):
                for merged in sheet.merged_cells.ranges:
                    if cell.coordinate in merged:
                        return sheet.cell(merged.min_row, merged.min_col).value or ''
            return cell.value or ''
        for col in range(3, sheet.max_column + 1):
            header = sheet.cell(3, col); raw = header.value
            if raw is None: continue
            current = cached[sheet.title].cell(3, col).value
            if isinstance(raw, str) and raw.startswith('='):
                match = re.fullmatch(r'=\$?C\$?2(?:\+(\d+))?', raw.replace(' ', ''), re.I)
                if not match: raise DocumentError('Fórmula de data não suportada; forneça uma planilha com datas verificáveis.')
                day = initial + timedelta(days=int(match[1] or 0))
                if isinstance(current, datetime): current = current.date()
                if current is not None and current != day:
                    raise DocumentError('Data calculada e valor armazenado divergem; revise a planilha.')
            else:
                day = raw.date() if isinstance(raw, datetime) else raw
            if not isinstance(day, date): raise DocumentError('Cabeçalho de dia inválido.')
            blocks = []; active = None
            for row, hour in times.items():
                text = str(body(row, col)).strip()
                key = normalized(details(text)[0]) if text else ''
                if not text or key in {'livre', 'dia livre', 'tempo livre'} or key in ignored:
                    if active: blocks.append(active); active = None
                    if text:
                        destination = contexts if key in ignored else free
                        destination.append({'day': day.isoformat(), 'start': None if key=='dia livre' else hour,
                            'all_day':key=='dia livre','label': clean(text), 'locator': f'{sheet.title}!{get_column_letter(col)}{row}'})
                    continue
                if active and active['key'] == key and row == active['rows'][-1] + 1:
                    active['rows'].append(row)
                    if text not in active['texts']: active['texts'].append(text)
                else:
                    if active: blocks.append(active)
                    active = {'key': key, 'rows': [row], 'texts': [text]}
            if active: blocks.append(active)
            # A written interval identifies a continuous event even when a meal interrupts its cells.
            explicit_groups = {}
            for block in blocks:
                combined = '\n'.join(block['texts']); interval = explicit_interval(combined)
                signature = (block['key'], interval)
                if interval and signature in explicit_groups:
                    existing = explicit_groups[signature]
                    existing['rows'] += block['rows']
                    existing['texts'] += [t for t in block['texts'] if t not in existing['texts']]
                else:
                    if interval: explicit_groups[signature] = block
            unique = [b for b in blocks if not explicit_interval('\n'.join(b['texts'])) or explicit_groups[(b['key'], explicit_interval('\n'.join(b['texts'])))] is b]
            for block in unique:
                text = '\n'.join(block['texts']); title, venue, address = details(block['texts'][0])
                start_row, end_row = min(block['rows']), max(block['rows'])
                grid_start = times[start_row]
                grid_end = times.get(end_row + 1) if len(block['rows']) > 1 else None
                interval = explicit_interval(text)
                provisional = bool(re.search(r'confirmar|verificar.*hor[aá]rio|provis[oó]ri|a definir', text, re.I))
                kind = 'provisional' if provisional else 'explicit' if interval else 'grid'
                start, end = interval if interval else (grid_start, grid_end)
                issues = []
                # Last occupied row can be an endpoint; do not assert a conflict from an invented +30 min.
                if interval and (grid_start != interval[0] or times[end_row] > interval[1]):
                    kind = 'conflict'; issues.append('Horário escrito diverge das marcações da grade.')
                elif interval and grid_end and grid_end!=interval[1]:
                    issues.append('A marca final da grade pode indicar o término; prevalece o intervalo escrito, sem adicionar duração à última célula.')
                if sheet.sheet_state != 'visible' or sheet.column_dimensions[get_column_letter(col)].hidden or any(sheet.row_dimensions[r].hidden for r in block['rows']):
                    issues.append('A origem contém células ocultas; revisar.')
                events.append(SourceEvent(day.isoformat(), title, text, category(title),
                    f'{sheet.title}!{get_column_letter(col)}{start_row}:{get_column_letter(col)}{end_row}',
                    start, end, kind, grid_start, grid_end, venue, address, issues))
    values.close();cached.close()
    return ParsedDocument('xlsx-grid', path.name, hashlib.sha256(path.read_bytes()).hexdigest(), _finish(events), free, contexts, warnings)


def read_pdf(path, *, year):
    import pdfplumber
    if not 2000 <= year <= 2100: raise DocumentError('Ano inválido.')
    events = []
    with pdfplumber.open(path) as document:
        for page_number, page in enumerate(document.pages, 1):
            words = page.extract_words()
            dates = [w for w in words if re.fullmatch(r'\d{1,2}/\d{1,2}(?:/\d{4})?', w['text'])]
            if not dates: raise DocumentError('O PDF não possui cabeçalhos de datas extraíveis; revise a imagem.')
            header_y = min(w['top'] for w in dates)
            dates = sorted([w for w in dates if abs(w['top'] - header_y) < 3], key=lambda w: w['x0'])
            centers = [(w['x0'] + w['x1']) / 2 for w in dates]
            left = centers[0] - (centers[1] - centers[0]) / 2 if len(centers) > 1 else centers[0] - 30
            ticks = sorted([w for w in words if clock(w['text']) and w['x1'] < left + 1 and w['top'] > header_y], key=lambda w: w['top'])
            if len(ticks) < 2: raise DocumentError('Não foi possível reconhecer a escala horária do PDF.')
            step = sorted(b['top']-a['top'] for a,b in zip(ticks,ticks[1:]))[len(ticks)//2-1]
            top, bottom = ticks[0]['top']-step/2, ticks[-1]['bottom']+step/2
            for index, header in enumerate(dates):
                label = header['text'].split('/')
                day = date(int(label[2]) if len(label)==3 else year, int(label[1]), int(label[0]))
                lo = left if index==0 else (centers[index-1]+centers[index])/2
                hi = (centers[index]+centers[index+1])/2 if index+1<len(centers) else centers[index]+(centers[index]-centers[index-1])/2 if len(centers)>1 else page.width
                selected = sorted([w for w in words if lo < (w['x0']+w['x1'])/2 < hi and top <= w['top'] <= bottom], key=lambda w:(round(w['top']/2)*2,w['x0']))
                clusters=[]
                for word in selected:
                    if not clusters or word['top']-max(w['bottom'] for w in clusters[-1]) > step*1.6:
                        clusters.append([word])
                    else: clusters[-1].append(word)
                for ordinal, cluster in enumerate(clusters):
                    text=clean(' '.join(w['text'] for w in cluster));title,venue,address=details(text)
                    interval=explicit_interval(text);grid_start=grid_end=None
                    mid_y=(min(w['top'] for w in cluster)+max(w['bottom'] for w in cluster))/2
                    colored=[]
                    for rectangle in page.rects:
                        color=rectangle.get('non_stroking_color')
                        if isinstance(color,(list,tuple)) and len(color)>=3 and max(color)-min(color)>.04 and rectangle['x0']<=centers[index]<=rectangle['x1']:
                            colored.append(rectangle)
                    regions=[]
                    for rectangle in sorted(colored,key=lambda r:r['top']):
                        if regions and rectangle['top']<=regions[-1][1]+1:
                            regions[-1][1]=max(regions[-1][1],rectangle['bottom'])
                        else:regions.append([rectangle['top'],rectangle['bottom']])
                    for first,last in regions:
                        if first<=mid_y<=last and last-first < (bottom-top)*.85:
                            first_tick=min(ticks,key=lambda w:abs((w['top']+w['bottom'])/2-(first+step/2)))
                            grid_start=clock(first_tick['text'])
                            candidates=[w for w in ticks if (w['top']+w['bottom'])/2>=last]
                            grid_end=clock(candidates[0]['text']) if candidates else None
                    # Coloured area is documentary context only, never a confirmed duration.
                    kind='explicit' if interval else 'grid_window' if grid_start else 'missing'
                    start,end=interval if interval else (None,None)
                    events.append(SourceEvent(day.isoformat(),title,text,category(title),f'página {page_number}, coluna {index+1}, bloco {ordinal+1}',
                        start,end,kind,grid_start,grid_end,venue,address))
    return ParsedDocument('pdf-grid',path.name,hashlib.sha256(path.read_bytes()).hexdigest(),_finish(events))


def read_document(path, *, year=None, context_labels=()):
    from pathlib import Path
    path=Path(path)
    if path.suffix.lower()=='.xlsx': return read_xlsx(path,context_labels=context_labels)
    if path.suffix.lower()=='.pdf':
        if year is None: raise DocumentError('Informe o ano de referência do PDF.')
        return read_pdf(path,year=year)
    raise DocumentError('Formato não suportado; use PDF de grade ou XLSX.')
