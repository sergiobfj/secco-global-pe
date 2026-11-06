"""Armazenamento efêmero e privado. Não é alternativa permanente ao Drive."""
import hashlib
import os
from pathlib import Path
import re
import secrets
import struct
import tempfile
from threading import RLock
import zlib
from app.core.test_database import assert_temporary_database, testing_enabled
from app.services.itinerary import InvalidActivity

MAX_FILE=5*1024*1024
MAX_STORAGE=100*1024*1024


def validate_file(item):
    name=item["name"]
    if (not name or len(name)>180 or any(ord(c)<32 for c in name) or any(c in name for c in ('/','\\',':')) or name.startswith('.') or name.endswith((' ','.'))):
        raise InvalidActivity({"files":"O nome do arquivo contém caracteres não permitidos."})
    suffix=Path(name).suffix.lower()
    extension={".jpeg":"jpg",".jpg":"jpg",".png":"png",".pdf":"pdf"}.get(suffix)
    expected={"jpg":"image/jpeg","png":"image/png","pdf":"application/pdf"}.get(extension)
    content=item["content"]
    if not content or len(content)>MAX_FILE: raise InvalidActivity({"files":"Cada arquivo deve ter conteúdo e no máximo 5 MB."})
    if expected is None or item["mime"]!=expected: raise InvalidActivity({"files":"Envie somente JPEG, PNG ou PDF com tipo e extensão correspondentes."})
    try:
        if extension=="png": _png(content)
        elif extension=="jpg": _jpeg(content)
        else: _pdf(content)
    except (ValueError,struct.error,zlib.error,OverflowError):
        raise InvalidActivity({"files":"O conteúdo do arquivo não corresponde a uma imagem ou PDF aceito."}) from None
    return {**item,"extension":extension,"checksum":hashlib.sha256(content).hexdigest(),"size_bytes":len(content)}


def _png(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError()
    pos=8; seen=[]; compressed=bytearray()
    while pos<len(data):
        length,kind=struct.unpack('>I4s',data[pos:pos+8]); pos+=8
        if length>MAX_FILE or pos+length+4>len(data): raise ValueError()
        value=data[pos:pos+length]; crc=struct.unpack('>I',data[pos+length:pos+length+4])[0]
        if zlib.crc32(kind+value)&0xffffffff!=crc: raise ValueError()
        pos+=length+4; seen.append(kind)
        if len(seen)==1:
            if kind!=b'IHDR' or length!=13: raise ValueError()
            w,h,depth,color,comp,flt,interlace=struct.unpack('>IIBBBBB',value)
            if not 0<w*h<=16000000 or not w or not h or comp or flt or interlace not in (0,1) or color not in (0,2,3,4,6) or depth not in (1,2,4,8,16): raise ValueError()
        elif kind==b'IHDR': raise ValueError()
        if kind==b'IDAT': compressed.extend(value)
        if kind==b'IEND':
            if length or pos!=len(data): raise ValueError()
            break
    if not seen or seen[-1]!=b'IEND' or not compressed: raise ValueError()
    valid_depths={0:(1,2,4,8,16),2:(8,16),3:(1,2,4,8),4:(8,16),6:(8,16)}
    if depth not in valid_depths[color]: raise ValueError()
    decoder=zlib.decompressobj()
    decoded=decoder.decompress(compressed,32*1024*1024+1)
    if len(decoded)>32*1024*1024 or not decoder.eof or decoder.unused_data: raise ValueError()
    if interlace==0:
        channels={0:1,2:3,3:1,4:2,6:4}[color]
        row_bytes=(w*depth*channels+7)//8
        if len(decoded)!=h*(row_bytes+1) or any(decoded[i]>4 for i in range(0,len(decoded),row_bytes+1)): raise ValueError()


def _jpeg(data):
    if not data.startswith(b'\xff\xd8\xff') or not data.endswith(b'\xff\xd9'): raise ValueError()
    pos=2; frame=False; scan=False
    while pos<len(data)-2:
        if data[pos]!=255: raise ValueError()
        while pos<len(data) and data[pos]==255: pos+=1
        marker=data[pos]; pos+=1
        if marker in (0,216,217): raise ValueError()
        if 208<=marker<=215: continue
        length=struct.unpack('>H',data[pos:pos+2])[0]
        if length<2 or pos+length>len(data): raise ValueError()
        payload=data[pos+2:pos+length]
        if marker in (192,193,194):
            if len(payload)<6: raise ValueError()
            h,w=struct.unpack('>HH',payload[1:5])
            if not w or not h or w*h>16000000: raise ValueError()
            frame=True
        pos+=length
        if marker==218:
            scan=True
            while pos<len(data)-2:
                if data[pos]==255 and data[pos+1] not in (0,255,*range(208,216)): break
                pos+=1
    if not frame or not scan or pos!=len(data)-2: raise ValueError()


def _pdf(data):
    if not re.match(rb'%PDF-1\.[0-7][\r\n]',data) or not data.rstrip().endswith(b'%%EOF'): raise ValueError()
    canonical=re.sub(rb'#([0-9a-fA-F]{2})',lambda m:bytes([int(m[1],16)]),data)
    if re.search(rb'/(?:JavaScript|JS|Launch|EmbeddedFile|OpenAction|AA|RichMedia|XFA|Encrypt)\b',canonical): raise ValueError()
    match=re.search(rb'startxref\s+(\d+)\s+%%EOF\s*$',data)
    if not match or not re.search(rb'\d+\s+\d+\s+obj\b',data): raise ValueError()
    offset=int(match[1])
    if offset>=len(data) or not (data[offset:].startswith(b'xref') or re.match(rb'\d+\s+\d+\s+obj\b',data[offset:])): raise ValueError()
    if b'/Root' not in data: raise ValueError()


class TemporaryReceiptStorage:
    def __init__(self, database_path):
        parent=None
        if testing_enabled():
            assert_temporary_database(database_path)
            parent=Path(database_path).parent
        self._temporary=tempfile.TemporaryDirectory(prefix="secco-receipts-",dir=parent)
        self.directory=Path(self._temporary.name).resolve()
        self.session=secrets.token_hex(24)
        self.marker=self.directory/".owner"
        self.marker.write_text(self.session,encoding="ascii")
        self.lock=RLock()

    def _assert_owner(self):
        if self.directory.is_symlink() or self.directory.resolve()!=self.directory or self.marker.is_symlink() or self.marker.read_text(encoding="ascii")!=self.session:
            raise OSError("Armazenamento temporário indisponível.")

    def _path(self, identifier):
        if not re.fullmatch(r'[a-f0-9]{32}',identifier): raise OSError("Identificador inválido.")
        self._assert_owner()
        candidate=self.directory/identifier
        if candidate.is_symlink(): raise OSError("Arquivo temporário inválido.")
        return candidate

    def put(self, identifier, content):
        with self.lock:
            target=self._path(identifier)
            total=sum(p.stat().st_size for p in self.directory.iterdir() if p.is_file())
            if total+len(content)>MAX_STORAGE: raise OSError("Limite temporário atingido.")
            try:
                with target.open('xb') as stream:
                    stream.write(content); stream.flush(); os.fsync(stream.fileno())
            except OSError:
                if target.is_file(): target.unlink()
                raise

    def read(self, identifier, checksum):
        with self.lock:
            content=self._path(identifier).read_bytes()
            if hashlib.sha256(content).hexdigest()!=checksum: raise OSError("Integridade do arquivo inválida.")
            return content

    def available(self, attachment):
        if attachment['storage_status']!='recebido_temporario' or attachment['storage_session']!=self.session: return False
        try:
            self.read(attachment['id'],attachment['checksum']); return True
        except OSError: return False

    def remove(self, identifier):
        with self.lock:
            self._path(identifier).unlink(missing_ok=True)

    def close(self):
        with self.lock:
            self._assert_owner()
            self._temporary.cleanup()
