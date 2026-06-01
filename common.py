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

SENSITIVE_KEYS = ['DEFAULT_PASSWORD', 'SERVICE_ACCOUNT_PASSWORD', 'ZIMBRA_ADMIN_PASSWORD']

_cached_config = None

def load_config(force_reload=False):
    """Carrega, descriptografa e retorna os dados de configuração com cache simples."""
    global _cached_config
    if _cached_config is not None and not force_reload:
        return _cached_config
        
    try:
        if not os.path.exists(CONFIG_FILE):
            return {}
            
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
        _cached_config = config
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
    
    # Invalida o cache após salvar
    global _cached_config
    _cached_config = None

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
    try:
        with open(PERMISSIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_permissions(permissions):
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
    try:
        with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_schedules(schedules):
    with open(SCHEDULE_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedules, f, indent=4)

def load_disable_schedules():
    try:
        with open(DISABLE_SCHEDULE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_disable_schedules(schedules):
    with open(DISABLE_SCHEDULE_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedules, f, indent=4)

def load_group_schedules():
    try:
        with open(GROUP_SCHEDULE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_group_schedules(schedules):
    with open(GROUP_SCHEDULE_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedules, f, indent=4)

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
        server = Server(ad_server, use_ssl=use_ldaps, get_info=ALL, connect_timeout=5)
        
        # Caso 1: Login de Usuário (Sempre Simples)
        if user and password:
            logging.debug(f"Autenticação simples para usuário: {user}")
            return Connection(server, user=user, password=password, auto_bind=True, receive_timeout=10, read_only=read_only)

        # Caso 2: Conta de Serviço
        service_user = config.get('SERVICE_ACCOUNT_USER')
        service_password = config.get('SERVICE_ACCOUNT_PASSWORD')
        
        if not service_user or not service_password:
            raise Exception("Conta de serviço não configurada.")

        # Tenta Kerberos se disponível (requer libs do sistema)
        try:
            logging.debug("Tentando SASL/GSSAPI (Kerberos)...")
            return Connection(server, user=service_user, password=service_password,
                              authentication='SASL', sasl_mechanism='GSSAPI',
                              auto_bind=True, receive_timeout=15, read_only=read_only)
        except Exception as e_sasl:
            logging.debug(f"SASL falhou: {e_sasl}. Usando Simples...")
            return Connection(server, user=service_user, password=service_password, 
                              auto_bind=True, receive_timeout=15, read_only=read_only)

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

def get_user_by_samaccountname(conn, sam_account_name, attributes=None):
    if attributes is None:
        attributes = ALL_ATTRIBUTES
    config = load_config()
    search_base = config.get('AD_SEARCH_BASE')
    if not search_base:
        if conn.server.info and conn.server.info.other:
            search_base = conn.server.info.other['defaultNamingContext'][0]
        else:
            raise Exception("AD_SEARCH_BASE não configurado e informações do servidor indisponíveis.")
            
    conn.search(search_base, f'(sAMAccountName={sam_account_name})', attributes=attributes)
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
    email = f"{first_name.lower()}.{last_name_part.lower()}@{email_domain}"

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

def save_to_history(action, user_sam, details=""):
    """Salva uma ação executada no arquivo de histórico."""
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
        
        # Mantém apenas os últimos 1000 registros
        if len(history) > 1000:
            history = history[-1000:]
            
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4)
    except Exception as e:
        logging.error(f"Erro ao salvar histórico: {e}")
