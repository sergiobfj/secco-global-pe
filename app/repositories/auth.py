"""Identidades e sessões opacas. Tokens Google nunca são persistidos."""
import hashlib
import hmac
import secrets
import sqlite3
import time
from app.db.connection import connect


class IdentityDenied(ValueError):
    pass


USER_SQL = """SELECT u.*,p.nome,m.codigo AS default_mission_code
 FROM app_users u JOIN participants p ON p.id=u.participant_id
 JOIN missions m ON m.id=u.default_mission_id"""


class AuthRepository:
    def __init__(self, settings, clock=time.time):
        self.settings = settings
        self.database_path = settings.database_path
        self.clock = clock

    def digest(self, purpose, value):
        return hmac.new(self.settings.session_secret.encode(), (purpose+":"+value).encode(), hashlib.sha256).hexdigest()

    def config_hash(self):
        s = self.settings
        return self.digest("config", s.google_client_id+"|"+s.google_workspace_domain+"|"+s.google_redirect_uri)

    def allowed(self, user):
        return (bool(user["enabled"]) and (user["participant_id"], user["email_allowlist"]) in self.settings.allowed_users
                and user["workspace_domain"] == self.settings.google_workspace_domain)

    def provision(self):
        """Associa a allowlist a participantes existentes, sem criar identidades Google."""
        with connect(self.database_path) as db:
            db.execute("BEGIN IMMEDIATE")
            for participant_id, email in self.settings.allowed_users:
                row = db.execute("SELECT mission_id FROM mission_participants WHERE participant_id=? ORDER BY mission_id LIMIT 1", (participant_id,)).fetchone()
                if not row:
                    raise RuntimeError("ALLOWED_USERS contém participante inexistente ou sem missão.")
                db.execute("""INSERT INTO app_users(participant_id,email_allowlist,default_mission_id)
                    VALUES(?,?,?) ON CONFLICT(participant_id) DO UPDATE SET email_allowlist=excluded.email_allowlist
                    WHERE app_users.email_allowlist!=excluded.email_allowlist""", (participant_id,email,row[0]))
            allowed_ids = [p for p,e in self.settings.allowed_users]
            if allowed_ids:
                placeholders = ",".join("?" for _ in allowed_ids)
                db.execute(f"UPDATE app_users SET enabled=0 WHERE participant_id NOT IN ({placeholders})", allowed_ids)

    def get_user(self, user_id):
        with connect(self.database_path) as db:
            row = db.execute(USER_SQL+" WHERE u.id=?", (user_id,)).fetchone()
            return dict(row) if row else None

    def bind_identity(self, claims):
        email = claims["email"].strip().casefold()
        try:
            with connect(self.database_path) as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(USER_SQL+" WHERE u.google_sub=?", (claims["sub"],)).fetchone()
                if row is None:
                    participant_id = next((p for p,e in self.settings.allowed_users if e == email), None)
                    row = db.execute(USER_SQL+" WHERE u.participant_id=?", (participant_id,)).fetchone()
                    if not row or row["google_sub"] is not None:
                        raise IdentityDenied()
                if not row["enabled"] or (row["participant_id"], row["email_allowlist"]) not in self.settings.allowed_users:
                    raise IdentityDenied()
                user_id = row["id"]
                if row["email_current"] and row["email_current"] != email:
                    db.execute("INSERT INTO auth_events(user_id,event) VALUES(?,'email_changed')", (user_id,))
                db.execute("""UPDATE app_users SET google_sub=?,email_current=?,workspace_domain=?,
                    last_login_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                    updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""",
                    (claims["sub"], email, claims["hd"].casefold(), user_id))
                return user_id
        except sqlite3.IntegrityError:
            raise IdentityDenied() from None

    def begin_login(self):
        state, browser, nonce = (secrets.token_urlsafe(32) for _ in range(3))
        verifier = secrets.token_urlsafe(64)
        now = self.clock()
        with connect(self.database_path) as db:
            db.execute("DELETE FROM oauth_transactions WHERE expires_at<=?", (now,))
            db.execute("INSERT INTO oauth_transactions VALUES(?,?,?,?,?)",
                (self.digest("state",state),self.digest("browser",browser),hashlib.sha256(nonce.encode()).hexdigest(),verifier,now+600))
        return {"state":state,"browser":browser,"nonce":nonce,"verifier":verifier}

    def consume_login(self, state, browser):
        if not state or not browser or len(state)>200 or len(browser)>200:
            raise IdentityDenied()
        with connect(self.database_path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM oauth_transactions WHERE state_hash=? AND browser_hash=? AND expires_at>?",
                (self.digest("state",state),self.digest("browser",browser),self.clock())).fetchone()
            if not row:
                raise IdentityDenied()
            db.execute("DELETE FROM oauth_transactions WHERE state_hash=?", (row["state_hash"],))
            return dict(row)

    def create_session(self, user_id, previous_token=None):
        now = self.clock()
        token, session_id, csrf = (secrets.token_urlsafe(48) for _ in range(3))
        with connect(self.database_path) as db:
            db.execute("BEGIN IMMEDIATE")
            user = db.execute(USER_SQL+" WHERE u.id=?", (user_id,)).fetchone()
            if not user or not self.allowed(user):
                raise IdentityDenied()
            if previous_token:
                old_hash = self.digest("session",previous_token)
                db.execute("UPDATE user_sessions SET revoked_at=? WHERE token_hash=? OR previous_hash=?", (now,old_hash,old_hash))
            db.execute("""INSERT INTO user_sessions(id,user_id,token_hash,csrf_secret,config_hash,created_at,last_seen_at,rotated_at,expires_at)
                VALUES(?,?,?,?,?,?,?,?,?)""", (session_id,user_id,self.digest("session",token),csrf,self.config_hash(),now,now,now,now+self.settings.session_absolute_seconds))
            db.execute("INSERT INTO auth_events(user_id,event) VALUES(?,'login')", (user_id,))
        return {"token":token,"csrf":csrf,"expires_at":now+self.settings.session_absolute_seconds}

    def resolve_session(self, token):
        if not token or len(token)>200 or not self.settings.auth_ready:
            return None
        now = self.clock()
        hashed = self.digest("session",token)
        with connect(self.database_path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT * FROM user_sessions WHERE token_hash=?
                OR (previous_hash=? AND previous_valid_until>?)""", (hashed,hashed,now)).fetchone()
            if not row or row["revoked_at"] is not None:
                return None
            user = db.execute(USER_SQL+" WHERE u.id=?", (row["user_id"],)).fetchone()
            if (not user or not self.allowed(user) or row["expires_at"]<=now
                    or row["last_seen_at"]+self.settings.session_idle_seconds<=now
                    or not hmac.compare_digest(row["config_hash"],self.config_hash())):
                db.execute("UPDATE user_sessions SET revoked_at=? WHERE id=?", (now,row["id"]))
                return None
            new_token = None
            if row["token_hash"] == hashed and row["rotated_at"]+self.settings.session_rotation_seconds<=now:
                new_token = secrets.token_urlsafe(48)
                db.execute("""UPDATE user_sessions SET previous_hash=token_hash,previous_valid_until=?,
                    token_hash=?,rotated_at=? WHERE id=?""", (now+30,self.digest("session",new_token),now,row["id"]))
            db.execute("UPDATE user_sessions SET last_seen_at=MAX(last_seen_at,?) WHERE id=?", (now,row["id"]))
            return {"user":dict(user),"csrf":row["csrf_secret"],"new_token":new_token,"expires_at":row["expires_at"]}

    def logout(self, token):
        if not token:
            return
        hashed = self.digest("session",token)
        with connect(self.database_path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT user_id FROM user_sessions WHERE token_hash=? OR previous_hash=?", (hashed,hashed)).fetchone()
            db.execute("UPDATE user_sessions SET revoked_at=? WHERE token_hash=? OR previous_hash=?", (self.clock(),hashed,hashed))
            if row:
                db.execute("INSERT INTO auth_events(user_id,event) VALUES(?,'logout')", (row[0],))

    def can_edit(self, user, mission_id):
        if not user or not self.allowed(user):
            return False
        with connect(self.database_path) as db:
            return bool(db.execute("""SELECT 1 FROM mission_participants WHERE participant_id=? AND mission_id=?
                UNION SELECT 1 FROM user_mission_permissions WHERE user_id=? AND mission_id=? AND can_edit=1""",
                (user["participant_id"],mission_id,user["id"],mission_id)).fetchone())

    def set_default(self, user_id, mission_id):
        with connect(self.database_path) as db:
            db.execute("UPDATE app_users SET default_mission_id=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (mission_id,user_id))

    def author_names(self):
        with connect(self.database_path) as db:
            return {r["id"]:r["nome"] for r in db.execute("SELECT u.id,p.nome FROM app_users u JOIN participants p ON p.id=u.participant_id")}
