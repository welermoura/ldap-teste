import os
import json
import logging
from ldap3 import Server, Connection, ALL, ALL_ATTRIBUTES, MODIFY_REPLACE, MODIFY_DELETE, BASE, SUBTREE
from ldap3.utils.log import set_library_log_detail_level, EXTENDED
from cryptography.fernet import Fernet
from ldap3.utils.conv import escape_filter_chars

# Habilita o logging detalhado para a biblioteca ldap3 para depuração
set_library_log_detail_level(EXTENDED)
from datetime import datetime, timezone

# ==============================================================================
# Configuração Base
# ==============================================================================
basedir = os.path.abspath(os.path.dirname(__file__))
data_dir = os.path.join(basedir, 'data')
logs_dir = os.path.join(basedir, 'logs')
os.makedirs(data_dir, exist_ok=True)
os.makedirs(logs_dir, exist_ok=True)

CONFIG_FILE = os.path.join(data_dir, 'config.json')
KEY_FILE = os.path.join(data_dir, 'secret.key')
SCHEDULE_FILE = os.path.join(data_dir, 'schedules.json')
DISABLE_SCHEDULE_FILE = os.path.join(data_dir, 'disable_schedules.json')
GROUP_SCHEDULE_FILE = os.path.join(data_dir, 'group_schedules.json')
HISTORY_FILE = os.path.join(data_dir, 'history.json')
PERMISSIONS_FILE = os.path.join(data_dir, 'permissions.json')
USER_FILE = os.path.join(data_dir, 'user.json')
FLASK_SECRET_FILE = os.path.join(data_dir, 'flask_secret.key')

# ==============================================================================
# Funções de Criptografia e Configuração
# ==============================================================================
def write_key():
    """Gera uma chave e a salva em 'secret.key'."""
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as key_file:
        key_file.write(key)

def load_key():
    """Carrega a chave de 'secret.key'."""
    if not os.path.exists(KEY_FILE):
        write_key()
    return open(KEY_FILE, "rb").read()

def get_flask_secret_key():
    if os.path.exists(FLASK_SECRET_FILE):
        with open(FLASK_SECRET_FILE, 'r') as f:
            return f.read().strip()
    else:
        import secrets
        new_key = secrets.token_hex(32)
        with open(FLASK_SECRET_FILE, 'w') as f:
            f.write(new_key)
        os.chmod(FLASK_SECRET_FILE, 0o600)
        return new_key

key = load_key()
cipher_suite = Fernet(key)

SENSITIVE_KEYS = ['DEFAULT_PASSWORD', 'SERVICE_ACCOUNT_PASSWORD', 'ZIMBRA_ADMIN_PASSWORD', 'DB_PASSWORD', 'SQL_SERVER_URI', 'TEAMS_CLIENT_SECRET', 'ZIMBRA_SECURITY_DEFAULT_PASSWORD', 'TEAMS_USER_PASSWORD']

def get_sql_server_uri():
    # Priority 1: Environment variable
    env_uri = os.environ.get('SQL_SERVER_URI')
    if env_uri:
        return env_uri
    # Priority 2: Config file (config.json)
    try:
        config = load_config(force_reload=True)
        if config.get('USE_SQL_SERVER') and config.get('SQL_SERVER_URI'):
            return config.get('SQL_SERVER_URI')
    except Exception:
        pass
    return None

BOOTSTRAP_KEYS = ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD', 'SQL_SERVER_URI', 'USE_SQL_SERVER']

def load_config(force_reload=False):
    """Carrega, descriptografa e retorna os dados de configuração de forma híbrida (bootstrap local + banco SQL Server)."""
    # 1. Carrega as configurações locais do config.json (Bootstrap)
    local_config = {}
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                encrypted_config = json.load(f)
            for k, v in encrypted_config.items():
                if k in SENSITIVE_KEYS and v:
                    try:
                        local_config[k] = cipher_suite.decrypt(v.encode()).decode()
                    except Exception:
                        local_config[k] = v
                else:
                    local_config[k] = v
    except Exception:
        pass

    # 2. Se o SQL Server estiver ativo e houver um contexto Flask ativo com SQLAlchemy inicializado, carrega as configurações do banco
    from flask import has_app_context, current_app
    if has_app_context() and current_app and 'sqlalchemy' in current_app.extensions and local_config.get('USE_SQL_SERVER') and local_config.get('SQL_SERVER_URI'):
        try:
            from models import ConfigSetting, ensure_db_registered
            ensure_db_registered()
            db_settings = ConfigSetting.query.all()
            db_config = {}
            for s in db_settings:
                k, v = s.key, s.value
                if k in SENSITIVE_KEYS and v:
                    try:
                        db_config[k] = cipher_suite.decrypt(v.encode()).decode()
                    except Exception:
                        db_config[k] = v
                else:
                    db_config[k] = v
            
            # Mescla: as chaves locais de bootstrap têm prioridade, e as outras vêm do banco
            merged_config = {**local_config}
            for k, v in db_config.items():
                if k not in BOOTSTRAP_KEYS:
                    merged_config[k] = v
            return merged_config
        except Exception as e:
            logging.error(f"[DB] Erro ao carregar configurações da tabela ConfigSetting: {e}")

    return local_config


def save_config(config):
    """Criptografa e salva os dados de configuração de forma híbrida (disco local + SQL Server)."""
    # 1. Separa as configurações locais de bootstrap e as demais
    local_to_save = {}
    db_to_save = {}
    
    for k, v in config.items():
        if k in BOOTSTRAP_KEYS:
            local_to_save[k] = v
        else:
            local_to_save[k] = v  # Mantém no local por segurança/redundância e fallback
            db_to_save[k] = v

    # 2. Grava no config.json local (criptografado)
    encrypted_local = {}
    for k, v in local_to_save.items():
        if k in SENSITIVE_KEYS and v:
            encrypted_local[k] = cipher_suite.encrypt(v.encode()).decode()
        else:
            encrypted_local[k] = v

    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(encrypted_local, f, indent=4)
    except Exception as e:
        logging.error(f"Erro ao salvar arquivo config.json local: {e}")

    # 3. Grava no SQL Server se ativo
    if config.get('USE_SQL_SERVER') and config.get('SQL_SERVER_URI'):
        try:
            from models import db, ConfigSetting, ensure_db_registered
            ensure_db_registered()
            
            for k, v in db_to_save.items():
                v_str = str(v) if v is not None else ''
                if k in SENSITIVE_KEYS and v_str:
                    v_str = cipher_suite.encrypt(v_str.encode()).decode()
                
                setting = ConfigSetting.query.filter_by(key=k).first()
                if setting:
                    setting.value = v_str
                else:
                    setting = ConfigSetting(key=k, value=v_str)
                    db.session.add(setting)
            
            db.session.commit()
        except Exception as e:
            logging.error(f"[DB] Erro ao salvar configurações na tabela ConfigSetting: {e}")
            db.session.rollback()

def get_ad_upn_suffixes(conn):
    """Busca automaticamente os sufixos UPN configurados no Active Directory."""
    try:
        # Tenta pegar direto do Server Info (mais rápido e seguro)
        config_nc = None
        if conn.server and conn.server.info:
            config_nc = conn.server.info.other.get('configurationNamingContext')
            if isinstance(config_nc, list): config_nc = config_nc[0]

        if not config_nc:
            # Fallback para busca manual do RootDSE
            conn.search('', '(objectClass=*)', search_scope=BASE, attributes=['configurationNamingContext'])
            if conn.entries:
                config_nc = conn.entries[0].configurationNamingContext.value
        
        if not config_nc:
            logging.warning("Não foi possível localizar o configurationNamingContext.")
            return []
        
        # Busca os sufixos em CN=Partitions (o container e seus filhos)
        partitions_dn = f"CN=Partitions,{config_nc}"
        
        # Busca no container (sufixos da floresta) e nos objetos crossRef (domínios/partições)
        conn.search(partitions_dn, '(|(objectClass=crossRef)(objectClass=crossRefContainer))', search_scope=SUBTREE, attributes=['uPNSuffixes', 'dnsRoot', 'cn'])
        
        suffixes = set()
        logging.info(f"Busca em {partitions_dn} retornou {len(conn.entries)} entradas de partições.")
        for entry in conn.entries:
            # uPNSuffixes é uma lista de sufixos adicionais
            if 'uPNSuffixes' in entry and entry.uPNSuffixes.value:
                vals = entry.uPNSuffixes.value
                if isinstance(vals, list):
                    for v in vals:
                        if v: suffixes.add('@' + str(v).lstrip('@'))
                else:
                    suffixes.add('@' + str(vals).lstrip('@'))
            
            # dnsRoot costuma ser o sufixo principal do domínio/partição
            if 'dnsRoot' in entry and entry.dnsRoot.value:
                dns_root = str(entry.dnsRoot.value).lower()
                # Filtrar zonas de DNS internas que geralmente não são UPNs reais
                if not dns_root.startswith(('domaindnszones', 'forestdnszones')):
                    suffixes.add('@' + dns_root.lstrip('@'))
        
        logging.info(f"Sufixos detectados: {suffixes}")
        return sorted(list(suffixes))
    except Exception as e:
        logging.error(f"Erro ao buscar sufixos UPN do AD: {e}")
        return []

# ==============================================================================
# Funções de Dados (JSON)
# ==============================================================================
def load_permissions():
    sql_server_uri = get_sql_server_uri()
    if sql_server_uri:
        try:
            from models import Permission, ensure_db_registered
            ensure_db_registered()
            perms = Permission.query.all()
            result = {}
            for p in perms:
                # Normaliza para garantir que actions e views sejam sempre dicionários
                # mesmo que tenham sido gravados ou seedados como listas vazias []
                loaded_actions = json.loads(p.actions) if p.actions else {}
                if isinstance(loaded_actions, list):
                    loaded_actions = {}
                loaded_views = json.loads(p.views) if hasattr(p, 'views') and p.views else {}
                if isinstance(loaded_views, list):
                    loaded_views = {}
                loaded_fields = json.loads(p.fields) if hasattr(p, 'fields') and p.fields else []
                if not isinstance(loaded_fields, list):
                    loaded_fields = []

                result[p.group_name] = {
                    'type': p.type,
                    'allowed_ous': json.loads(p.allowed_ous) if p.allowed_ous else [],
                    'actions': loaded_actions,
                    'views': loaded_views,
                    'fields': loaded_fields
                }
            return result
        except Exception as e:
            logging.error(f"[DB] Error loading permissions: {e}")
            
    try:
        with open(PERMISSIONS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Normaliza fallback local JSON
            for k, v in data.items():
                if 'actions' not in v or isinstance(v['actions'], list):
                    v['actions'] = {}
                if 'views' not in v or isinstance(v['views'], list):
                    v['views'] = {}
                if 'fields' not in v or not isinstance(v['fields'], list):
                    v['fields'] = []
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_permissions(permissions):
    sql_server_uri = get_sql_server_uri()
    if sql_server_uri:
        try:
            from models import db, Permission, ensure_db_registered
            ensure_db_registered()
            existing_names = set(permissions.keys())
            db_perms = Permission.query.all()
            for db_p in db_perms:
                if db_p.group_name not in existing_names:
                    db.session.delete(db_p)
            for k, v in permissions.items():
                allowed_ous_str = json.dumps(v.get('allowed_ous', []))
                actions_str = json.dumps(v.get('actions', {}))
                views_str = json.dumps(v.get('views', {}))
                fields_str = json.dumps(v.get('fields', []))
                perm = Permission.query.filter_by(group_name=k).first()
                if perm:
                    perm.type = v.get('type', 'none')
                    perm.allowed_ous = allowed_ous_str
                    perm.actions = actions_str
                    perm.views = views_str
                    perm.fields = fields_str
                else:
                    perm = Permission(
                        group_name=k,
                        type=v.get('type', 'none'),
                        allowed_ous=allowed_ous_str,
                        actions=actions_str,
                        views=views_str,
                        fields=fields_str
                    )
                    db.session.add(perm)
            db.session.commit()
            return
        except Exception as e:
            logging.error(f"[DB] Error saving permissions: {e}")
            db.session.rollback()

    with open(PERMISSIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(permissions, f, indent=4)

def load_user():
    try:
        if not os.path.exists(USER_FILE):
            return None
        with open(USER_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

def save_user(users):
    with open(USER_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=4)

def load_schedules():
    sql_server_uri = get_sql_server_uri()
    if sql_server_uri:
        try:
            from models import Schedule, ensure_db_registered
            ensure_db_registered()
            scheds = Schedule.query.all()
            return {s.username: s.reactivation_date for s in scheds}
        except Exception as e:
            logging.error(f"[DB] Error loading schedules: {e}")
            
    try:
        with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_schedules(schedules):
    sql_server_uri = get_sql_server_uri()
    if sql_server_uri:
        try:
            from models import db, Schedule, ensure_db_registered
            ensure_db_registered()
            existing_usernames = set(schedules.keys())
            db_scheds = Schedule.query.all()
            for db_s in db_scheds:
                if db_s.username not in existing_usernames:
                    db.session.delete(db_s)
            for username, reactivation_date in schedules.items():
                sched = Schedule.query.filter_by(username=username).first()
                if sched:
                    sched.reactivation_date = reactivation_date
                else:
                    sched = Schedule(username=username, reactivation_date=reactivation_date)
                    db.session.add(sched)
            db.session.commit()
            return
        except Exception as e:
            logging.error(f"[DB] Error saving schedules: {e}")
            db.session.rollback()

    with open(SCHEDULE_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedules, f, indent=4)

def load_disable_schedules():
    sql_server_uri = get_sql_server_uri()
    if sql_server_uri:
        try:
            from models import DisableSchedule, ensure_db_registered
            ensure_db_registered()
            scheds = DisableSchedule.query.all()
            return {s.username: s.deactivation_date for s in scheds}
        except Exception as e:
            logging.error(f"[DB] Error loading disable schedules: {e}")
            
    try:
        with open(DISABLE_SCHEDULE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_disable_schedules(schedules):
    sql_server_uri = get_sql_server_uri()
    if sql_server_uri:
        try:
            from models import db, DisableSchedule, ensure_db_registered
            ensure_db_registered()
            existing_usernames = set(schedules.keys())
            db_scheds = DisableSchedule.query.all()
            for db_s in db_scheds:
                if db_s.username not in existing_usernames:
                    db.session.delete(db_s)
            for username, deactivation_date in schedules.items():
                sched = DisableSchedule.query.filter_by(username=username).first()
                if sched:
                    sched.deactivation_date = deactivation_date
                else:
                    sched = DisableSchedule(username=username, deactivation_date=deactivation_date)
                    db.session.add(sched)
            db.session.commit()
            return
        except Exception as e:
            logging.error(f"[DB] Error saving disable schedules: {e}")
            db.session.rollback()

    with open(DISABLE_SCHEDULE_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedules, f, indent=4)

def load_group_schedules():
    sql_server_uri = get_sql_server_uri()
    if sql_server_uri:
        try:
            from models import GroupSchedule, ensure_db_registered
            ensure_db_registered()
            scheds = GroupSchedule.query.all()
            return [{
                'group_dn': s.group_dn,
                'target_mail': s.target_mail,
                'sync_type': s.sync_type,
                'active': s.active
            } for s in scheds]
        except Exception as e:
            logging.error(f"[DB] Error loading group schedules: {e}")
            
    try:
        with open(GROUP_SCHEDULE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_group_schedules(schedules):
    sql_server_uri = get_sql_server_uri()
    if sql_server_uri:
        try:
            from models import db, GroupSchedule, ensure_db_registered
            ensure_db_registered()
            existing_group_dns = {item.get('group_dn') for item in schedules}
            db_scheds = GroupSchedule.query.all()
            for db_s in db_scheds:
                if db_s.group_dn not in existing_group_dns:
                    db.session.delete(db_s)
            for item in schedules:
                group_dn = item.get('group_dn')
                sched = GroupSchedule.query.filter_by(group_dn=group_dn).first()
                if sched:
                    sched.target_mail = item.get('target_mail')
                    sched.sync_type = item.get('sync_type', 'zimbra')
                    sched.active = item.get('active', True)
                else:
                    sched = GroupSchedule(
                        group_dn=group_dn,
                        target_mail=item.get('target_mail'),
                        sync_type=item.get('sync_type', 'zimbra'),
                        active=item.get('active', True)
                    )
                    db.session.add(sched)
            db.session.commit()
            return
        except Exception as e:
            logging.error(f"[DB] Error saving group schedules: {e}")
            db.session.rollback()

    with open(GROUP_SCHEDULE_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedules, f, indent=4)

def load_admin_users():
    sql_server_uri = get_sql_server_uri()
    if sql_server_uri:
        try:
            from models import AdminUser, ensure_db_registered
            ensure_db_registered()
            users = AdminUser.query.filter_by(active=True).all()
            return {u.username: u.password_hash for u in users}
        except Exception as e:
            logging.error(f"[DB] Error loading admin users: {e}")
            
    basedir = os.path.abspath(os.path.dirname(__file__))
    data_dir = os.path.join(basedir, 'data')
    users_file = os.path.join(data_dir, 'users.json')
    admins = {}
    if os.path.exists(users_file):
        try:
            with open(users_file, 'r') as f:
                admins = json.load(f)
        except Exception:
            pass
    if not admins:
        old_admin = load_user()
        if old_admin:
            admins[old_admin['username']] = old_admin['password_hash']
            try:
                with open(users_file, 'w') as f:
                    json.dump(admins, f)
            except Exception:
                pass
    return admins

def save_admin_users(admins):
    sql_server_uri = get_sql_server_uri()
    if sql_server_uri:
        try:
            from models import db, AdminUser, ensure_db_registered
            ensure_db_registered()
            existing_usernames = set(admins.keys())
            db_users = AdminUser.query.all()
            for db_u in db_users:
                if db_u.username not in existing_usernames:
                    db.session.delete(db_u)
            for username, password_hash in admins.items():
                admin_user = AdminUser.query.filter_by(username=username).first()
                if admin_user:
                    admin_user.password_hash = password_hash
                    admin_user.active = True
                else:
                    admin_user = AdminUser(
                        username=username,
                        password_hash=password_hash,
                        display_name=username.capitalize(),
                        active=True
                    )
                    db.session.add(admin_user)
            db.session.commit()
            return
        except Exception as e:
            logging.error(f"[DB] Error saving admin users: {e}")
            db.session.rollback()

    basedir = os.path.abspath(os.path.dirname(__file__))
    data_dir = os.path.join(basedir, 'data')
    users_file = os.path.join(data_dir, 'users.json')
    with open(users_file, 'w') as f:
        json.dump(admins, f, indent=4)

# ==============================================================================
# Utilitários de AD e Acesso
# ==============================================================================
def get_user_access_level(user_groups):
    """
    Determina o nível de acesso mais alto de um usuário com base em seus grupos.
    Retorna 'full', 'custom', ou 'none'.
    A ordem de precedência é: full > custom > none.
    """
    permissions = load_permissions()
    if not permissions or not user_groups:
        return 'none'
    
    access_levels = set()
    for group in user_groups:
        group_norm = group.strip()
        rule = permissions.get(group_norm)
        if not rule:
            # Fallback case-insensitive
            for p_key, p_val in permissions.items():
                if p_key.lower() == group_norm.lower():
                    rule = p_val
                    break
        
        if rule:
            access_levels.add(rule.get('type', 'none'))

    if 'full' in access_levels:
        return 'full'
    if 'custom' in access_levels:
        return 'custom'
    return 'none'

def get_attr_value(user, attr):
    """Retorna o valor de um atributo do usuário com segurança."""
    if attr in user and user[attr].value is not None:
        return user[attr].value
    return ''

def validate_sam_account(field_data):
    """Valida se o sAMAccountName contém apenas caracteres permitidos."""
    if not all(c.isalnum() or c in '.-_' for c in field_data):
        return False
    return True

def format_phone_number(phone_str):
    """Formata um número de telefone para o padrão XX XXXX-XXXX."""
    import re
    if not phone_str:
        return ""
    digits = re.sub(r'\D', '', phone_str)
    if len(digits) > 10:
        digits = digits[-10:]
    if len(digits) == 10:
        return f"{digits[0:2]} {digits[2:6]}-{digits[6:10]}"
    return phone_str

# ==============================================================================
# Funções de Conexão e Lógica AD
# ==============================================================================
def get_ldap_connection(user=None, password=None, read_only=False):
    """
    Cria uma conexão LDAP de forma robusta. 
    Para conta de serviço, tenta Kerberos/SASL e faz fallback para simples.
    """
    config = load_config()
    ad_server = config.get('AD_SERVER')
    use_ldaps = config.get('USE_LDAPS', False)
    
    if not ad_server:
        raise Exception("Servidor AD não configurado.")

    try:
        tls_config = None
        if use_ldaps:
            cert_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'ca_raiz.cer')
            if os.path.exists(cert_path):
                import ssl
                from ldap3 import Tls
                try:
                    # Resolve os nomes válidos para a validação do certificado (ad_server e FQDN)
                    valid_names = [ad_server]
                    search_base = config.get('AD_SEARCH_BASE', '')
                    if search_base:
                        try:
                            domain_parts = [part.strip().split('=')[1] for part in search_base.split(',') if part.strip().lower().startswith('dc=')]
                            if domain_parts:
                                domain_name = '.'.join(domain_parts)
                                if domain_name not in valid_names:
                                    valid_names.append(domain_name)
                                    valid_names.append(f"*.{domain_name}")
                                if '.' not in ad_server:
                                    fqdn = f"{ad_server}.{domain_name}"
                                    if fqdn not in valid_names:
                                        valid_names.append(fqdn)
                                else:
                                    # Se for IP (como 10.10.1.41), adicionamos nomes conhecidos comuns no certificado do AD
                                    valid_names.append(f"DSMTZDC04.{domain_name}")
                                    valid_names.append("DSMTZDC04")
                        except Exception:
                            pass
                    
                    tls_config = Tls(
                        validate=ssl.CERT_REQUIRED,
                        version=ssl.PROTOCOL_TLSv1_2,
                        ca_certs_file=cert_path,
                        valid_names=valid_names
                    )
                    logging.info(f"[LDAP] Conectando via LDAPS com validação de certificado CA: {cert_path} (Nomes válidos: {valid_names})")
                except Exception as e_tls:
                    logging.error(f"[LDAP] Erro ao configurar Tls com certificado CA: {e_tls}")
            else:
                logging.warning("[LDAP] LDAPS está ativo, mas nenhum certificado CA foi configurado em /app/data/ca_raiz.cer. Conectando sem validação (inseguro).")

        server = Server(ad_server, use_ssl=use_ldaps, tls=tls_config, get_info=ALL, connect_timeout=5)
        
        # Caso 1: Login de Usuário (Sempre Simples)
        if user and password:
            logging.debug(f"Autenticação simples para usuário: {user}")
            try:
                return Connection(server, user=user, password=password, auto_bind=True, receive_timeout=10, read_only=read_only)
            except Exception as e_bind:
                if use_ldaps and tls_config and ("invalid server address" in str(e_bind) or "certificate verify" in str(e_bind) or "verify failed" in str(e_bind)):
                    logging.warning(f"[LDAP] Erro de validação de SSL ({e_bind}). Tentando fallback para CERT_NONE...")
                    import ssl as local_ssl
                    from ldap3 import Tls as fallback_Tls
                    fallback_tls = fallback_Tls(validate=local_ssl.CERT_NONE, version=local_ssl.PROTOCOL_TLSv1_2)
                    fallback_server = Server(ad_server, use_ssl=True, tls=fallback_tls, get_info=ALL, connect_timeout=5)
                    return Connection(fallback_server, user=user, password=password, auto_bind=True, receive_timeout=10, read_only=read_only)
                raise

        # Caso 2: Conta de Serviço
        service_user = config.get('SERVICE_ACCOUNT_USER')
        service_password = config.get('SERVICE_ACCOUNT_PASSWORD')
        
        if not service_user or not service_password:
            raise Exception("Conta de serviço não configurada.")

        # Tenta Kerberos se disponível (requer libs do sistema)
        try:
            try:
                logging.debug("Tentando SASL/GSSAPI (Kerberos)...")
                return Connection(server, user=service_user, password=service_password,
                                  authentication='SASL', sasl_mechanism='GSSAPI',
                                  auto_bind=True, receive_timeout=15, read_only=read_only)
            except Exception as e_sasl:
                logging.debug(f"SASL falhou: {e_sasl}. Usando Simples...")
                return Connection(server, user=service_user, password=service_password, 
                                  auto_bind=True, receive_timeout=15, read_only=read_only)
        except Exception as e_bind:
            if use_ldaps and tls_config and ("invalid server address" in str(e_bind) or "certificate verify" in str(e_bind) or "verify failed" in str(e_bind)):
                logging.warning(f"[LDAP] Erro de validação de SSL ({e_bind}). Tentando fallback para CERT_NONE...")
                import ssl as local_ssl
                from ldap3 import Tls as fallback_Tls
                fallback_tls = fallback_Tls(validate=local_ssl.CERT_NONE, version=local_ssl.PROTOCOL_TLSv1_2)
                fallback_server = Server(ad_server, use_ssl=True, tls=fallback_tls, get_info=ALL, connect_timeout=5)
                try:
                    logging.debug("Tentando SASL/GSSAPI (Kerberos) com CERT_NONE...")
                    return Connection(fallback_server, user=service_user, password=service_password,
                                      authentication='SASL', sasl_mechanism='GSSAPI',
                                      auto_bind=True, receive_timeout=15, read_only=read_only)
                except Exception as e_sasl:
                    logging.debug(f"SASL falhou com CERT_NONE: {e_sasl}. Usando Simples...")
                    return Connection(fallback_server, user=service_user, password=service_password, 
                                      auto_bind=True, receive_timeout=15, read_only=read_only)
            raise

    except Exception as e:
        logging.error(f"Erro crítico de conexão LDAP: {e}")
        raise

def get_service_account_connection():
    """Atalho para obter a conexão da conta de serviço com reuso por requisição."""
    from flask import has_app_context, g
    if has_app_context():
        if 'service_conn' not in g:
            g.service_conn = get_ldap_connection()
        return g.service_conn
    return get_ldap_connection()

# Alias para compatibilidade
get_ad_connection = get_ldap_connection

def is_recycle_bin_enabled(conn):
    """Verifica se a Lixeira do Active Directory está habilitada."""
    if not conn or not conn.bound:
        return False
    try:
        # O DN da funcionalidade da lixeira é construído a partir do sufixo do domínio (rootDSE)
        domain_dn = conn.server.info.other.get('defaultNamingContext')[0]
        config_dn = conn.server.info.other.get('configurationNamingContext')[0]

        search_base = f"CN=Optional Features,CN=Directory Service,CN=Windows NT,CN=Services,{config_dn}"
        search_filter = "(cn=Recycle Bin Feature)"

        conn.search(search_base, search_filter, attributes=['cn'])

        return bool(conn.entries)
    except Exception as e:
        logging.error(f"Erro ao verificar o status da Lixeira do AD: {e}")
        return False

def get_user_by_samaccountname(conn, sam_account_name, attributes=None, controls=None):
    if attributes is None:
        attributes = ALL_ATTRIBUTES
    config = load_config()
    search_base = config.get('AD_SEARCH_BASE')
    if not search_base:
        if conn.server.info and conn.server.info.other:
            search_base = conn.server.info.other['defaultNamingContext'][0]
        else:
            raise Exception("AD_SEARCH_BASE não configurado e informações do servidor indisponíveis.")
            
    conn.search(search_base, f'(sAMAccountName={sam_account_name})', attributes=attributes, controls=controls)
    if conn.entries:
        return conn.entries[0]
    return None

def create_ad_user(conn, form_data, model_attrs):
    from flask import session
    from routes.utils import get_ou_from_dn, get_ou_path
    config = load_config()
    first_name = form_data['first_name']
    last_name = form_data['last_name']
    sam = form_data['sam_account']

    # Tenta usar o sufixo UPN fornecido no formulário, caso contrário, deriva da base de busca
    upn_suffix = form_data.get('upn_suffix')
    if not upn_suffix:
        def _get_upn_suffix(search_base):
            dc_parts = [part.split('=')[1] for part in search_base.split(',') if part.strip().upper().startswith('DC=')]
            return '@' + '.'.join(dc_parts) if dc_parts else None
        
        upn_suffix = _get_upn_suffix(config.get('AD_SEARCH_BASE', ''))
    
    if not upn_suffix:
        return {'success': False, 'message': "Erro: Não foi possível determinar o Sufixo UPN."}

    upn = f"{sam}{upn_suffix}"
    last_name_part = last_name.split()[-1] if last_name else ""
    display_name = f"{first_name} {last_name_part}"
    initials = ''.join([p[0].upper() for p in (first_name + " " + last_name).split() if p])
    ou_dn = get_ou_from_dn(model_attrs.entry_dn)
    
    try:
        if get_user_by_samaccountname(conn, sam):
            return {'success': False, 'message': f"Erro: O login '{sam}' já existe no AD."}

        safe_display_name = escape_filter_chars(display_name)
        conn.search(ou_dn, f'(&(objectClass=user)(cn={safe_display_name}))', attributes=['cn'])
        if conn.entries:
            return {'success': False, 'message': f"Erro: Já existe um usuário com o nome '{display_name}' nesta OU."}
    except Exception as e:
        return {'success': False, 'message': f"Erro durante a verificação: {str(e)}"}

    email_domain = upn_suffix.lstrip('@')
    email = normalize_email(f"{first_name}.{last_name_part}@{email_domain}")

    user_attributes = {
        'samAccountName': sam, 'userPrincipalName': upn, 'givenName': first_name, 
        'sn': last_name, 'displayName': display_name, 'name': display_name, 
        'mail': email, 'initials': initials, 'extensionAttribute4': form_data.get('matricula', ''),
        'proxyAddresses': [f'SMTP:{email}']
    }
    
    model_attributes_to_copy = [
        'title', 'department', 'company', 'description', 'manager', 
        'physicalDeliveryOfficeName', 'streetAddress', 'l', 'st', 'postalCode', 
        'c', 'telephoneNumber', 'homePhone', 'wWWHomePage', 'postOfficeBox', 
        'pager', 'mobile', 'facsimileTelephoneNumber'
    ]
    for attr in model_attributes_to_copy:
        if attr in model_attrs and model_attrs[attr]:
            user_attributes[attr] = str(model_attrs[attr])

    if form_data.get('telephone'):
        formatted_phone = format_phone_number(form_data['telephone'])
        user_attributes['telephoneNumber'] = formatted_phone
        user_attributes['homePhone'] = formatted_phone

    try:
        user_dn = f"CN={display_name},{ou_dn}"
        conn.add(user_dn, ['user'], user_attributes)
        if not conn.result['description'] == 'success':
            raise Exception(f"Erro ao adicionar usuário: {conn.result['message']}")

        default_password = config.get('DEFAULT_PASSWORD')
        if not default_password:
             return {'success': False, 'message': "Erro: A senha padrão não está configurada."}

        conn.extend.microsoft.modify_password(user_dn, default_password)
        conn.modify(user_dn, {'userAccountControl': [(MODIFY_REPLACE, [512])], 'pwdLastSet': [(MODIFY_REPLACE, [0])]})
        
        if 'memberOf' in model_attrs and model_attrs.memberOf:
            conn.extend.microsoft.add_members_to_groups(user_dn, [str(g) for g in model_attrs.memberOf])
            
        logging.info(f"[CRIAÇÃO] Usuário '{display_name}' ({sam}) foi criado por '{session.get('user_display_name', session.get('ad_user', 'System'))}'.")
        save_to_history('creation', sam, f"Criado por {session.get('user_display_name', 'System')}")
        return {
            'success': True, 'message': f"Usuário '{display_name}' criado com sucesso!", 
            'email': email, 'sam_account': sam, 'password': default_password,
            'display_name': display_name, 'initials': initials, 'ou_path': get_ou_path(model_attrs.entry_dn)
        }
    except Exception as e:
        logging.error(f"Erro ao criar o usuário '{display_name}' por '{session.get('user_display_name', session.get('ad_user', 'System'))}': {e}")
        try:
            conn.delete(user_dn)
        except:
            pass
        return {'success': False, 'message': f"Erro ao criar usuário: {str(e)}"}


def search_groups_for_user_addition(conn, query, username):
    """
    Busca grupos no AD para adicionar um usuário, excluindo os grupos dos quais o usuário já é membro.
    Retorna uma lista de dicionários, cada um contendo 'cn' e 'description' do grupo.
    """
    try:
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE')

        # 1. Obter os grupos atuais do usuário para exclusão posterior
        user = get_user_by_samaccountname(conn, username, attributes=['memberOf'])
        if not user:
            # Se o usuário não for encontrado, retorna uma lista vazia, pois não é possível determinar a associação.
            return []

        current_user_groups_dns = set(user.memberOf.values) if 'memberOf' in user and user.memberOf.values else set()

        # 2. Buscar todos os grupos que correspondem à query
        search_filter = f"(&(objectClass=group)(|(cn=*{escape_filter_chars(query)}*)(sAMAccountName=*{escape_filter_chars(query)}*)))"
        conn.search(search_base, search_filter, attributes=['cn', 'sAMAccountName', 'description', 'distinguishedName'])

        # 3. Filtrar os resultados para excluir aqueles dos quais o usuário já é membro
        groups_not_member_of = []
        for group in conn.entries:
            if group.distinguishedName.value not in current_user_groups_dns:
                groups_not_member_of.append({
                    'cn': group.cn.value if 'cn' in group else '',
                    'sAMAccountName': group.sAMAccountName.value if 'sAMAccountName' in group else (group.cn.value if 'cn' in group else ''),
                    'description': group.description.value if 'description' in group else 'N/A'
                })

        return sorted(groups_not_member_of, key=lambda g: g['cn'].lower())

    except Exception as e:
        # Loga o erro para depuração
        # Supondo que 'logging' está configurado no módulo que chama esta função
        # logging.error(f"Erro ao buscar grupos para adição do usuário '{username}': {e}", exc_info=True)
        # Retorna uma lista vazia em caso de erro para não quebrar a API
        return []

def filetime_to_datetime(ft):
    """Converts a Microsoft FILETIME timestamp to a Python datetime object."""
    EPOCH_AS_FILETIME = 116444736000000000
    HUNDREDS_OF_NANOSECONDS = 10000000
    if ft is None or int(ft) == 0 or int(ft) == 9223372036854775807:
        return None
    return datetime.fromtimestamp((int(ft) - EPOCH_AS_FILETIME) / HUNDREDS_OF_NANOSECONDS, tz=timezone.utc)

def get_group_by_name(conn, group_name, attributes=None):
    if attributes is None:
        attributes = ALL_ATTRIBUTES
    config = load_config()
    search_base = config.get('AD_SEARCH_BASE', conn.server.info.other['defaultNamingContext'][0])
    
    # 1. Tenta buscar por sAMAccountName (único e preciso)
    conn.search(search_base, f'(&(objectClass=group)(sAMAccountName={group_name}))', attributes=attributes)
    if conn.entries:
        return conn.entries[0]
        
    # 2. Fallback para cn (compatibilidade)
    conn.search(search_base, f'(&(objectClass=group)(cn={group_name}))', attributes=attributes)
    if conn.entries:
        return conn.entries[0]
        
    return None

def save_to_history(action, user_sam, details=""):
    """Salva uma ação executada no histórico (SQL ou JSON)."""
    sql_server_uri = get_sql_server_uri()
    if sql_server_uri:
        try:
            from models import db, HistoryLog, ensure_db_registered
            ensure_db_registered()
            log = HistoryLog(
                timestamp=datetime.now(),
                action=action,
                user_sam=user_sam,
                details=details
            )
            db.session.add(log)
            db.session.commit()
            return
        except Exception as e:
            logging.error(f"[DB] Error saving history log: {e}")
            db.session.rollback()

    try:
        history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        
        entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'user_sam': user_sam,
            'details': details
        }
        history.append(entry)
        
        if len(history) > 1000:
            history = history[-1000:]
            
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4)
    except Exception as e:
        logging.error(f"Erro ao salvar histórico: {e}")

def load_history():
    """Carrega o histórico de ações (SQL ou JSON)."""
    sql_server_uri = get_sql_server_uri()
    if sql_server_uri:
        try:
            from models import HistoryLog, ensure_db_registered
            ensure_db_registered()
            logs = HistoryLog.query.order_by(HistoryLog.timestamp.desc()).limit(1000).all()
            return [{
                'timestamp': l.timestamp.isoformat(),
                'action': l.action,
                'user_sam': l.user_sam,
                'details': l.details
            } for l in logs]
        except Exception as e:
            logging.error(f"[DB] Error loading history logs: {e}")
            
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
                history.reverse()
                return history
    except (json.JSONDecodeError, IOError):
        pass
    return []

import unicodedata

def normalize_email(email):
    """Normaliza o e-mail removendo acentos/diacríticos e convertendo para minúsculas.
    
    Evita erros de sintaxe em integrações como a API SOAP do Zimbra.
    """
    if not email:
        return email
    try:
        # Decompõe caracteres acentuados (ex: 'ã' vira 'a' + til unicode)
        normalized = unicodedata.normalize('NFD', email.strip().lower())
        # Codifica para ASCII ignorando caracteres não-ASCII (remove acentos), decodifica de volta
        return normalized.encode('ascii', 'ignore').decode('ascii')
    except Exception:
        return email.strip().lower()

def get_group_members_emails(conn, group_dn):
    """Busca direta e normalizada dos e-mails dos membros de um grupo do AD.
    
    Realiza apenas uma busca simples e direta no atributo 'member' do grupo,
    sem recursão em grupos aninhados e sem filtro de contas desativadas.
    """
    emails = set()
    try:
        conn.search(group_dn, '(objectClass=*)', attributes=['member'])
        if conn.entries:
            group_entry = conn.entries[0]
            member_dns = group_entry.member.values if 'member' in group_entry and group_entry.member.values else []
            for dn in member_dns:
                conn.search(dn, '(objectClass=*)', attributes=['mail', 'userPrincipalName'])
                if conn.entries:
                    entry = conn.entries[0]
                    email = get_attr_value(entry, 'userPrincipalName') or get_attr_value(entry, 'mail')
                    if email:
                        normalized = normalize_email(email)
                        if normalized:
                            emails.add(normalized)
    except Exception as e:
        logging.error(f"[LDAP] Erro ao buscar membros do grupo '{group_dn}': {e}")
    return emails


def get_group_members_identities(conn, group_dn):
    """Busca os membros de um grupo do AD e retorna suas identidades completas.
    
    Retorna uma lista de dicionários contendo:
    - 'dn': distinguishedName
    - 'primary_email': E-mail principal (mail ou userPrincipalName, normalizado)
    - 'all_emails': Conjunto contendo mail, UPN e proxyAddresses (normalizados)
    """
    members = []
    try:
        conn.search(group_dn, '(objectClass=*)', attributes=['member'])
        if conn.entries:
            group_entry = conn.entries[0]
            member_dns = group_entry.member.values if 'member' in group_entry and group_entry.member.values else []
            for dn in member_dns:
                conn.search(dn, '(objectClass=*)', attributes=['mail', 'userPrincipalName', 'proxyAddresses'])
                if conn.entries:
                    entry = conn.entries[0]
                    primary_email = get_attr_value(entry, 'mail') or get_attr_value(entry, 'userPrincipalName')
                    primary_normalized = normalize_email(primary_email) if primary_email else None
                    
                    all_emails = set()
                    if primary_normalized:
                        all_emails.add(primary_normalized)
                    
                    upn = get_attr_value(entry, 'userPrincipalName')
                    upn_normalized = normalize_email(upn) if upn else None
                    if upn_normalized:
                        all_emails.add(upn_normalized)
                        
                    proxy_vals = entry.proxyAddresses.values if 'proxyAddresses' in entry and entry.proxyAddresses.values else []
                    for addr in proxy_vals:
                        addr_str = str(addr).strip().lower()
                        if addr_str.startswith('smtp:'):
                            addr_str = addr_str[5:]
                        normalized_proxy = normalize_email(addr_str)
                        if normalized_proxy:
                            all_emails.add(normalized_proxy)
                            
                    members.append({
                        'dn': dn,
                        'primary_email': primary_normalized,
                        'all_emails': all_emails
                    })
    except Exception as e:
        logging.error(f"[LDAP] Erro ao buscar identidades dos membros do grupo '{group_dn}': {e}")
    return members



