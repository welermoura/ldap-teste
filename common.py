import os
import json
import logging
from ldap3 import Server, Connection, ALL, ALL_ATTRIBUTES
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
    """
    Cria uma conexão LDAP. Para a conta de serviço, tenta primeiro uma conexão
    segura com SASL/GSSAPI (Kerberos) e sealing, ideal para operações sensíveis
    como reset de senha. Se falhar, recorre à autenticação simples.
    """
    config = load_config()
    ad_server = config.get('AD_SERVER')
    use_ldaps = config.get('USE_LDAPS', False)
    if not ad_server:
        raise Exception("Servidor AD não configurado.")

    server = Server(ad_server, use_ssl=use_ldaps, get_info=ALL)

    # Conexão para um usuário final (login) usa sempre autenticação simples
    if user and password:
        logging.info(f"Tentando autenticação simples para o usuário: {user}")
        return Connection(server, user=user, password=password, auto_bind=True)

    # Conexão com a conta de serviço
    service_user = config.get('SERVICE_ACCOUNT_USER')
    service_password = config.get('SERVICE_ACCOUNT_PASSWORD')
    if not service_user or not service_password:
        raise Exception("Conta de serviço não configurada.")

    # Tenta a conexão segura com Kerberos/GSSAPI primeiro para a conta de serviço
    try:
        logging.info(f"Tentando conexão SASL/GSSAPI (Kerberos) para: {service_user}")
        # A biblioteca ldap3 delega a negociação de "sealing" para a
        # configuração do Kerberos no nível do sistema. O parâmetro 'sasl_seal'
        # não é válido. Apenas solicitar GSSAPI é o suficiente.
        conn = Connection(server, user=service_user, password=service_password,
                          authentication='SASL', sasl_mechanism='GSSAPI',
                          auto_bind=True)
        logging.info("Conexão SASL/GSSAPI bem-sucedida.")
        return conn
    except Exception as e_sasl:
        logging.warning(f"Falha na conexão SASL/GSSAPI com sealing: {e_sasl}. Tentando autenticação simples como fallback.")
        # Se a conexão SASL falhar, tenta a autenticação simples como fallback
        try:
            conn = Connection(server, user=service_user, password=service_password, auto_bind=True)
            logging.info("Conexão de fallback com autenticação simples bem-sucedida.")
            return conn
        except Exception as e_simple:
            logging.error(f"Falha na conexão de fallback com autenticação simples: {e_simple}")
            raise Exception(f"Falha em ambas as tentativas de conexão (SASL e Simples): SASL Error: {e_sasl}, Simple Auth Error: {e_simple}")

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

def get_user_by_samaccountname(conn, sam_account_name, attributes=None):
    if attributes is None:
        attributes = ALL_ATTRIBUTES
    config = load_config()
    search_base = config.get('AD_SEARCH_BASE', conn.server.info.other['defaultNamingContext'][0])
    conn.search(search_base, f'(sAMAccountName={sam_account_name})', attributes=attributes)
    if conn.entries:
        return conn.entries[0]
    return None


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
        search_filter = f"(&(objectClass=group)(cn=*{escape_filter_chars(query)}*))"
        conn.search(search_base, search_filter, attributes=['cn', 'description', 'distinguishedName'])

        # 3. Filtrar os resultados para excluir aqueles dos quais o usuário já é membro
        groups_not_member_of = []
        for group in conn.entries:
            if group.distinguishedName.value not in current_user_groups_dns:
                groups_not_member_of.append({
                    'cn': group.cn.value if 'cn' in group else '',
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
    conn.search(search_base, f'(&(objectClass=group)(cn={group_name}))', attributes=attributes)
    if conn.entries:
        return conn.entries[0]
    return None
