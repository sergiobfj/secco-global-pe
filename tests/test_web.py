from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from app.core.config import ROOT, Settings
from app.db.connection import connect
from app.main import create_app


def test_startup_initializes_database(client):
    assert client.get("/health").json() == {"status":"ok","ambiente":"development"}
    with connect(client.app.state.settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM missions").fetchone()[0] == 2


@pytest.mark.parametrize("env,flag",[
    ("",False),("production",True),("production",False),("development",False),("staging",True)
])
def test_unsafe_configuration_refused(tmp_path,env,flag):
    database = tmp_path / "must-not-exist.sqlite3"
    with pytest.raises(RuntimeError,match="não pode executar"):
        with TestClient(create_app(Settings(env,flag,database))):
            pass
    assert not database.exists()


def test_home(client):
    response = client.get("/")
    assert response.status_code == 200
    for text in ["SECCO Global PE","Portugal","Argentina","Hugo Mendes","Renato","Tiago Prado","Bruno de Castro","Acessar missão"]:
        assert text in response.text
    assert 'lang="pt-BR"' in response.text
    assert 'aria-label="Navegação principal"' in response.text


@pytest.mark.parametrize("code,country,target",[
    ("portugal","Portugal","10"),("argentina","Argentina","8")
])
def test_dashboard(client,code,country,target):
    response = client.get("/missoes/"+code)
    assert response.status_code == 200
    for text in ["Missão "+country,"Agenda do dia","Nenhum compromisso cadastrado","Pendências",
                 "Nenhuma pendência cadastrada","Meta: "+target,"Atividades previstas"]:
        assert text in response.text


def test_api_missions(client):
    data = client.get("/api/missoes").json()
    assert len(data) == 2
    assert [m["codigo"] for m in data] == ["portugal","argentina"]
    for code in ("portugal","argentina"):
        result = client.get("/api/missoes/"+code)
        assert result.status_code == 200
        assert result.json()["codigo"] == code
        assert all(p["email"] is None for p in result.json()["participantes"])


@pytest.mark.parametrize("section",["planejamento","diario","prestacao-de-contas","organizacao","documentos"])
def test_placeholder_pages(client,section):
    for prefix in ("/secoes/","/missoes/portugal/secoes/","/missoes/argentina/secoes/"):
        response = client.get(prefix+section)
        assert response.status_code == 200
        if section == "planejamento":
            assert ("Planejamento" if prefix!="/secoes/" else "Acessar missão") in response.text
        else:
            assert "Funcionalidade em desenvolvimento" in response.text


@pytest.mark.parametrize("url",["/missoes/nao-existe","/nao-existe","/secoes/invalida","/missoes/nao-existe/secoes/diario"])
def test_404(client,url):
    response = client.get(url)
    assert response.status_code == 404
    assert "Voltar ao início" in response.text


def test_api_404(client):
    assert client.get("/api/missoes/nao-existe").status_code == 404


@pytest.mark.parametrize("method",["post","put","patch","delete"])
def test_no_write_endpoints(client,method):
    assert getattr(client,method)("/api/missoes").status_code == 405


def test_security_headers_and_unknown_host(client):
    response = client.get("/")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/",headers={"host":"attacker.invalid"}).status_code == 400
    assert client.get("/docs").status_code == 404


def test_non_loopback_connections_refused(tmp_path):
    app = create_app(Settings("development",True,tmp_path/"remote.sqlite3"))
    with TestClient(app,client=("192.168.0.10",1234)) as remote:
        assert remote.get("/").status_code == 403


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()

    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if (tag,key) in [("a","href"),("img","src"),("script","src"),("link","href")]:
                if value and not value.startswith("#"):
                    self.links.add(value)


def test_all_navigation_and_assets_resolve(client):
    for url in ("/","/missoes/portugal","/missoes/argentina"):
        parser = LinkParser()
        parser.feed(client.get(url).text)
        for link in parser.links:
            if link.startswith("https://seccolab.com.br/"):
                continue
            assert client.get(link).status_code == 200, link


def test_manifest_and_no_external_assets(client):
    response = client.get("/static/manifest.webmanifest")
    assert response.status_code == 200
    assert response.json()["lang"] == "pt-BR"
    for file in (ROOT/"app/templates").rglob("*.html"):
        source = file.read_text(encoding="utf-8")
        assert "—" not in source and "fonts.googleapis.com" not in source


def test_templates_escape_database_content(client):
    database = client.app.state.settings.database_path
    with connect(database) as db:
        db.execute("INSERT INTO mission_tasks(mission_id,titulo) VALUES(1,?)",('<script>alert("teste")</script>',))
    response = client.get("/missoes/portugal")
    assert '<script>alert("teste")</script>' not in response.text
    assert "&lt;script&gt;" in response.text
