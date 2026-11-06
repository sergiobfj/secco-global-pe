"""QA somente em SQLite temporário com concessão verificada."""
import argparse
import json
import os
from pathlib import Path

from app.core.test_database import TemporaryDatabase, assert_temporary_database, enable_test_mode

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=8057)
    parser.add_argument("--auth-mode",choices=("local","synthetic","pending"),default="local")
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
        if args.auth_mode=="synthetic":
            import sys
            sys.path.insert(0,str(ROOT/"tests"))
            from auth_support import SyntheticGoogle, synthetic_settings
            settings=synthetic_settings(temporary.path,google_redirect_uri=f"http://127.0.0.1:{args.port}/auth/google/callback")
            application=create_app(settings)
            google=SyntheticGoogle(settings)
            application.state.oidc=google.provider()
        else:
            application=create_app(Settings("development",args.auth_mode=="local",temporary.path))
        application.state.qa_auth_mode=args.auth_mode
        instance=temporary.nonce
        application.state.qa_instance=instance
        (ROOT/".tools").mkdir(exist_ok=True)
        manifest=ROOT/".tools/qa-current.json"
        manifest.write_text(json.dumps({"url":f"http://127.0.0.1:{args.port}","instance":instance,"auth_mode":args.auth_mode}),encoding="utf-8")
        @application.get("/__qa__/identity")
        def identity():
            assert_temporary_database(application.state.settings.database_path)
            return {"qa":True,"isolated":True,"policy":"temporary-lease-v1","instance":instance}
        if args.auth_mode=="synthetic":
            from fastapi import HTTPException
            from fastapi.responses import RedirectResponse
            from urllib.parse import urlencode
            @application.get("/__qa__/authorize")
            def synthetic_authorize(request: Request):
                assert_temporary_database(application.state.settings.database_path)
                if request.headers.get("x-secco-qa-instance")!=instance:
                    raise HTTPException(403,"Identidade de QA necessária.")
                google.nonce=request.query_params["nonce"]
                google.challenge=request.query_params["code_challenge"]
                return RedirectResponse("/auth/google/callback?"+urlencode({"state":request.query_params["state"],"code":"synthetic-browser-code"}),status_code=303)
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
