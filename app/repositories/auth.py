"""OIDC e sessões comuns a viajantes e coordenação, sem identidade financeira implícita."""
import hashlib
import hmac
import secrets
import sqlite3
import time
from app.db.connection import connect
from app.core.workspace_access import COORDINATOR_KEY,COORDINATOR_PREFIX,SECCO_ACCOUNTS,WORKSPACE_DOMAIN,account_key


class IdentityDenied(ValueError):
    pass


USER_SQL="""SELECT u.*,p.nome,m.codigo AS default_mission_code
 FROM app_users u JOIN participants p ON p.id=u.participant_id
 JOIN missions m ON m.id=u.default_mission_id"""


class AuthRepository:
    def __init__(self,settings,clock=time.time):
        self.settings=settings; self.database_path=settings.database_path; self.clock=clock

    def digest(self,purpose,value):
        return hmac.new(self.settings.session_secret.encode(),(purpose+':'+value).encode(),hashlib.sha256).hexdigest()

    def config_hash(self):
        s=self.settings
        return self.digest('config',s.google_client_id+'|'+s.google_workspace_domain+'|'+s.google_redirect_uri)

    def _user(self,row,coordinator=False):
        if not row: return None
        user=dict(row)
        user['is_coordinator']=coordinator
        user['primary_locked']=coordinator or self.settings.google_workspace_domain==WORKSPACE_DOMAIN
        if coordinator:
            user.update(id=COORDINATOR_PREFIX+str(row['id']),participant_id=None,role='coordinator',default_mission_id=None,default_mission_code=None)
        elif self.settings.google_workspace_domain==WORKSPACE_DOMAIN:
            policy=SECCO_ACCOUNTS.get(user['participant_id'])
            if policy and policy[0]==user['email_allowlist']: user['default_mission_code']=policy[1]
        return user

    def _location(self,user_id):
        if isinstance(user_id,str) and user_id.startswith(COORDINATOR_PREFIX):
            suffix=user_id[len(COORDINATOR_PREFIX):]
            if not suffix.isdecimal() or not 0<int(suffix)<2**63: raise IdentityDenied()
            return 'coordination_accounts','coordination_sessions',int(suffix),True
        if type(user_id) is not int or user_id<=0: raise IdentityDenied()
        return 'app_users','user_sessions',user_id,False

    def _lookup(self,db,user_id):
        _,_,identifier,coord=self._location(user_id)
        sql='SELECT * FROM coordination_accounts WHERE id=?' if coord else USER_SQL+' WHERE u.id=?'
        return self._user(db.execute(sql,(identifier,)).fetchone(),coord)

    def _event(self,db,user_id,event):
        _,_,identifier,coord=self._location(user_id)
        column='coordinator_id' if coord else 'user_id'
        db.execute(f'INSERT INTO auth_events({column},event) VALUES(?,?)',(identifier,event))

    def allowed(self,user):
        user=dict(user)
        key=account_key(user)
        return (bool(user['enabled']) and (key,user['email_allowlist']) in self.settings.allowed_users
                and user['workspace_domain']==self.settings.google_workspace_domain)

    def provision(self):
        """Somente por ação explícita do operador, ou em concessões sintéticas de teste."""
        with connect(self.database_path) as db:
            db.execute('BEGIN IMMEDIATE')
            for key,email in self.settings.allowed_users:
                if key==COORDINATOR_KEY:
                    db.execute('''INSERT INTO coordination_accounts(account_key,nome,email_allowlist) VALUES(?,?,?)
                        ON CONFLICT(account_key) DO UPDATE SET email_allowlist=excluded.email_allowlist
                        WHERE coordination_accounts.email_allowlist!=excluded.email_allowlist''',(key,'Marcos',email))
                    continue
                row=db.execute('''SELECT mp.mission_id,p.nome,m.codigo FROM mission_participants mp
                    JOIN participants p ON p.id=mp.participant_id JOIN missions m ON m.id=mp.mission_id
                    WHERE mp.participant_id=? ORDER BY mp.mission_id LIMIT 1''',(key,)).fetchone()
                if not row: raise RuntimeError('ALLOWED_USERS contém participante inexistente ou sem missão.')
                if self.settings.google_workspace_domain==WORKSPACE_DOMAIN:
                    policy=SECCO_ACCOUNTS.get(key)
                    if not policy or (email,row['codigo'],row['nome'])!=policy:
                        raise RuntimeError('O perfil autorizado não corresponde ao participante e à missão existentes.')
                db.execute('''INSERT INTO app_users(participant_id,email_allowlist,default_mission_id) VALUES(?,?,?)
                    ON CONFLICT(participant_id) DO UPDATE SET email_allowlist=excluded.email_allowlist
                    WHERE app_users.email_allowlist!=excluded.email_allowlist''',(key,email,row['mission_id']))
            allowed_ids=[key for key,email in self.settings.allowed_users if type(key) is int]
            if allowed_ids:
                marks=','.join('?' for _ in allowed_ids)
                db.execute(f'UPDATE app_users SET enabled=0 WHERE participant_id NOT IN ({marks})',allowed_ids)
            else: db.execute('UPDATE app_users SET enabled=0')
            if not any(key==COORDINATOR_KEY for key,email in self.settings.allowed_users):
                db.execute('UPDATE coordination_accounts SET enabled=0')

    def get_user(self,user_id):
        with connect(self.database_path) as db: return self._lookup(db,user_id)

    def bind_identity(self,claims):
        email=claims['email'].strip().casefold()
        try:
            with connect(self.database_path) as db:
                db.execute('BEGIN IMMEDIATE')
                row=db.execute(USER_SQL+' WHERE u.google_sub=?',(claims['sub'],)).fetchone()
                user=self._user(row)
                if user is None:
                    user=self._user(db.execute('SELECT * FROM coordination_accounts WHERE google_sub=?',(claims['sub'],)).fetchone(),True)
                if user is None:
                    key=next((key for key,allowed_email in self.settings.allowed_users if allowed_email==email),None)
                    if key==COORDINATOR_KEY:
                        user=self._user(db.execute('SELECT * FROM coordination_accounts WHERE account_key=?',(key,)).fetchone(),True)
                    elif type(key) is int:
                        user=self._user(db.execute(USER_SQL+' WHERE u.participant_id=?',(key,)).fetchone())
                    if not user or user['google_sub'] is not None: raise IdentityDenied()
                if not user['enabled'] or (account_key(user),user['email_allowlist']) not in self.settings.allowed_users:
                    raise IdentityDenied()
                if claims.get('email_verified') is not True or claims.get('hd','').casefold()!=self.settings.google_workspace_domain:
                    raise IdentityDenied()
                table,_,identifier,_=self._location(user['id'])
                if user['email_current'] and user['email_current']!=email: self._event(db,user['id'],'email_changed')
                db.execute(f'''UPDATE {table} SET google_sub=?,email_current=?,workspace_domain=?,
                    last_login_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?''',
                    (claims['sub'],email,claims['hd'].casefold(),identifier))
                return user['id']
        except sqlite3.IntegrityError: raise IdentityDenied() from None

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

    def create_session(self,user_id,previous_token=None):
        now=self.clock()
        token,session_id,csrf=(secrets.token_urlsafe(48) for _ in range(3))
        with connect(self.database_path) as db:
            db.execute('BEGIN IMMEDIATE')
            user=self._lookup(db,user_id)
            if not user or not self.allowed(user): raise IdentityDenied()
            _,sessions,identifier,_=self._location(user_id)
            if previous_token:
                hashed=self.digest('session',previous_token)
                for table in ('user_sessions','coordination_sessions'):
                    db.execute(f'UPDATE {table} SET revoked_at=? WHERE token_hash=? OR previous_hash=?',(now,hashed,hashed))
            db.execute(f'''INSERT INTO {sessions}(id,user_id,token_hash,csrf_secret,config_hash,created_at,last_seen_at,rotated_at,expires_at)
                VALUES(?,?,?,?,?,?,?,?,?)''',(session_id,identifier,self.digest('session',token),csrf,self.config_hash(),now,now,now,now+self.settings.session_absolute_seconds))
            self._event(db,user_id,'login')
        return {'token':token,'csrf':csrf,'expires_at':now+self.settings.session_absolute_seconds}

    def resolve_session(self,token):
        if not token or len(token)>200 or not self.settings.auth_ready: return None
        now=self.clock(); hashed=self.digest('session',token)
        with connect(self.database_path) as db:
            db.execute('BEGIN IMMEDIATE')
            for table,coord in (('user_sessions',False),('coordination_sessions',True)):
                row=db.execute(f'''SELECT * FROM {table} WHERE token_hash=?
                    OR (previous_hash=? AND previous_valid_until>?)''',(hashed,hashed,now)).fetchone()
                if not row: continue
                if row['revoked_at'] is not None: return None
                user_id=COORDINATOR_PREFIX+str(row['user_id']) if coord else row['user_id']
                user=self._lookup(db,user_id)
                if (not user or not self.allowed(user) or row['expires_at']<=now
                    or row['last_seen_at']+self.settings.session_idle_seconds<=now
                    or not hmac.compare_digest(row['config_hash'],self.config_hash())):
                    db.execute(f'UPDATE {table} SET revoked_at=? WHERE id=?',(now,row['id'])); return None
                new_token=None
                if row['token_hash']==hashed and row['rotated_at']+self.settings.session_rotation_seconds<=now:
                    new_token=secrets.token_urlsafe(48)
                    db.execute(f'''UPDATE {table} SET previous_hash=token_hash,previous_valid_until=?,token_hash=?,rotated_at=? WHERE id=?''',
                        (now+30,self.digest('session',new_token),now,row['id']))
                db.execute(f'UPDATE {table} SET last_seen_at=MAX(last_seen_at,?) WHERE id=?',(now,row['id']))
                return {'user':user,'csrf':row['csrf_secret'],'new_token':new_token,'expires_at':row['expires_at']}
        return None

    def logout(self,token):
        if not token: return
        hashed=self.digest('session',token)
        with connect(self.database_path) as db:
            db.execute('BEGIN IMMEDIATE')
            for table,coord in (('user_sessions',False),('coordination_sessions',True)):
                row=db.execute(f'SELECT user_id FROM {table} WHERE token_hash=? OR previous_hash=?',(hashed,hashed)).fetchone()
                db.execute(f'UPDATE {table} SET revoked_at=? WHERE token_hash=? OR previous_hash=?',(self.clock(),hashed,hashed))
                if row: self._event(db,COORDINATOR_PREFIX+str(row[0]) if coord else row[0],'logout')

    def can_edit(self,user,mission_id):
        if not user or user.get('is_coordinator') or not self.allowed(user): return False
        with connect(self.database_path) as db:
            if self.settings.google_workspace_domain==WORKSPACE_DOMAIN:
                primary=SECCO_ACCOUNTS.get(user['participant_id'])
                mission=db.execute('SELECT codigo FROM missions WHERE id=?',(mission_id,)).fetchone()
                if not primary or not mission or mission[0]!=primary[1]: return False
            return bool(db.execute('''SELECT 1 FROM mission_participants WHERE participant_id=? AND mission_id=?
                UNION SELECT 1 FROM user_mission_permissions WHERE user_id=? AND mission_id=? AND can_edit=1''',
                (user['participant_id'],mission_id,user['id'],mission_id)).fetchone())

    def set_default(self,user_id,mission_id):
        user=self.get_user(user_id)
        if not user or user['is_coordinator']: raise IdentityDenied()
        if self.settings.google_workspace_domain==WORKSPACE_DOMAIN:
            with connect(self.database_path) as db:
                row=db.execute('SELECT codigo FROM missions WHERE id=?',(mission_id,)).fetchone()
                if not row or row[0]!=SECCO_ACCOUNTS[user['participant_id']][1]: raise IdentityDenied()
        with connect(self.database_path) as db:
            db.execute("UPDATE app_users SET default_mission_id=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",(mission_id,user_id))

    def author_names(self):
        # Coordenação nunca é projetada como participante ou autora de atividade de viajante.
        with connect(self.database_path) as db:
            return {r['id']:r['nome'] for r in db.execute('SELECT u.id,p.nome FROM app_users u JOIN participants p ON p.id=u.participant_id')}
