"""Execute na raiz: python -m scripts.init_db."""
from app.core.config import Settings
from app.db.migrate import migrate
from app.db.seed import seed

if __name__ == "__main__":
    settings = Settings.from_env()
    settings.validate()
    migrate(settings.database_path)
    seed(settings.database_path)
    print(f"Banco inicializado: {settings.database_path}")
