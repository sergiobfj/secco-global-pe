"""Manutenção sintética local explícita. Não migra nem inicializa a aplicação."""
import argparse
import json
from app.core.config import Settings
from app.services.local_receipt_storage import LocalReceiptStorage


def main():
    parser=argparse.ArgumentParser(description='Reconciliação do volume sintético privado, com aplicativo parado.')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--purge-quarantine',action='store_true')
    parser.add_argument('--confirm-synthetic',action='store_true')
    args=parser.parse_args()
    if not args.apply or not args.confirm_synthetic:
        parser.error('A manutenção exige --apply --confirm-synthetic. Não foi feita alteração.')
    settings=Settings.from_env(); settings.validate()
    if settings.receipts_storage_backend!='local': parser.error('Configure explicitamente o adaptador local sintético.')
    storage=LocalReceiptStorage(settings.database_path,settings.receipts_private_dir)
    try: print(json.dumps(storage.reconcile(purge_quarantine=args.purge_quarantine)))
    finally: storage.close()


if __name__=='__main__': main()
