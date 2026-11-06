"""QA somente em SQLite temporário com concessão verificada."""
import argparse
import json
import os
from pathlib import Path

from app.core.test_database import TemporaryDatabase, assert_temporary_database, enable_test_mode

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=8057)
    args=parser.parse_args()
    enable_test_mode()
    if os.getenv("DATABASE_PATH"):
        # Uma configuração persistente explícita falha, em vez de ser ignorada.
        assert_temporary_database(os.environ["DATABASE_PATH"])
    if os.getenv("APP_ENV","development")!="development":
        raise RuntimeError("QA não pode ser iniciado como produção.")
    with TemporaryDatabase() as temporary:
        os.environ["DATABASE_PATH"]=str(temporary.path)
        os.environ["SECCO_TEST_MODE"]="1"
        from app.core.config import ROOT, Settings
        from app.core.forms import read_form
        from app.main import create_app
        from fastapi import Request
        import uvicorn
        application=create_app(Settings("development",True,temporary.path))
        instance=temporary.nonce
        application.state.qa_instance=instance
        (ROOT/".tools").mkdir(exist_ok=True)
        manifest=ROOT/".tools/qa-current.json"
        manifest.write_text(json.dumps({"url":f"http://127.0.0.1:{args.port}","instance":instance}),encoding="utf-8")
        @application.get("/__qa__/identity")
        def identity():
            assert_temporary_database(application.state.settings.database_path)
            return {"qa":True,"isolated":True,"policy":"temporary-lease-v1","instance":instance}
        server=uvicorn.Server(uvicorn.Config(application,host="127.0.0.1",port=args.port,proxy_headers=False))
        @application.post("/__qa__/shutdown")
        async def shutdown(request: Request):
            await read_form(request)
            server.should_exit=True
            return {"status":"encerrando"}
        try:
            server.run()
        finally:
            if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8")).get("instance")==instance:
                manifest.unlink()

if __name__=="__main__":
    main()
