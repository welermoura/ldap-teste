import os
import json
import logging
from ldap3 import Server, Connection, ALL
from ldap3.utils.log import set_library_log_detail_level, EXTENDED
from cryptography.fernet import Fernet

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

key = load_key()
cipher_suite = Fernet(key)

SENSITIVE_KEYS = ['DEFAULT_PASSWORD', 'SERVICE_ACCOUNT_PASSWORD']

def load_config():
    """Carrega, descriptografa e retorna os dados de configuração."""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            encrypted_config = json.load(f)

        config = {}
        for k, v in encrypted_config.items():
            if k in SENSITIVE_KEYS and v:
                try:
                    config[k] = cipher_suite.decrypt(v.encode()).decode()
                except Exception:
                    config[k] = v
            else:
                config[k] = v
        return config
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_config(config):
    """Criptografa e salva os dados de configuração."""
    encrypted_config = {}
    config_copy = config.copy()
    for k, v in config_copy.items():
        if k in SENSITIVE_KEYS and v:
            encrypted_config[k] = cipher_suite.encrypt(v.encode()).decode()
        else:
            encrypted_config[k] = v

    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(encrypted_config, f, indent=4)

# ==============================================================================
# Funções de Conexão e Lógica AD
# ==============================================================================
def get_ldap_connection(user=None, password=None):
    """Cria uma conexão LDAP com base na configuração."""
    config = load_config()
    ad_server = config.get('AD_SERVER')
    use_ldaps = config.get('USE_LDAPS', False)
    if not ad_server:
        raise Exception("Servidor AD não configurado.")

    if user and password:
        server = Server(ad_server, use_ssl=use_ldaps, get_info=ALL)
        return Connection(server, user=user, password=password, auto_bind=True)
    else:
        service_user = config.get('SERVICE_ACCOUNT_USER')
        service_password = config.get('SERVICE_ACCOUNT_PASSWORD')
        if not service_user or not service_password:
            raise Exception("Conta de serviço não configurada.")
        server = Server(ad_server, use_ssl=use_ldaps, get_info=ALL)
        return Connection(server, user=service_user, password=service_password, auto_bind=True)

def is_recycle_bin_enabled(conn):
    """Verifica se a Lixeira do Active Directory está habilitada."""
    if not conn or not conn.bound:
        return False
    try:
        # A informação sobre features opcionais como a lixeira fica no "Configuration Naming Context"
        config_dn = conn.server.info.other.get('configurationNamingContext')[0]
        if not config_dn:
            logging.warning("Não foi possível determinar o 'configurationNamingContext' do servidor AD.")
            return False

        # O objeto que representa a funcionalidade da lixeira tem um DN e atributos específicos
        search_base = f"CN=Optional Features,CN=Directory Service,CN=Windows NT,CN=Services,{config_dn}"
        # O atributo msDS-EnabledFeature aponta para o DN da feature habilitada.
        # O GUID '766ddcd8-acd0-445e-f3b9-a7f9b6744f2a' é o well-known GUID para a Lixeira.
        search_filter = "(&(objectClass=msDS-OptionalFeature)(msDS-EnabledFeature=CN=Recycle Bin Feature,CN=Optional Features,CN=Directory Service,CN=Windows NT,CN=Services," + config_dn + "))"

        conn.search(search_base, search_filter, attributes=['cn'])

        # Se a busca retornar alguma entrada, a funcionalidade está habilitada.
        return bool(conn.entries)
    except Exception as e:
        logging.error(f"Erro ao verificar o status da Lixeira do AD: {e}")
        return False

def get_user_by_samaccountname(conn, sam_account_name, attributes=None):
    if attributes is None:
        attributes = ALL
    config = load_config()
    search_base = config.get('AD_SEARCH_BASE', conn.server.info.other['defaultNamingContext'][0])
    conn.search(search_base, f'(sAMAccountName={sam_account_name})', attributes=attributes)
    if conn.entries:
        return conn.entries[0]
    return None

def filetime_to_datetime(ft):
    """Converts a Microsoft FILETIME timestamp to a Python datetime object."""
    EPOCH_AS_FILETIME = 116444736000000000
    HUNDREDS_OF_NANOSECONDS = 10000000
    if ft is None or int(ft) == 0 or int(ft) == 9223372036854775807:
        return None
    return datetime.fromtimestamp((int(ft) - EPOCH_AS_FILETIME) / HUNDREDS_OF_NANOSECONDS, tz=timezone.utc)

def get_group_by_name(conn, group_name, attributes=None):
    if attributes is None:
        attributes = ALL
    config = load_config()
    search_base = config.get('AD_SEARCH_BASE', conn.server.info.other['defaultNamingContext'][0])
    conn.search(search_base, f'(&(objectClass=group)(cn={group_name}))', attributes=attributes)
    if conn.entries:
        return conn.entries[0]
    return None
