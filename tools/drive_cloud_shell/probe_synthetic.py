"""Único formato de arquivo do pacote: os dois PNGs determinísticos do ensaio."""
import hashlib

MAX_FILE=69


class InvalidActivity(ValueError):
    pass


def validate_file(item):
    from app.services.drive_supervised import probe_png
    content=item['content']
    if (item['name']!='receipt.png' or item['mime']!='image/png' or len(content)!=69
            or content not in (probe_png('argentina'),probe_png('portugal'))):
        raise InvalidActivity('sintetico')
    return {**item,'extension':'png','checksum':hashlib.sha256(content).hexdigest(),'size_bytes':69}
