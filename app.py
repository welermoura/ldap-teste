# Reverted to stable version
import os
import logging
from flask import Flask, render_template, request, flash, redirect, url_for, session, jsonify, Response, send_from_directory
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, ValidationError, Length, EqualTo
import ldap3
from ldap3 import Server, Connection, ALL, SUBTREE, BASE, LEVEL
from ldap3.utils.conv import escape_filter_chars
from datetime import datetime, timedelta, date, timezone
import json
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import re
import secrets
import io
import csv
import base64
from common import load_config, save_config, get_ldap_connection, get_user_by_samaccountname, get_group_by_name, filetime_to_datetime, is_recycle_bin_enabled

# ==============================================================================
# Configuração Base
# ==============================================================================
basedir = os.path.abspath(os.path.dirname(__file__))

# Criação dos diretórios de dados e logs
data_dir = os.path.join(basedir, 'data')
logs_dir = os.path.join(basedir, 'logs')
os.makedirs(data_dir, exist_ok=True)
os.chmod(data_dir, 0o750) # Permissões mais restritivas
os.makedirs(logs_dir, exist_ok=True)

log_path = os.path.join(logs_dir, 'ad_creator.log')
logging.basicConfig(filename=log_path, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', encoding='utf-8')
app = Flask(__name__)

def get_flask_secret_key():
    key_file_path = os.path.join(data_dir, 'flask_secret.key')
    if os.path.exists(key_file_path):
        with open(key_file_path, 'r') as f:
            return f.read().strip()
    else:
        new_key = secrets.token_hex(32)
        with open(key_file_path, 'w') as f:
            f.write(new_key)
        os.chmod(key_file_path, 0o600)
        return new_key

app.secret_key = get_flask_secret_key()
SCHEDULE_FILE = os.path.join(data_dir, 'schedules.json')
DISABLE_SCHEDULE_FILE = os.path.join(data_dir, 'disable_schedules.json')
PERMISSIONS_FILE = os.path.join(data_dir, 'permissions.json')
KEY_FILE = os.path.join(data_dir, 'secret.key')
CONFIG_FILE = os.path.join(data_dir, 'config.json')

# ==============================================================================
# Funções Auxiliares de User/Schedule/Permissions (sem alteração)
# ==============================================================================
def load_user():
    user_path = os.path.join(data_dir, 'user.json')
    try:
        with open(user_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def save_user(user_data):
    user_path = os.path.join(data_dir, 'user.json')
    with open(user_path, 'w', encoding='utf-8') as f:
        json.dump(user_data, f, indent=4)

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

GROUP_SCHEDULE_FILE = os.path.join(data_dir, 'group_schedules.json')

def load_group_schedules():
    try:
        with open(GROUP_SCHEDULE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_group_schedules(schedules):
    with open(GROUP_SCHEDULE_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedules, f, indent=4)

def load_permissions():
    try:
        with open(PERMISSIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_permissions(permissions):
    with open(PERMISSIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(permissions, f, indent=4)


# ==============================================================================
# Lógica de Permissões (sem alteração)
# ==============================================================================
def get_user_access_level(user_groups):
    """
    Determina o nível de acesso mais alto de um usuário com base em seus grupos.
    Retorna 'full', 'custom', ou 'none'.
    A ordem de precedência é: full > custom > none.
    """
    permissions = load_permissions()
    if not user_groups or not permissions:
        return 'none'

    access_levels = {'none'}  # Começa com o nível mais baixo
    for group in user_groups:
        rule = permissions.get(group, {})
        access_levels.add(rule.get('type', 'none'))

    if 'full' in access_levels:
        return 'full'
    if 'custom' in access_levels:
        return 'custom'
    return 'none'

def check_permission(action=None, field=None, view=None):
    access_level = session.get('access_level')
    if access_level == 'full':
        return True
    if access_level == 'none':
        return False

    # Se for 'custom', verifica as permissões detalhadas
    user_groups = session.get('user_groups', [])
    permissions = load_permissions()
    if not permissions or not user_groups: return False

    for group in user_groups:
        rule = permissions.get(group)
        if rule and rule.get('type') == 'custom':
            if action and rule.get('actions', {}).get(action): return True
            if field and field in rule.get('fields', []): return True
            if view and rule.get('views', {}).get(view): return True
    return False

def require_permission(action=None, field=None, view=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not check_permission(action=action, field=field, view=view):
                flash('Você não tem permissão para realizar esta ação.', 'error')
                return redirect(request.referrer or url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_api_permission(action=None):
    """Decorator de permissão para rotas de API que retorna JSON em vez de redirecionar."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not check_permission(action=action):
                return jsonify({'error': 'Permissão negada.'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ==============================================================================
# Decorators e Processadores de Contexto (sem alteração)
# ==============================================================================
@app.before_request
def before_request_func():
    # A verificação de usuário admin foi removida daqui para corrigir o loop de login.
    # A proteção individual em cada rota de admin já é suficiente.

    # Adiciona a verificação da lixeira à sessão para evitar checagens repetidas
    if 'recycle_bin_enabled' not in session and is_authenticated():
        try:
            conn = get_read_connection()
            session['recycle_bin_enabled'] = is_recycle_bin_enabled(conn)
            if session['recycle_bin_enabled']:
                logging.info("Lixeira do AD está habilitada para esta sessão.")
            else:
                logging.info("Lixeira do AD não está habilitada para esta sessão.")
        except Exception as e:
            logging.error(f"Falha ao verificar o status da lixeira do AD: {e}")
            session['recycle_bin_enabled'] = False

def is_authenticated():
    return 'ad_user' in session

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_authenticated():
            flash("Sua sessão expirou. Por favor, faça login novamente.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_year():
    return {'year': datetime.now().year}

@app.context_processor
def inject_user_status_processor():
    return dict(get_user_status=get_user_status)

@app.context_processor
def inject_attr_value_getter():
    return dict(get_attr_value=get_attr_value)

@app.context_processor
def inject_permission_checker():
    return dict(check_permission=check_permission)

# ==============================================================================
# Validadores Customizados e Funções Auxiliares (sem alteração)
# ==============================================================================
def validate_sam_account(form, field):
    if not all(c.isalnum() or c in '.-_' for c in field.data):
        raise ValidationError('O login pode conter apenas letras, números e os caracteres ".", "-" e "_".')

def get_attr_value(user, attr):
    return user[attr].value if attr in user and user[attr].value is not None else ''

def filetime_to_datetime(ft):
    EPOCH_AS_FILETIME = 116444736000000000
    HUNDREDS_OF_NANOSECONDS = 10000000
    if ft is None or int(ft) == 0 or int(ft) == 9223372036854775807:
        return None
    return datetime.fromtimestamp((int(ft) - EPOCH_AS_FILETIME) / HUNDREDS_OF_NANOSECONDS, tz=timezone.utc)

def format_phone_number(phone_str):
    """Formata um número de telefone para o padrão XX XXXX-XXXX."""
    if not phone_str:
        return ""

    digits = re.sub(r'\D', '', phone_str)

    # Se tiver mais de 10 dígitos, considera apenas os últimos 10 para o formato fixo.
    if len(digits) > 10:
        digits = digits[-10:]

    if len(digits) == 10:
        return f"{digits[0:2]} {digits[2:6]}-{digits[6:10]}"
    else:
        # Se não tiver 10 dígitos, retorna o número com os dígitos que tem
        return phone_str

# ==============================================================================
# Modelos de Formulário (Forms)
# ==============================================================================
class LoginForm(FlaskForm):
    username = StringField('Nome de Usuário', validators=[DataRequired()])
    password = PasswordField('Senha', validators=[DataRequired()])
    submit = SubmitField('Entrar')

class CreateUserForm(FlaskForm):
    first_name = StringField('Primeiro Nome', validators=[DataRequired()])
    last_name = StringField('Sobrenome', validators=[DataRequired()])
    sam_account = StringField('Login de Usuário (máx 20 caracteres)', validators=[DataRequired(), Length(max=20), validate_sam_account])
    model_name = StringField('Nome do Usuário Modelo', validators=[DataRequired()])
    telephone = StringField('Telefone (opcional)')
    submit = SubmitField('Buscar Modelo')

class AdminRegistrationForm(FlaskForm):
    username = StringField('Nome de Usuário do Admin', validators=[DataRequired(), Length(min=4, max=25)])
    password = PasswordField('Senha do Admin', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirmar Senha', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Registrar Admin')

class AdminLoginForm(FlaskForm):
    username = StringField('Nome de Usuário do Admin', validators=[DataRequired()])
    password = PasswordField('Senha do Admin', validators=[DataRequired()])
    submit = SubmitField('Entrar')

class AdminChangePasswordForm(FlaskForm):
    current_password = PasswordField('Senha Atual', validators=[DataRequired()])
    new_password = PasswordField('Nova Senha', validators=[DataRequired(), Length(min=8, message='A senha deve ter pelo menos 8 caracteres.')])
    confirm_new_password = PasswordField('Confirmar Nova Senha', validators=[DataRequired(), EqualTo('new_password', message='As senhas não coincidem.')])
    submit = SubmitField('Alterar Senha')

class ConfigForm(FlaskForm):
    ad_server = StringField('Servidor AD', validators=[DataRequired()])
    use_ldaps = BooleanField('Usar LDAPS (SSL)', default=False)
    ad_domain = StringField('Domínio (NetBIOS name, ex: MEUDOMINIO)', validators=[DataRequired()])
    ad_search_base = StringField('Base de Busca AD (ex: OU=Usuarios,DC=dominio,DC=com)', validators=[DataRequired()])
    sso_enabled = BooleanField('Habilitar Single Sign-On (SSO)', default=False)
    default_password = PasswordField('Senha Padrão (deixe em branco para não alterar)')
    service_account_user = StringField('Usuário de Serviço (para tarefas automáticas)')
    service_account_password = PasswordField('Senha do Usuário de Serviço (deixe em branco para não alterar)')
    submit = SubmitField('Salvar Configuração')

class UserSearchForm(FlaskForm):
    search_query = StringField('Buscar Usuário (Nome ou Login)', validators=[DataRequired()])
    submit = SubmitField('Buscar')

class GroupSearchForm(FlaskForm):
    search_query = StringField('Buscar Grupo por Nome', validators=[DataRequired()])
    submit = SubmitField('Buscar')

class LogSearchForm(FlaskForm):
    search_query = StringField('Filtrar Log por Texto')
    submit = SubmitField('Filtrar')

class EditUserForm(FlaskForm):
    first_name = StringField('Nome', validators=[DataRequired()])
    initials = StringField('Iniciais')
    last_name = StringField('Sobrenome', validators=[DataRequired()])
    display_name = StringField('Nome de Exibição', validators=[DataRequired()])
    description = StringField('Descrição')
    office = StringField('Escritório')
    telephone = StringField('Telefone Principal')
    email = StringField('E-mail')
    web_page = StringField('Página da Web')
    street = StringField('Rua')
    post_office_box = StringField('Caixa Postal')
    city = StringField('Cidade')
    state = StringField('Estado/Província')
    zip_code = StringField('CEP')
    home_phone = StringField('Telefone Residencial')
    pager = StringField('Pager')
    mobile = StringField('Celular')
    fax = StringField('Fax')
    title = StringField('Cargo')
    department = StringField('Departamento')
    company = StringField('Empresa')
    submit = SubmitField('Salvar Alterações')

class DeleteUserForm(FlaskForm):
    confirm_title = StringField('Confirmar Cargo', validators=[DataRequired()])
    confirm_sam = StringField('Confirmar Login', validators=[DataRequired()])
    submit = SubmitField('Eu entendo as consequências, excluir este usuário')

# ==============================================================================
# Funções Auxiliares do Active Directory
# ==============================================================================
def get_service_account_connection():
    """Obtém uma conexão LDAP usando a conta de serviço."""
    return get_ldap_connection()

def get_read_connection():
    """
    Retorna uma conexão para operações de LEITURA.
    Usa sempre a conta de serviço, que é mais segura e centralizada.
    """
    try:
        return get_service_account_connection()
    except Exception as e:
        raise Exception(f"É necessária uma conta de serviço configurada para todas as operações de leitura. Erro: {e}")

def get_user_by_samaccountname(conn, sam_account_name, attributes=None):
    if attributes is None:
        attributes = ldap3.ALL_ATTRIBUTES
    config = load_config()
    search_base = config.get('AD_SEARCH_BASE', conn.server.info.other['defaultNamingContext'][0])
    conn.search(search_base, f'(sAMAccountName={sam_account_name})', attributes=attributes)
    if conn.entries:
        return conn.entries[0]
    return None

def get_group_by_name(conn, group_name, attributes=None):
    if attributes is None:
        attributes = ldap3.ALL_ATTRIBUTES
    config = load_config()
    search_base = config.get('AD_SEARCH_BASE', conn.server.info.other['defaultNamingContext'][0])
    # Escape the group name to handle special characters in the LDAP filter
    safe_group_name = escape_filter_chars(group_name)
    conn.search(search_base, f'(&(objectClass=group)(cn={safe_group_name}))', attributes=attributes)
    if conn.entries:
        return conn.entries[0]
    return None

def get_user_by_dn(conn, user_dn, attributes=None):
    """Busca um usuário diretamente pelo seu Distinguished Name."""
    if attributes is None:
        attributes = ldap3.ALL_ATTRIBUTES
    try:
        conn.search(user_dn, '(objectClass=*)', BASE, attributes=attributes)
        if conn.entries:
            return conn.entries[0]
    except ldap3.core.exceptions.LDAPNoSuchObjectResult:
        # Isso pode acontecer se o DN for de um objeto que não é mais válido
        return None
    return None

def get_ou_from_dn(dn):
    parts = dn.split(',')
    return ','.join(parts[1:])

def get_ou_path(dn):
    parts = dn.split(',')
    ou_parts = [p.split('=')[1] for p in parts if p.startswith(('OU=', 'CN='))]
    ou_parts.reverse()
    if ou_parts: ou_parts.pop(0)
    return ' --- '.join(ou_parts) if ou_parts else 'N/A'

def get_user_status(user_entry):
    if not user_entry or 'userAccountControl' not in user_entry:
        return "Desconhecido"
    uac = user_entry.userAccountControl.value
    if uac & 2:
        return "Desativado"
    return "Ativo"

def search_general_users(conn, query):
    try:
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE', conn.server.info.other['defaultNamingContext'][0])
        search_filter = f"(&(objectClass=user)(objectCategory=person)(|(displayName=*{query.replace('*', '')}*)(sAMAccountName=*{query.replace('*', '')}*)))"
        # Adicionando 'name' e 'mail' para corrigir a busca de usuários.
        attributes_to_get = ['displayName', 'name', 'mail', 'sAMAccountName', 'title', 'l', 'userAccountControl', 'distinguishedName']
        conn.search(search_base, search_filter, SUBTREE, attributes=attributes_to_get)
        return conn.entries
    except Exception as e:
        logging.error(f"Erro ao buscar usuários com a query '{query}': {str(e)}")
        return []

def get_all_ous(conn):
    """Busca todas as OUs e containers e os retorna em uma estrutura de árvore hierárquica."""
    config = load_config()
    search_base = config.get('AD_SEARCH_BASE')
    if not search_base:
        return []

    # Filtro para buscar tanto Unidades Organizacionais quanto Containers padrão.
    ldap_filter = "(|(objectClass=organizationalUnit)(objectClass=container))"
    conn.search(search_base, ldap_filter, SUBTREE, attributes=['ou', 'cn', 'distinguishedName', 'objectClass'])

    if not conn.entries:
        return []

    nodes = {}
    # Primeira passada: cria todos os objetos de nó e os armazena em um dicionário pelo seu DN.
    for entry in conn.entries:
        # Pula o container "ForeignSecurityPrincipals" que geralmente não é relevante para gerenciamento.
        if 'ForeignSecurityPrincipals' in str(entry.cn):
            continue

        dn = str(entry.distinguishedName)
        # O nome vem do atributo 'ou' para OUs e 'cn' para Containers.
        node_name = str(entry.ou) if 'organizationalUnit' in entry.objectClass else str(entry.cn)

        nodes[dn] = {
            'text': node_name,
            'dn': dn,
            'nodes': []
        }

    tree_roots = []
    # Second pass: link nodes together.
    for dn, node in nodes.items():
        # Determine the parent DN by removing the first component of the current DN.
        parent_dn = ','.join(dn.split(',')[1:])

        # If the parent DN exists in our dictionary, it's a child of that parent.
        if parent_dn in nodes:
            nodes[parent_dn]['nodes'].append(node)
        # Otherwise, it's a root node in our hierarchy.
        else:
            tree_roots.append(node)

    # Sort the tree and all sub-nodes alphabetically by 'text' for a clean UI.
    def sort_tree_nodes_recursively(node_list):
        node_list.sort(key=lambda x: x['text'])
        for node in node_list:
            if node['nodes']:
                sort_tree_nodes_recursively(node['nodes'])

    sort_tree_nodes_recursively(tree_roots)

    return tree_roots

def get_upn_suffix_from_base(search_base):
    """Deriva o sufixo UPN da base de busca. Ex: OU=Users,DC=corp,DC=com -> @corp.com"""
    dc_parts = [part.split('=')[1] for part in search_base.split(',') if part.strip().upper().startswith('DC=')]
    if not dc_parts:
        return None
    return '@' + '.'.join(dc_parts)

def create_ad_user(conn, form_data, model_attrs):
    config = load_config()
    first_name = form_data['first_name']
    last_name = form_data['last_name']
    sam = form_data['sam_account']

    upn_suffix = get_upn_suffix_from_base(config.get('AD_SEARCH_BASE', ''))
    if not upn_suffix:
        return {'success': False, 'message': "Erro: Não foi possível derivar o Sufixo UPN da Base de Busca AD. Verifique a configuração."}

    upn = f"{sam}{upn_suffix}"
    last_name_part = last_name.split()[-1] if last_name else ""
    display_name = f"{first_name} {last_name_part}"
    initials = ''.join([p[0].upper() for p in (first_name + " " + last_name).split() if p])
    ou_dn = get_ou_from_dn(model_attrs.entry_dn)
    try:
        # 1. Verificar se o login (sAMAccountName) já existe em todo o AD
        if get_user_by_samaccountname(conn, sam):
            return {'success': False, 'message': f"Erro: O login '{sam}' já existe no Active Directory."}

        # 2. Verificar se o nome de exibição (CN) já existe na mesma OU
        safe_display_name = escape_filter_chars(display_name)
        conn.search(ou_dn, f'(&(objectClass=user)(cn={safe_display_name}))', attributes=['cn'])
        if conn.entries:
            return {'success': False, 'message': f"Erro: Já existe um usuário com o nome '{display_name}' nesta Unidade Organizacional. Por favor, escolha outro nome."}

    except Exception as e:
        return {'success': False, 'message': f"Erro durante a verificação de existência do usuário: {str(e)}"}

    email_domain = upn_suffix.lstrip('@')
    if 'mail' in model_attrs and model_attrs.mail:
        email_str = str(model_attrs.mail)
        if '@' in email_str: email_domain = email_str.split('@')[1]
    email = f"{first_name.lower()}.{last_name_part.lower()}@{email_domain}"

    user_attributes = {'samAccountName': sam, 'userPrincipalName': upn, 'givenName': first_name, 'sn': last_name, 'displayName': display_name, 'name': display_name, 'mail': email, 'initials': initials}
    model_attributes_to_copy = ['title', 'department', 'company', 'description', 'manager', 'physicalDeliveryOfficeName', 'streetAddress', 'l', 'st', 'postalCode', 'c', 'telephoneNumber', 'homePhone', 'wWWHomePage', 'postOfficeBox', 'pager', 'mobile', 'facsimileTelephoneNumber']
    for attr in model_attributes_to_copy:
        if attr in model_attrs and model_attrs[attr]: user_attributes[attr] = str(model_attrs[attr])
    if form_data.get('telephone'):
        formatted_phone = format_phone_number(form_data['telephone'])
        user_attributes['telephoneNumber'] = formatted_phone
        user_attributes['homePhone'] = formatted_phone

    try:
        user_dn = f"CN={display_name},{ou_dn}"
        conn.add(user_dn, ['user'], user_attributes)
        if not conn.result['description'] == 'success': raise Exception(f"Erro ao adicionar usuário: {conn.result['message']}")

        default_password = config.get('DEFAULT_PASSWORD')
        if not default_password:
             return {'success': False, 'message': "Erro: A senha padrão não está configurada."}

        conn.extend.microsoft.modify_password(user_dn, default_password)
        conn.modify(user_dn, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [512])], 'pwdLastSet': [(ldap3.MODIFY_REPLACE, [0])]})
        if 'memberOf' in model_attrs and model_attrs.memberOf: conn.extend.microsoft.add_members_to_groups(user_dn, [str(g) for g in model_attrs.memberOf])
        logging.info(f"Usuário '{display_name}' ({sam}) foi criado por '{session.get('ad_user')}'.")
        return {'success': True, 'message': f"Usuário '{display_name}' criado com sucesso!", 'email': email, 'initials': initials, 'display_name': display_name, 'sam_account': sam, 'password': default_password, 'ou_path': get_ou_path(model_attrs.entry_dn)}
    except Exception as e:
        logging.error(f"Erro ao criar o usuário '{display_name}': {e}")
        # Attempt to delete the partially created user to avoid orphaned objects
        try:
            conn.delete(user_dn)
            logging.warning(f"Objeto de usuário parcialmente criado para '{display_name}' foi removido após erro na criação.")
        except Exception as delete_e:
            logging.error(f"Falha ao remover objeto de usuário parcialmente criado para '{display_name}': {delete_e}")
        return {'success': False, 'message': f"Erro ao criar usuário: {str(e)}"}

# ==============================================================================
# Rotas Principais da Aplicação
# ==============================================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    config = load_config()
    sso_enabled = config.get('SSO_ENABLED', False)

    form = LoginForm()
    if form.validate_on_submit():
        try:
            ad_domain = config.get('AD_DOMAIN')
            if not ad_domain:
                flash('O domínio AD não está configurado. Por favor, contate o administrador.', 'error')
                return render_template('login.html', form=form, sso_enabled=sso_enabled)

            username = form.username.data
            password = form.password.data
            full_username = f'{ad_domain}\\{username}'

            conn = get_ldap_connection(full_username, password)

            # Busca também o displayName e sAMAccountName para exibição
            user_object = get_user_by_samaccountname(conn, username, attributes=['memberOf', 'displayName', 'sAMAccountName'])
            if not user_object:
                flash('Nome de usuário ou senha inválidos.', 'error')
                return redirect(url_for('login'))

            user_groups = [g.split(',')[0].split('=')[1] for g in user_object.memberOf.values] if 'memberOf' in user_object and user_object.memberOf.value else []
            access_level = get_user_access_level(user_groups)

            if access_level == 'none':
                flash('Você não tem permissão para acessar o sistema.', 'error')
                return redirect(url_for('login'))

            session['ad_user'] = user_object.entry_dn
            session['user_display_name'] = get_attr_value(user_object, 'displayName') or get_attr_value(user_object, 'sAMAccountName')
            session['user_groups'] = user_groups
            session['access_level'] = access_level
            session['sso_login'] = False

            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('dashboard'))
        except ldap3.core.exceptions.LDAPInvalidCredentialsResult:
            flash('Login ou senha inválidos.', 'error')
        except Exception as e:
            flash('Erro de conexão com o servidor. Por favor, contate o administrador.', 'error')
            logging.error(f"Erro de login para usuário '{form.username.data}': {e}", exc_info=True)

    return render_template('login.html', form=form, sso_enabled=sso_enabled)

@app.route('/sso_login')
def sso_login():
    config = load_config()
    if not config.get('SSO_ENABLED', False):
        flash("O Single Sign-On não está habilitado.", "error")
        return redirect(url_for('login'))

    # O nome de usuário é fornecido pelo servidor web (ex: Apache com mod_auth_kerb)
    # no formato 'user@REALM' ou 'user'.
    remote_user = request.environ.get('REMOTE_USER')
    if not remote_user:
        flash("Não foi possível obter a identidade do usuário para o SSO. Verifique a configuração do servidor web.", "error")
        logging.error("SSO Login falhou: a variável de ambiente REMOTE_USER não foi encontrada.")
        return redirect(url_for('login'))

    # Extrai o sAMAccountName (ex: de 'user@CORP.COM' para 'user')
    username = remote_user.split('@')[0]

    try:
        # Para SSO, a conexão inicial é feita com a conta de serviço para verificar o usuário
        conn = get_service_account_connection()
        user_object = get_user_by_samaccountname(conn, username, attributes=['memberOf', 'distinguishedName', 'displayName', 'sAMAccountName'])

        if not user_object:
            flash(f"Usuário SSO '{username}' não encontrado no Active Directory.", 'error')
            logging.warning(f"Tentativa de login SSO falhou. Usuário '{username}' não encontrado.")
            return redirect(url_for('login'))

        user_groups = [g.split(',')[0].split('=')[1] for g in user_object.memberOf.values] if 'memberOf' in user_object and user_object.memberOf.value else []

        access_level = get_user_access_level(user_groups)

        if access_level not in ['full', 'custom', 'none']:
            flash('Você não tem permissão para acessar o sistema.', 'error')
            logging.warning(f"Tentativa de login SSO para o usuário '{username}' falhou devido à falta de permissões.")
            return redirect(url_for('login'))

        session['ad_user'] = user_object.distinguishedName.value
        session['user_display_name'] = get_attr_value(user_object, 'displayName') or get_attr_value(user_object, 'sAMAccountName')
        session['user_groups'] = user_groups
        session['access_level'] = access_level
        session['sso_login'] = True

        if access_level == 'none':
            flash('Bem-vindo ao Catálogo de Endereços!', 'info')
            return redirect(url_for('address_book'))

        flash('Login via SSO realizado com sucesso!', 'success')
        logging.info(f"Usuário '{username}' logado com sucesso via SSO.")
        return redirect(url_for('dashboard'))

    except Exception as e:
        flash(f"Ocorreu um erro durante o processo de SSO: {e}", 'error')
        logging.error(f"Erro de SSO para o usuário '{username}': {e}", exc_info=True)
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@require_auth
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@require_auth
def dashboard():
    context = {
        'active_users': 0,
        'disabled_users': 0,
        'deactivated_last_week': 0,
        'pending_reactivations': 0,
        'pending_deactivations': 0,
        'expiring_passwords': []
    }
    try:
        conn = get_read_connection()
        # Permissões para cada card
        if check_permission(view='can_view_user_stats'):
            stats = get_dashboard_stats(conn)
            context['active_users'] = stats.get('enabled_users', 0)
            context['disabled_users'] = stats.get('disabled_users', 0)

        if check_permission(view='can_view_deactivated_last_week'):
            context['deactivated_last_week'] = get_deactivated_last_week()

        if check_permission(view='can_view_pending_reactivations'):
            context['pending_reactivations'] = get_pending_reactivations(days=7)

        if check_permission(view='can_view_pending_deactivations'):
            context['pending_deactivations'] = get_pending_deactivations(days=7)

        if check_permission(view='can_view_expiring_passwords'):
            context['expiring_passwords'] = get_expiring_passwords(conn, days=5)

    except Exception as e:
        flash(f"Erro ao carregar dados do dashboard: {e}", "error")

    return render_template('dashboard.html', **context)

@app.route('/create_user_form', methods=['GET', 'POST'])
@require_auth
@require_permission(action='can_create')
def create_user_form():
    form = CreateUserForm()
    if form.validate_on_submit():
        try:
            conn = get_read_connection() # Alterado para usar a conexão de leitura
            model_name = form.model_name.data.strip()
            if not model_name:
                flash("O nome do usuário modelo é obrigatório.", 'error')
                return render_template('create_user_form.html', form=form)
            users = search_general_users(conn, model_name)
            if not users:
                flash(f"Nenhum usuário encontrado com o nome '{model_name}'.", 'error')
                return render_template('create_user_form.html', form=form)
            session['form_data'] = {
                'first_name': form.first_name.data,
                'last_name': form.last_name.data,
                'sam_account': form.sam_account.data,
                'telephone': form.telephone.data
            }
            session['found_users_sams'] = [u.sAMAccountName.value for u in users]
            return redirect(url_for('select_model'))
        except Exception as e:
            flash(f"Erro ao buscar modelo: {e}", 'error')
    return render_template('create_user_form.html', form=form)

@app.route('/select_model', methods=['GET', 'POST'])
@require_auth
@require_permission(action='can_create')
def select_model():
    form_data = session.get('form_data')
    if not form_data:
        return redirect(url_for('index'))
    users = []
    try:
        conn = get_read_connection() # Alterado para usar a conexão de leitura
        for sam_name in session.get('found_users_sams', []):
            user_entry = get_user_by_samaccountname(conn, sam_name, ['name', 'sAMAccountName', 'distinguishedName', 'physicalDeliveryOfficeName'])
            if user_entry:
                users.append({'name': user_entry.name.value, 'sam_account': user_entry.sAMAccountName.value, 'office': str(user_entry.physicalDeliveryOfficeName.value) if 'physicalDeliveryOfficeName' in user_entry and user_entry.physicalDeliveryOfficeName.value else 'N/A', 'ou_path': get_ou_path(user_entry.entry_dn)})
    except Exception as e:
        flash(f"Erro ao carregar lista de modelos: {e}", 'error')
        return redirect(url_for('index'))
    form = FlaskForm()
    if request.method == 'POST':
        selected_user_sam = request.form.get('selected_user_sam')
        if not selected_user_sam:
            flash("Por favor, selecione um usuário modelo.", 'error')
            return render_template('select_model.html', users=users, form_data=form_data, form=form)
        try:
            service_conn = get_service_account_connection()
            model_attrs = get_user_by_samaccountname(service_conn, selected_user_sam)
            result = create_ad_user(service_conn, form_data, model_attrs)
            if result['success']:
                session.pop('form_data', None)
                session.pop('found_users_sams', None)
                return render_template('result.html', result=result)
            else:
                flash(result['message'], 'error')
        except Exception as e:
            flash(f"Erro fatal ao criar usuário: {e}", 'error')
            return redirect(url_for('index'))
    return render_template('select_model.html', users=users, form_data=form_data, form=form)

@app.route('/result')
@require_auth
def result():
    return redirect(url_for('index'))

@app.route('/ad-tree')
@require_auth
def ad_tree():
    """Renderiza o template que hospeda a aplicação React."""
    try:
        manifest_path = os.path.join(basedir, 'frontend', 'dist', '.vite', 'manifest.json')
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        # A chave de entrada correta geralmente corresponde ao arquivo de entrada do projeto Vite
        entry_point_key = 'src/main.jsx'
        if entry_point_key not in manifest:
            # Fallback para a primeira chave se o nome não for o esperado
            entry_point_key = next(iter(manifest))

        entry_point = manifest[entry_point_key]
        js_file = entry_point.get('file')
        css_files = entry_point.get('css', [])
        css_file = css_files[0] if css_files else None

        return render_template('ad_tree.html', js_file=js_file, css_file=css_file)
    except Exception as e:
        logging.error(f"Erro ao carregar o manifesto do Vite: {e}", exc_info=True)
        return "Erro ao carregar a aplicação. Verifique os logs.", 500

@app.route('/ad-tree/assets/<path:filename>')
@require_auth
def ad_tree_assets(filename):
    """Serve os assets da aplicação React."""
    return send_from_directory(os.path.join(basedir, 'frontend', 'dist', 'assets'), filename)

@app.route('/recycle_bin')
@require_auth
def recycle_bin():
    if not session.get('recycle_bin_enabled'):
        flash('A lixeira do Active Directory não está habilitada ou acessível.', 'warning')
        return redirect(url_for('dashboard'))

    items = []
    try:
        conn = get_read_connection()
        domain_dn = conn.server.info.other.get('defaultNamingContext')[0]
        deleted_objects_container = f"CN=Deleted Objects,{domain_dn}"

        # Este controle é essencial para buscar objetos excluídos
        conn.search(deleted_objects_container, '(isDeleted=TRUE)', SUBTREE,
                    attributes=['lastKnownParent', 'cn', 'whenChanged'],
                    controls=[('1.2.840.113556.1.4.417', True, None)])

        for entry in conn.entries:
            items.append({
                'dn': entry.distinguishedName.value,
                'name': entry.cn.value,
                'original_ou': get_ou_path(entry.lastKnownParent.value),
                'deleted_date': entry.whenChanged.value.strftime('%d/%m/%Y %H:%M')
            })
        items.sort(key=lambda x: x['name'].lower())
    except Exception as e:
        flash(f'Erro ao ler a lixeira: {e}', 'danger')
        logging.error(f"Erro ao acessar a lixeira do AD: {e}", exc_info=True)

    return render_template('recycle_bin.html', items=items)

@app.route('/manage_users', methods=['GET', 'POST'])
@require_auth
def manage_users():
    if not check_permission(action='can_edit'):
        flash('Você não tem permissão para acessar esta página.', 'error')
        return redirect(url_for('dashboard'))
    form = UserSearchForm()
    users = []
    if form.validate_on_submit():
        try:
            conn = get_read_connection() # Alterado para usar a conexão de leitura
            users = search_general_users(conn, form.search_query.data.strip())
        except Exception as e:
            flash(f"Erro ao conectar ou buscar usuários: {e}", "error")
    return render_template('manage_users.html', form=form, users=users)

@app.route('/group_management', methods=['GET', 'POST'])
@require_auth
@require_permission(action='can_manage_groups')
def group_management():
    form = GroupSearchForm()
    groups = []
    if form.validate_on_submit():
        try:
            conn = get_service_account_connection()
            config = load_config()
            search_base = config.get('AD_SEARCH_BASE')
            query = form.search_query.data
            search_filter = f"(&(objectClass=group)(cn=*{query}*))"
            conn.search(search_base, search_filter, attributes=['cn', 'description', 'member'])
            groups = conn.entries
            if not groups:
                flash(f"Nenhum grupo encontrado com o nome '{query}'.", "info")
        except Exception as e:
            flash(f"Erro ao buscar grupos: {e}", "error")
            logging.error(f"Erro ao buscar grupos com a query '{form.search_query.data}': {e}", exc_info=True)

    return render_template('manage_groups.html', form=form, groups=groups)


@app.route('/api/group_members/<group_name>')
@require_auth
@require_api_permission(action='can_manage_groups')
def api_group_members(group_name):
    try:
        conn = get_service_account_connection()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        search_query = request.args.get('query', '', type=str).strip()

        group = get_group_by_name(conn, group_name, attributes=['member'])
        if not group:
            return jsonify({'error': 'Group not found'}), 404

        member_dns = group.member.values if group.member.values else []

        if search_query:
            escaped_query = re.escape(search_query)
            member_dns = [dn for dn in member_dns if re.search(f'CN={escaped_query}', dn, re.IGNORECASE)]

        total_members = len(member_dns)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_dns = sorted(member_dns)[start:end] # Sort all before paginating

        members_details = []
        attributes_to_get = ['displayName', 'sAMAccountName', 'title', 'l']
        for dn in paginated_dns:
            user_entry = get_user_by_dn(conn, dn, attributes=attributes_to_get)
            if user_entry:
                members_details.append({
                    'displayName': get_attr_value(user_entry, 'displayName'),
                    'sAMAccountName': get_attr_value(user_entry, 'sAMAccountName'),
                    'title': get_attr_value(user_entry, 'title'),
                    'city': get_attr_value(user_entry, 'l')
                })
            else:
                cn_part = dn.split(',')[0]
                display_name = cn_part.split('=')[1] if '=' in cn_part else cn_part
                members_details.append({
                    'displayName': f"{display_name} (Objeto desconhecido)",
                    'sAMAccountName': 'N/A', 'title': 'N/A', 'city': 'N/A'
                })

        return jsonify({
            'members': members_details,
            'total': total_members, 'page': page, 'per_page': per_page,
            'total_pages': (total_members + per_page - 1) // per_page
        })

    except Exception as e:
        logging.error(f"Erro na API de membros do grupo '{group_name}': {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

def get_paginated_user_details(conn, search_base, sam_account_names, page, per_page, attributes):
    """
    Busca detalhes de usuários no AD de forma paginada a partir de uma lista de sAMAccountNames.
    """
    if not sam_account_names:
        return [], 0

    total_items = len(sam_account_names)
    total_pages = (total_items + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page

    sams_to_fetch = sam_account_names[start:end]
    if not sams_to_fetch:
        return [], total_pages

    # Constrói um filtro LDAP para buscar todos os usuários da página de uma só vez
    ldap_filter = "(|"
    for sam in sams_to_fetch:
        ldap_filter += f"(sAMAccountName={escape_filter_chars(sam)})"
    ldap_filter += ")"

    # Adiciona o filtro para garantir que o userPrincipalName exista
    final_filter = f"(&(userPrincipalName=*){ldap_filter})"

    conn.search(search_base, final_filter, attributes=attributes)

    # Mapeia os resultados para facilitar a ordenação e formatação
    user_details_map = {get_attr_value(e, 'sAMAccountName'): e for e in conn.entries}

    # Monta a lista final na mesma ordem dos sAMs da página
    items = []
    for sam in sams_to_fetch:
        user_entry = user_details_map.get(sam)
        if user_entry:
            items.append({
                'cn': get_attr_value(user_entry, 'cn'),
                'sam': get_attr_value(user_entry, 'sAMAccountName'),
                'title': get_attr_value(user_entry, 'title'),
                'location': get_attr_value(user_entry, 'l'),
                'department': get_attr_value(user_entry, 'department'),
                'company': get_attr_value(user_entry, 'company')
            })

    return items, total_pages

@app.route('/api/dashboard_list/<category>')
@require_auth
def api_dashboard_list(category):
    # Mapeia a categoria da API para a permissão de visualização necessária
    category_to_permission = {
        'active_users': 'can_view_user_stats',
        'disabled_users': 'can_view_user_stats',
        'deactivated_last_week': 'can_view_deactivated_last_week',
        'pending_reactivations': 'can_view_pending_reactivations',
        'pending_deactivations': 'can_view_pending_deactivations',
    }
    required_permission = category_to_permission.get(category)

    # Se a categoria tiver uma permissão associada, verifique-a
    if required_permission and not check_permission(view=required_permission):
        return jsonify({'error': 'Permissão negada para visualizar esta categoria.'}), 403

    try:
        conn = get_read_connection()
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE')
        attributes = ['cn', 'sAMAccountName', 'title', 'l', 'department', 'company']

        page = request.args.get('page', 1, type=int)
        per_page = 20 # Itens por página
        items = []
        total_pages = 0

        if category == 'deactivated_last_week':
            seven_days_ago = datetime.now() - timedelta(days=7)
            usernames = set()
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - Conta '(.+?)' foi desativada por", line)
                        if match:
                            log_time = datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S,%f')
                            if log_time >= seven_days_ago:
                                usernames.add(match.group(2))
            except (FileNotFoundError, Exception) as e:
                logging.error(f"Erro ao processar log para API de desativados: {e}")

            sorted_usernames = sorted(list(usernames))
            items, total_pages = get_paginated_user_details(conn, search_base, sorted_usernames, page, per_page, attributes)

        elif category == 'pending_reactivations':
            schedules = load_schedules()
            today = date.today()
            limit_date = today + timedelta(days=7)

            scheduled_users = []
            for username, date_str in schedules.items():
                try:
                    reactivation_date = date.fromisoformat(date_str)
                    if today <= reactivation_date < limit_date:
                        scheduled_users.append({'sam': username, 'date': reactivation_date})
                except (ValueError, TypeError):
                    continue

            sorted_users = sorted(scheduled_users, key=lambda x: x['date'])
            sam_names = [user['sam'] for user in sorted_users]

            items, total_pages = get_paginated_user_details(conn, search_base, sam_names, page, per_page, attributes)

            # Adiciona a data agendada aos itens retornados
            user_dates = {user['sam']: user['date'].strftime('%d/%m/%Y') for user in sorted_users}
            for item in items:
                item['scheduled_date'] = user_dates.get(item['sam'])

        elif category == 'pending_deactivations':
            schedules = load_disable_schedules()
            today = date.today()
            limit_date = today + timedelta(days=7)

            scheduled_users = []
            for username, date_str in schedules.items():
                try:
                    deactivation_date = date.fromisoformat(date_str)
                    if today <= deactivation_date < limit_date:
                        scheduled_users.append({'sam': username, 'date': deactivation_date})
                except (ValueError, TypeError):
                    continue

            sorted_users = sorted(scheduled_users, key=lambda x: x['date'])
            sam_names = [user['sam'] for user in sorted_users]

            items, total_pages = get_paginated_user_details(conn, search_base, sam_names, page, per_page, attributes)

            user_dates = {user['sam']: user['date'].strftime('%d/%m/%Y') for user in sorted_users}
            for item in items:
                item['scheduled_date'] = user_dates.get(item['sam'])

        elif category in ['active_users', 'disabled_users']:
            base_filter = "(&(objectClass=user)(objectCategory=person)(userPrincipalName=*))"
            category_filters = {
                'active_users': '(!(userAccountControl:1.2.840.113556.1.4.803:=2))',
                'disabled_users': '(userAccountControl:1.2.840.113556.1.4.803:=2)',
            }
            specific_filter = category_filters.get(category)
            search_filter = f"(&{base_filter}{specific_filter})"

            b64_cookie_str = request.args.get('cookie')
            paged_cookie = base64.b64decode(b64_cookie_str) if b64_cookie_str else None

            conn.search(search_base, search_filter, attributes=attributes, paged_size=per_page, paged_cookie=paged_cookie)

            items = [
                {
                    'cn': get_attr_value(e, 'cn'),
                    'sam': get_attr_value(e, 'sAMAccountName'),
                    'title': get_attr_value(e, 'title'),
                    'location': get_attr_value(e, 'l'),
                    'department': get_attr_value(e, 'department'),
                    'company': get_attr_value(e, 'company')
                }
                for e in conn.entries
            ]

            paged_results_control = conn.result.get('controls', {}).get('1.2.840.113556.1.4.319', {})
            cookie_bytes = paged_results_control.get('value', {}).get('cookie')
            next_cookie_b64 = base64.b64encode(cookie_bytes).decode('utf-8') if cookie_bytes else None

            return jsonify({
                'items': items,
                'cookie': next_cookie_b64
            })
        else:
            return jsonify({'error': 'Categoria inválida'}), 404

        return jsonify({
            'items': items,
            'page': page,
            'total_pages': total_pages
        })

    except ldap3.core.exceptions.LDAPInvalidFilterError as e:
        logging.error(f"Erro de filtro LDAP para a categoria '{category}': {e}", exc_info=True)
        return jsonify({'error': f"Filtro LDAP malformado para a categoria: {category}"}), 500
    except Exception as e:
        logging.error(f"Erro na API do dashboard para a categoria '{category}': {e}", exc_info=True)
        return jsonify({'error': 'Falha ao carregar dados.'}), 500

@app.route('/api/search_users_for_group/<group_name>')
@require_auth
@require_api_permission(action='can_manage_groups')
def api_search_users_for_group(group_name):
    query = request.args.get('query', '')
    if not query or len(query) < 3:
        return jsonify([])

    try:
        conn = get_service_account_connection()
        group = get_group_by_name(conn, group_name, attributes=['member'])
        if not group:
            return jsonify({'error': 'Group not found'}), 404

        current_member_dns = {m.lower() for m in group.member.values} if group.member.values else set()
        all_found_users = search_general_users(conn, query)

        user_search_results = [
            {
                'displayName': get_attr_value(user, 'displayName'),
                'sAMAccountName': get_attr_value(user, 'sAMAccountName'),
                'title': get_attr_value(user, 'title'),
                'city': get_attr_value(user, 'l')
            }
            for user in all_found_users
            if user.distinguishedName.value.lower() not in current_member_dns
        ]
        return jsonify(user_search_results)

    except Exception as e:
        logging.error(f"Erro na API de busca de usuários para o grupo '{group_name}': {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/view_group/<group_name>')
@require_auth
@require_permission(action='can_manage_groups')
def view_group(group_name):
    # Create a form instance to pass to the template for CSRF token generation
    form = FlaskForm()
    try:
        conn = get_service_account_connection()
        group = get_group_by_name(conn, group_name, attributes=['cn', 'description'])
        if not group:
            flash(f"Grupo '{group_name}' não encontrado.", 'error')
            return redirect(url_for('group_management'))
        return render_template('view_group.html', group=group, form=form)
    except Exception as e:
        flash(f"Erro ao carregar a página do grupo: {e}", "error")
        logging.error(f"Erro ao carregar a view do grupo '{group_name}': {e}", exc_info=True)
        return redirect(url_for('group_management'))

@app.route('/api/user_groups/<username>')
@require_auth
def api_user_groups(username):
    """
    API endpoint to get the list of groups a user is a member of.
    """
    try:
        conn = get_read_connection()
        user = get_user_by_samaccountname(conn, username, attributes=['memberOf'])

        if not user:
            return jsonify([]) # Retorna lista vazia se o usuário não for encontrado

        group_dns = user.memberOf.values if 'memberOf' in user and user.memberOf.values else []
        if not group_dns:
            return jsonify([])

        groups_details = []
        # Para cada DN de grupo, busca seus detalhes
        for dn in group_dns:
            # Usamos uma busca base no DN do grupo para pegar seus atributos
            conn.search(dn, '(objectClass=group)', BASE, attributes=['cn', 'description'])
            if conn.entries:
                group_entry = conn.entries[0]
                groups_details.append({
                    'cn': get_attr_value(group_entry, 'cn'),
                    'description': get_attr_value(group_entry, 'description')
                })

        # Ordena os grupos pelo nome (cn)
        sorted_groups = sorted(groups_details, key=lambda g: g.get('cn', '').lower())

        return jsonify(sorted_groups)
    except Exception as e:
        logging.error(f"Erro na API de grupos do usuário '{username}': {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/user_details/<username>')
@require_auth
@require_api_permission(action='can_edit')
def api_user_details(username):
    """Retorna um dicionário com os detalhes de um usuário para edição."""
    try:
        conn = get_read_connection()
        # Lista de atributos que podem ser editados no frontend
        attributes_to_fetch = [
            'givenName', 'sn', 'initials', 'displayName', 'description',
            'physicalDeliveryOfficeName', 'telephoneNumber', 'mail', 'wWWHomePage',
            'streetAddress', 'postOfficeBox', 'l', 'st', 'postalCode',
            'homePhone', 'pager', 'mobile', 'facsimileTelephoneNumber',
            'title', 'department', 'company'
        ]

        user = get_user_by_samaccountname(conn, username, attributes=attributes_to_fetch)

        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404

        user_details = {attr: get_attr_value(user, attr) for attr in attributes_to_fetch}

        return jsonify(user_details)

    except Exception as e:
        logging.error(f"Erro ao buscar detalhes para o usuário '{username}': {e}", exc_info=True)
        return jsonify({'error': 'Falha ao buscar detalhes do usuário.'}), 500

@app.route('/api/edit_user/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_edit')
def api_edit_user(username):
    """Atualiza os detalhes de um usuário com base nos dados recebidos via JSON."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Dados não fornecidos.'}), 400

    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, attributes=['*']) # Pega todos os atributos para comparação

        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404

        changes = {}
        # Mapeia os nomes dos campos do frontend/JSON para os atributos do AD
        field_to_attr = {
            'givenName': 'givenName', 'sn': 'sn', 'initials': 'initials',
            'displayName': 'displayName', 'description': 'description', 'physicalDeliveryOfficeName': 'physicalDeliveryOfficeName',
            'telephoneNumber': 'telephoneNumber', 'mail': 'mail', 'wWWHomePage': 'wWWHomePage',
            'streetAddress': 'streetAddress', 'postOfficeBox': 'postOfficeBox', 'l': 'l',
            'st': 'st', 'postalCode': 'postalCode', 'homePhone': 'homePhone',
            'pager': 'pager', 'mobile': 'mobile', 'facsimileTelephoneNumber': 'facsimileTelephoneNumber',
            'title': 'title', 'department': 'department', 'company': 'company'
        }

        changes_to_log = []
        for field, attr_name in field_to_attr.items():
            # Verifica se o campo foi enviado na requisição
            if field in data:
                submitted_value = data[field]
                # Alguns campos de telefone podem precisar de formatação
                if attr_name in ['telephoneNumber', 'homePhone', 'pager', 'mobile', 'facsimileTelephoneNumber']:
                    submitted_value = format_phone_number(submitted_value)

                original_value = get_attr_value(user, attr_name)

                # Adiciona à operação de modificação apenas se o valor mudou
                if submitted_value != original_value:
                    changes[attr_name] = [(ldap3.MODIFY_REPLACE, [submitted_value or ''])]
                    changes_to_log.append(f"{attr_name}: de '{original_value}' para '{submitted_value}'")

        if not changes:
            return jsonify({'success': True, 'message': 'Nenhuma alteração detectada.'})

        conn.modify(user.distinguishedName.value, changes)
        if conn.result['description'] == 'success':
            log_details = "; ".join(changes_to_log)
            logging.info(f"Usuário '{username}' atualizado via API por '{session.get('user_display_name')}'. Detalhes: {log_details}")
            return jsonify({'success': True, 'message': 'Usuário atualizado com sucesso!'})
        else:
            raise Exception(f"Falha do LDAP: {conn.result['message']}")

    except Exception as e:
        logging.error(f"Erro ao editar o usuário '{username}' via API: {e}", exc_info=True)
        return jsonify({'error': f'Falha ao salvar alterações: {e}'}), 500

@app.route('/api/toggle_object_status', methods=['POST'])
@require_auth
@require_api_permission(action='can_disable')
def api_toggle_object_status():
    """Ativa ou desativa um objeto (usuário/computador) no AD."""
    data = request.get_json()
    dn = data.get('dn')
    sam = data.get('sam')  # sAMAccountName, para logs e agendamentos

    if not dn:
        return jsonify({'error': 'DN do objeto é obrigatório.'}), 400

    try:
        conn = get_service_account_connection()
        entry = get_user_by_dn(conn, dn, attributes=['userAccountControl', 'objectClass'])

        if not entry:
            return jsonify({'error': 'Objeto não encontrado.'}), 404

        if 'user' not in entry.objectClass and 'computer' not in entry.objectClass:
            return jsonify({'error': 'Ação aplicável apenas para usuários e computadores.'}), 400

        uac = entry.userAccountControl.value if 'userAccountControl' in entry else 512
        is_disabled = uac & 2

        new_uac, action_message = (uac - 2, "ativada") if is_disabled else (uac + 2, "desativada")

        conn.modify(dn, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(new_uac)])]})

        if conn.result['description'] != 'success':
            raise Exception(f"Erro do LDAP: {conn.result['message']}")

        if action_message == "ativada" and sam:
            schedules = load_schedules()
            if sam in schedules:
                del schedules[sam]
                save_schedules(schedules)
                logging.info(f"Agendamento de reativação para '{sam}' foi removido devido à reativação manual.")

        logging.info(f"Conta '{sam or dn}' foi {action_message} por '{session.get('user_display_name')}'.")

        new_status = "Ativo" if action_message == "ativada" else "Desativado"
        return jsonify({'success': True, 'message': f"Conta {action_message} com sucesso.", 'newStatus': new_status})

    except Exception as e:
        logging.error(f"Erro ao alterar status do objeto '{dn}': {e}", exc_info=True)
        return jsonify({'error': f'Falha ao alterar o status: {e}'}), 500

@app.route('/api/reset_password/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_reset_password')
def api_reset_password(username):
    """Reseta a senha de um usuário para a padrão e retorna a senha em JSON."""
    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, ['distinguishedName'])
        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404

        config = load_config()
        default_password = config.get('DEFAULT_PASSWORD')
        if not default_password:
            return jsonify({'error': 'A senha padrão não está definida na configuração.'}), 500

        conn.extend.microsoft.modify_password(user.distinguishedName.value, default_password)
        conn.modify(user.distinguishedName.value, {'pwdLastSet': [(ldap3.MODIFY_REPLACE, [0])]})

        if conn.result['description'] != 'success':
             raise Exception(f"Erro do LDAP: {conn.result['message']}")

        logging.info(f"A senha para '{username}' foi resetada via API por '{session.get('user_display_name')}'.")
        return jsonify({'success': True, 'message': 'Senha resetada com sucesso.', 'new_password': default_password})

    except Exception as e:
        logging.error(f"Erro ao resetar senha para '{username}' via API: {e}", exc_info=True)
        return jsonify({'error': f'Falha ao resetar a senha: {e}'}), 500

@app.route('/api/delete_object', methods=['DELETE'])
@require_auth
@require_api_permission(action='can_delete_user')
def api_delete_object():
    """Exclui um objeto do AD a partir do seu DN."""
    data = request.get_json()
    dn = data.get('dn')
    name = data.get('name') # Para logging

    if not dn:
        return jsonify({'error': 'DN do objeto é obrigatório.'}), 400

    try:
        conn = get_service_account_connection()
        conn.delete(dn)

        if conn.result['description'] != 'success':
            raise Exception(f"Erro do LDAP: {conn.result['message']}")

        logging.info(f"Objeto '{name or dn}' foi EXCLUÍDO por '{session.get('user_display_name')}'.")
        return jsonify({'success': True, 'message': 'Objeto excluído com sucesso.'})

    except Exception as e:
        logging.error(f"Erro ao excluir objeto '{dn}' via API: {e}", exc_info=True)
        return jsonify({'error': f'Falha ao excluir o objeto: {e}'}), 500

@app.route('/api/disable_user_temp/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_disable')
def api_disable_user_temp(username):
    """Desativa um usuário e agenda sua reativação."""
    data = request.get_json()
    days = data.get('days')

    if not isinstance(days, int) or days <= 0:
        return jsonify({'error': 'O número de dias deve ser um inteiro positivo.'}), 400

    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, ['userAccountControl', 'distinguishedName'])
        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404

        uac = user.userAccountControl.value
        if not (uac & 2): # Se a conta não estiver desativada
            conn.modify(user.distinguishedName.value, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(uac + 2)])]})
            if conn.result['description'] != 'success':
                raise Exception(f"Erro do LDAP ao desativar: {conn.result['message']}")

        schedules = load_schedules()
        reactivation_date = (date.today() + timedelta(days=days))
        schedules[username] = reactivation_date.isoformat()
        save_schedules(schedules)

        logging.info(f"Conta de '{username}' desativada por {days} dias via API por '{session.get('user_display_name')}'. Reativação agendada para {reactivation_date.isoformat()}.")
        return jsonify({'success': True, 'message': f"Usuário desativado. Reativação agendada para {reactivation_date.strftime('%d/%m/%Y')}."})

    except Exception as e:
        logging.error(f"Erro em api_disable_user_temp para '{username}': {e}", exc_info=True)
        return jsonify({'error': f'Falha ao desativar temporariamente: {e}'}), 500

@app.route('/api/schedule_absence/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_disable')
def api_schedule_absence(username):
    """Agenda a desativação e reativação de um usuário."""
    data = request.get_json()
    deactivation_date_str = data.get('deactivation_date')
    reactivation_date_str = data.get('reactivation_date')

    if not deactivation_date_str or not reactivation_date_str:
        return jsonify({'error': 'Datas de desativação and reativação são obrigatórias.'}), 400

    try:
        deactivation_date = date.fromisoformat(deactivation_date_str)
        reactivation_date = date.fromisoformat(reactivation_date_str)

        if deactivation_date >= reactivation_date:
            return jsonify({'error': 'A data de reativação deve ser posterior à de desativação.'}), 400

        # Salva o agendamento de desativação
        disable_schedules = load_disable_schedules()
        disable_schedules[username] = deactivation_date.isoformat()
        save_disable_schedules(disable_schedules)

        # Salva o agendamento de reativação
        reactivation_schedules = load_schedules()
        reactivation_schedules[username] = reactivation_date.isoformat()
        save_schedules(reactivation_schedules)

        logging.info(f"Ausência para '{username}' agendada via API por '{session.get('user_display_name')}'. Desativação em: {deactivation_date_str}, Reativação em: {reactivation_date_str}.")
        return jsonify({'success': True, 'message': 'Ausência agendada com sucesso.'})

    except ValueError:
        return jsonify({'error': 'Formato de data inválido. Use AAAA-MM-DD.'}), 400
    except Exception as e:
        logging.error(f"Erro em api_schedule_absence para '{username}': {e}", exc_info=True)
        return jsonify({'error': f'Falha ao agendar ausência: {e}'}), 500

@app.route('/api/action_permissions')
@require_auth
def api_action_permissions():
    """Retorna as permissões de ação para o usuário logado."""
    try:
        actions = [
            'can_create',
            'can_disable',
            'can_reset_password',
            'can_edit',
            'can_manage_groups',
            'can_delete_user',
            'can_move_user'
        ]
        user_permissions = {action: check_permission(action=action) for action in actions}
        return jsonify(user_permissions)
    except Exception as e:
        logging.error(f"Erro ao verificar permissões de API para o usuário '{session.get('user_display_name')}': {e}", exc_info=True)
        return jsonify({'error': 'Falha ao obter permissões.'}), 500

@app.route('/api/recycle_bin')
@require_auth
def api_recycle_bin():
    """Retorna os objetos da lixeira do AD."""
    if not session.get('recycle_bin_enabled'):
        return jsonify({'error': 'A lixeira não está habilitada.'}), 403

    try:
        conn = get_read_connection()
        config = load_config()
        domain_dn = conn.server.info.other.get('defaultNamingContext')[0]
        deleted_objects_container = f"CN=Deleted Objects,{domain_dn}"

        # Filtro para buscar apenas usuários, grupos e computadores
        search_filter = '(|(objectClass=user)(objectClass=group)(objectClass=computer))'
        conn.search(deleted_objects_container, search_filter, SUBTREE,
                    attributes=['lastKnownParent', 'cn', 'distinguishedName', 'objectClass', 'title', 'whenChanged', 'sAMAccountName'],
                    controls=[('1.2.840.113556.1.4.417', True, None)])

        logging.info(f"Busca na lixeira encontrou {len(conn.entries)} objetos no total.")

        processed_dns = set()
        items = []
        for entry in conn.entries:
            dn = entry.distinguishedName.value
            if not entry.cn.value or dn in processed_dns:
                continue

            original_cn = entry.cn.value
            clean_name = re.split(r'\0A|\n', original_cn)[0].strip()

            obj_class = entry.objectClass.values
            obj_type = 'object'
            if 'user' in obj_class: obj_type = 'user'
            elif 'group' in obj_class: obj_type = 'group'
            elif 'computer' in obj_class: obj_type = 'computer'

            items.append({
                'dn': dn,
                'name': clean_name,
                'type': obj_type,
                'status': 'Excluído',
                'title': entry.title.value if 'title' in entry and entry.title.value else 'N/A',
                'originalOU': get_ou_path(entry.lastKnownParent.value) if 'lastKnownParent' in entry and entry.lastKnownParent.value else 'N/A',
                'deletedDate': entry.whenChanged.value.strftime('%d/%m/%Y %H:%M') if 'whenChanged' in entry and entry.whenChanged.value else 'N/A',
                'sam': entry.sAMAccountName.value if 'sAMAccountName' in entry and entry.sAMAccountName.value else ''
            })
            processed_dns.add(dn)

        # Ordena por nome
        items.sort(key=lambda x: x['name'].lower())

        return jsonify(items)
    except Exception as e:
        logging.error(f"Erro ao buscar itens da lixeira via API: {e}", exc_info=True)
        return jsonify({'error': 'Falha ao buscar itens da lixeira.'}), 500

@app.route('/api/ous')
@require_auth
def api_get_ous():
    """Endpoint da API para listar todas as Unidades Organizacionais."""
    try:
        conn = get_read_connection()
        ous = get_all_ous(conn)

        # Se a lixeira do AD estiver habilitada, adiciona um nó para ela na árvore
        if session.get('recycle_bin_enabled'):
            recycle_bin_node = {
                'text': 'Lixeira',
                'dn': 'recycle_bin',  # Identificador especial para o frontend
                'nodes': [],
                'icon': 'fas fa-trash-alt' # Ícone de lixeira mais claro
            }
            ous.insert(0, recycle_bin_node)

        return jsonify(ous)
    except Exception as e:
        logging.error(f"Erro ao buscar OUs via API: {e}", exc_info=True)
        return jsonify({'error': 'Falha ao buscar Unidades Organizacionais.'}), 500

@app.route('/api/ou_members/<path:ou_dn>')
@require_auth
def api_ou_members(ou_dn):
    """Retorna os membros diretos (filhos) de uma Unidade Organizacional."""
    try:
        conn = get_read_connection()

        # A busca LEVEL recupera apenas os filhos imediatos
        conn.search(search_base=ou_dn,
                    search_filter='(objectClass=*)',
                    search_scope=LEVEL,
                    attributes=['objectClass', 'name', 'ou', 'cn', 'sAMAccountName', 'userAccountControl', 'distinguishedName'])

        items = []
        for entry in conn.entries:
            obj_class = entry.objectClass.values
            item = {'dn': entry.distinguishedName.value}

            if 'organizationalUnit' in obj_class:
                item['type'] = 'ou'
                item['name'] = entry.ou.value if 'ou' in entry else entry.name.value
            elif 'group' in obj_class:
                item['type'] = 'group'
                item['name'] = entry.cn.value if 'cn' in entry else entry.name.value
            elif 'computer' in obj_class:
                item['type'] = 'computer'
                item['name'] = entry.cn.value if 'cn' in entry else entry.name.value
            elif 'user' in obj_class and 'person' in obj_class:
                item['type'] = 'user'
                item['name'] = entry.cn.value if 'cn' in entry else entry.name.value
                item['sam'] = entry.sAMAccountName.value if 'sAMAccountName' in entry else ''
                item['status'] = get_user_status(entry)
            else:
                # Pula outros tipos de objeto ou os manipula conforme necessário
                continue

            items.append(item)

        # Ordena os itens: OUs primeiro, depois grupos, depois usuários, todos em ordem alfabética
        type_order = {'ou': 0, 'group': 1, 'user': 2}
        items.sort(key=lambda x: (type_order.get(x['type'], 99), x['name'].lower()))

        return jsonify(items)
    except ldap3.core.exceptions.LDAPInvalidDnError:
        logging.warning(f"API ou_members chamada com DN inválido: '{ou_dn}'")
        return jsonify({'error': 'O caminho da Unidade Organizacional fornecido é inválido.'}), 400
    except Exception as e:
        logging.error(f"Erro ao buscar membros da OU '{ou_dn}': {e}", exc_info=True)
        return jsonify({'error': f"Falha ao buscar membros da OU '{ou_dn}'."}), 500

@app.route('/api/restore_object', methods=['POST'])
@require_auth
def restore_object():
    """Restaura um objeto da lixeira do AD."""
    if not session.get('recycle_bin_enabled'):
        return jsonify({'error': 'A lixeira não está habilitada ou a sessão é inválida.'}), 403

    data = request.get_json()
    object_dn = data.get('dn')
    if not object_dn:
        return jsonify({'error': 'O DN do objeto é obrigatório.'}), 400

    try:
        conn = get_service_account_connection()

        # Busca o objeto para obter seu 'lastKnownParent' e o RDN
        conn.search(object_dn, '(objectClass=*)', BASE,
                    attributes=['lastKnownParent', 'cn'],
                    controls=[('1.2.840.113556.1.4.417', True, None)])

        if not conn.entries:
            return jsonify({'error': 'Objeto não encontrado na lixeira.'}), 404

        entry = conn.entries[0]
        target_ou_dn = entry.lastKnownParent.value

        # Divide o nome no caractere de nova linha para isolar o nome real
        original_cn = entry.cn.value
        clean_cn = re.split(r'\0A|\n', original_cn)[0].strip()
        new_rdn = f"CN={clean_cn}"

        # Restaura o objeto (movendo-o para sua antiga OU)
        # O AD adiciona um caractere de nova linha (\n) ao CN de objetos excluídos.
        # A operação modify_dn falha se esse caractere não for tratado, retornando NO_OBJECT.
        # A busca funciona, mas a modificação não. A solução, conforme a memória do projeto,
        # é remover ("strip") o caractere de nova linha do DN antes de passá-lo para modify_dn.
        # Embora pareça que o DN ficaria incorreto, este é um workaround conhecido para essa peculiaridade do AD.
        cleaned_object_dn = object_dn.replace('\n', '')
        conn.modify_dn(cleaned_object_dn, new_rdn, new_superior=target_ou_dn)

        if conn.result['description'] != 'success':
            raise Exception(f"Erro do LDAP: {conn.result['message']}")

        # Reativa a conta (remove o estado de desativado, se houver)
        uac_entry = get_user_by_dn(conn, f"{new_rdn},{target_ou_dn}", attributes=['userAccountControl'])
        if uac_entry and 'userAccountControl' in uac_entry:
            uac = uac_entry.userAccountControl.value
            if uac & 2: # Se estiver desativado
                conn.modify(f"{new_rdn},{target_ou_dn}", {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(uac - 2)])]})

        logging.info(f"Objeto '{object_dn}' restaurado por '{session.get('user_display_name')}'.")
        return jsonify({'success': True, 'message': 'Objeto restaurado com sucesso!'})

    except Exception as e:
        logging.error(f"Erro ao restaurar objeto '{object_dn}': {e}", exc_info=True)
        return jsonify({'error': f'Falha ao restaurar o objeto: {e}'}), 500

@app.route('/api/search_ad', methods=['GET'])
@require_auth
def api_search_ad():
    """Busca por usuários e computadores no AD."""
    query = request.args.get('q', '')
    if not query or len(query) < 3:
        return jsonify({'error': 'A busca deve ter no mínimo 3 caracteres.'}), 400

    try:
        conn = get_read_connection()
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE')

        # Escapa caracteres especiais para evitar injeção de filtro LDAP
        safe_query = escape_filter_chars(query)

        # O filtro busca por usuários ou computadores que correspondam à query em vários atributos
        search_filter = f"(&(|(objectClass=user)(objectClass=computer))(|(cn=*{safe_query}*)(displayName=*{safe_query}*)(sAMAccountName=*{safe_query}*)))"

        attributes = ['objectClass', 'name', 'cn', 'sAMAccountName', 'distinguishedName']

        conn.search(search_base, search_filter, SUBTREE, attributes=attributes)

        items = []
        for entry in conn.entries:
            obj_class = entry.objectClass.values
            item = {'dn': entry.distinguishedName.value}

            if 'computer' in obj_class:
                item['type'] = 'computer'
                item['name'] = entry.cn.value if 'cn' in entry else entry.name.value
            elif 'user' in obj_class:
                item['type'] = 'user'
                item['name'] = entry.cn.value if 'cn' in entry else entry.name.value
                item['sam'] = entry.sAMAccountName.value if 'sAMAccountName' in entry else ''
            else:
                continue

            # Adiciona o caminho da OU ao resultado
            item['ou_path'] = get_ou_path(entry.distinguishedName.value)
            items.append(item)

        # Ordena os resultados alfabeticamente pelo nome
        items.sort(key=lambda x: x['name'].lower())

        return jsonify(items)
    except Exception as e:
        logging.error(f"Erro na busca do AD com a query '{query}': {e}", exc_info=True)
        return jsonify({'error': 'Falha ao realizar a busca no Active Directory.'}), 500


@app.route('/api/move_object', methods=['POST'])
@require_auth
@require_api_permission(action='can_move_user')
def move_object():
    """Move um objeto (usuário, grupo) para uma nova Unidade Organizacional."""
    data = request.get_json()
    object_dn = data.get('object_dn')
    target_ou_dn = data.get('target_ou_dn')

    if not object_dn or not target_ou_dn:
        return jsonify({'error': 'DN do objeto e DN da OU de destino são obrigatórios.'}), 400

    try:
        conn = get_service_account_connection()
        new_rdn = object_dn.split(',')[0]

        conn.modify_dn(object_dn, new_rdn, new_superior=target_ou_dn)

        # Se a operação foi um sucesso direto, retorna a confirmação.
        if conn.result['description'] == 'success':
            logging.info(f"Objeto '{object_dn}' movido para '{target_ou_dn}' por '{session.get('user_display_name')}'.")
            return jsonify({'success': True, 'message': 'Objeto movido com sucesso.'})

        # Se falhou, extrai a mensagem de erro para análise.
        error_message = conn.result.get('message', 'Erro desconhecido do LDAP.')
        raise Exception(error_message)

    except Exception as e:
        # Verifica se o erro é o específico "WILL_NOT_PERFORM"
        if "WILL_NOT_PERFORM" in str(e):
            logging.warning(f"Recebido 'WILL_NOT_PERFORM' ao mover '{object_dn}'. Verificando se a operação foi bem-sucedida...")
            try:
                # Tenta buscar o objeto na nova OU para confirmar se a movimentação ocorreu
                new_dn = f"{new_rdn},{target_ou_dn}"
                conn.search(search_base=new_dn, search_filter='(objectClass=*)', search_scope=BASE, attributes=['cn'])

                if conn.entries:
                    logging.info(f"VERIFICAÇÃO BEM-SUCEDIDA: Objeto '{object_dn}' foi movido para '{target_ou_dn}' apesar do erro inicial.")
                    return jsonify({'success': True, 'message': 'Objeto movido com sucesso (verificado).'})
                else:
                    logging.error(f"FALHA NA VERIFICAÇÃO: Objeto '{object_dn}' não encontrado em '{target_ou_dn}' após erro 'WILL_NOT_PERFORM'.")
                    return jsonify({'error': 'O servidor se recusou a realizar a operação e a verificação falhou.'}), 500
            except Exception as verification_e:
                logging.error(f"Erro durante a verificação da movimentação do objeto '{object_dn}': {verification_e}", exc_info=True)
                return jsonify({'error': 'Ocorreu um erro secundário ao verificar a movimentação do objeto.'}), 500

        # Trata outros erros
        logging.error(f"Falha ao mover objeto '{object_dn}': {e}", exc_info=True)

        if isinstance(e, ldap3.core.exceptions.LDAPInvalidDnError):
            return jsonify({'error': 'DN inválido fornecido.'}), 400

        return jsonify({'error': f"Falha do LDAP: {str(e)}"}), 500

@app.route('/add_member/<group_name>', methods=['POST'])
@require_auth
@require_permission(action='can_manage_groups')
def add_member(group_name):
    try:
        user_sam = request.form.get('user_sam')
        if not user_sam:
            flash("Login do usuário não fornecido.", 'error')
            return redirect(url_for('view_group', group_name=group_name))

        conn = get_service_account_connection()
        user_to_add = get_user_by_samaccountname(conn, user_sam, ['distinguishedName'])
        group_to_modify = get_group_by_name(conn, group_name, ['distinguishedName'])

        if user_to_add and group_to_modify:
            conn.extend.microsoft.add_members_to_groups([user_to_add.distinguishedName.value], group_to_modify.distinguishedName.value)
            if conn.result['description'] == 'success':
                flash(f"Usuário '{user_sam}' adicionado ao grupo '{group_name}' com sucesso.", 'success')
                logging.info(f"Usuário '{user_sam}' adicionado ao grupo '{group_name}' por '{session.get('ad_user')}'.")
            else:
                flash(f"Falha ao adicionar usuário: {conn.result['message']}", 'error')
        else:
            flash("Usuário ou grupo não encontrado.", 'error')
    except Exception as e:
        flash(f"Erro ao adicionar usuário ao grupo: {e}", "error")
        logging.error(f"Erro ao adicionar usuário '{user_sam}' ao grupo '{group_name}': {e}", exc_info=True)

    return redirect(url_for('view_group', group_name=group_name))

@app.route('/remove_member/<group_name>/<user_sam>', methods=['POST'])
@require_auth
@require_permission(action='can_manage_groups')
def remove_member(group_name, user_sam):
    try:
        conn = get_service_account_connection()
        user_to_remove = get_user_by_samaccountname(conn, user_sam, ['distinguishedName'])
        group_to_modify = get_group_by_name(conn, group_name, ['distinguishedName'])

        if user_to_remove and group_to_modify:
            conn.extend.microsoft.remove_members_from_groups([user_to_remove.distinguishedName.value], group_to_modify.distinguishedName.value)
            if conn.result['description'] == 'success':
                flash(f"Usuário '{user_sam}' removido do grupo '{group_name}' com sucesso.", 'success')
                logging.info(f"Usuário '{user_sam}' removido do grupo '{group_name}' por '{session.get('ad_user')}'.")
            else:
                flash(f"Falha ao remover usuário: {conn.result['message']}", 'error')
        else:
            flash("Usuário ou grupo não encontrado.", 'error')
    except Exception as e:
        flash(f"Erro ao remover usuário do grupo: {e}", "error")
        logging.error(f"Erro ao remover usuário '{user_sam}' do grupo '{group_name}': {e}", exc_info=True)

    return redirect(url_for('view_group', group_name=group_name))

@app.route('/add_member_temp/<group_name>', methods=['POST'])
@require_auth
@require_permission(action='can_manage_groups')
def add_member_temp(group_name):
    try:
        days = int(request.args.get('days'))
        user_sam = request.form.get('user_sam')

        if days <= 0 or not user_sam:
            flash("Informações inválidas para adição temporária.", 'error')
            return redirect(url_for('view_group', group_name=group_name))

        conn = get_service_account_connection()
        user_to_add = get_user_by_samaccountname(conn, user_sam, ['distinguishedName'])
        group_to_modify = get_group_by_name(conn, group_name, ['distinguishedName'])

        if user_to_add and group_to_modify:
            # Adiciona o usuário imediatamente
            conn.extend.microsoft.add_members_to_groups([user_to_add.distinguishedName.value], group_to_modify.distinguishedName.value)
            if conn.result['description'] == 'success':
                # Agenda a remoção
                schedules = load_group_schedules()
                revert_date = (date.today() + timedelta(days=days)).isoformat()
                schedule_entry = {
                    'user_sam': user_sam,
                    'group_name': group_name,
                    'revert_action': 'remove',
                    'revert_date': revert_date
                }
                schedules.append(schedule_entry)
                save_group_schedules(schedules)

                flash(f"Usuário '{user_sam}' adicionado ao grupo '{group_name}' por {days} dias.", 'success')
                logging.info(f"Usuário '{user_sam}' adicionado temporariamente ao grupo '{group_name}' por '{session.get('ad_user')}'. Reversão em {revert_date}.")
            else:
                flash(f"Falha ao adicionar usuário: {conn.result['message']}", 'error')
        else:
            flash("Usuário ou grupo não encontrado.", 'error')

    except Exception as e:
        flash(f"Erro na adição temporária: {e}", 'error')
        logging.error(f"Erro ao adicionar temporariamente o usuário '{request.form.get('user_sam')}' ao grupo '{group_name}': {e}", exc_info=True)

    return redirect(url_for('view_group', group_name=group_name))

@app.route('/remove_member_temp/<group_name>/<user_sam>', methods=['POST'])
@require_auth
@require_permission(action='can_manage_groups')
def remove_member_temp(group_name, user_sam):
    try:
        days = int(request.args.get('days'))
        if days <= 0:
            flash("O número de dias deve ser positivo.", 'error')
            return redirect(url_for('view_group', group_name=group_name))

        conn = get_service_account_connection()
        user_to_remove = get_user_by_samaccountname(conn, user_sam, ['distinguishedName'])
        group_to_modify = get_group_by_name(conn, group_name, ['distinguishedName'])

        if user_to_remove and group_to_modify:
            # Remove o usuário imediatamente
            conn.extend.microsoft.remove_members_from_groups([user_to_remove.distinguishedName.value], group_to_modify.distinguishedName.value)
            if conn.result['description'] == 'success':
                # Agenda a adição de volta
                schedules = load_group_schedules()
                revert_date = (date.today() + timedelta(days=days)).isoformat()
                schedule_entry = {
                    'user_sam': user_sam,
                    'group_name': group_name,
                    'revert_action': 'add',
                    'revert_date': revert_date
                }
                schedules.append(schedule_entry)
                save_group_schedules(schedules)

                flash(f"Usuário '{user_sam}' removido do grupo '{group_name}' por {days} dias.", 'success')
                logging.info(f"Usuário '{user_sam}' removido temporariamente do grupo '{group_name}' por '{session.get('ad_user')}'. Reversão em {revert_date}.")
            else:
                 flash(f"Falha ao remover usuário: {conn.result['message']}", 'error')
        else:
            flash("Usuário ou grupo não encontrado.", 'error')

    except Exception as e:
        flash(f"Erro na remoção temporária: {e}", 'error')
        logging.error(f"Erro ao remover temporariamente o usuário '{user_sam}' do grupo '{group_name}': {e}", exc_info=True)

    return redirect(url_for('view_group', group_name=group_name))

@app.route('/view_user/<username>')
@require_auth
def view_user(username):
    try:
        conn = get_read_connection()
        attributes = ['*', 'msDS-UserPasswordExpiryTimeComputed']
        user = get_user_by_samaccountname(conn, username, attributes=attributes)
        if not user:
            logging.warning(f"Usuário '{session.get('ad_user')}' tentou ver o usuário '{username}' sem sucesso. Motivo: Usuário não encontrado ou permissões insuficientes.")
            flash("Usuário não encontrado ou você não tem permissão para ver os detalhes.", "error")
            return redirect(url_for('manage_users'))
        password_expiry_info = "Não aplicável (senha nunca expira ou não foi possível calcular)."
        if 'msDS-UserPasswordExpiryTimeComputed' in user and user['msDS-UserPasswordExpiryTimeComputed'].value:
            expiry_time_ft = user['msDS-UserPasswordExpiryTimeComputed'].value
            expiry_datetime = filetime_to_datetime(expiry_time_ft)
            if expiry_datetime:
                delta = expiry_datetime - datetime.now(timezone.utc)
                if delta.days >= 0:
                    password_expiry_info = f"Expira em {delta.days} dia(s) (em {expiry_datetime.strftime('%d/%m/%Y')})"
                else:
                    password_expiry_info = f"Expirou há {-delta.days} dia(s) (em {expiry_datetime.strftime('%d/%m/%Y')})"
            elif int(expiry_time_ft) == 9223372036854775807 or int(expiry_time_ft) == 0:
                 password_expiry_info = "A senha está configurada para nunca expirar."

        # Passa ambos os formulários para o template
        form = EditUserForm() # Para os formulários existentes
        delete_form = DeleteUserForm() # Para o modal de exclusão
        return render_template('view_user.html', user=user, form=form, delete_form=delete_form, password_expiry_info=password_expiry_info)
    except Exception as e:
        flash(f"Erro ao buscar detalhes do usuário: {e}", "error")
        logging.error(f"Erro ao buscar detalhes do usuário para {username}: {e}", exc_info=True)
        return redirect(url_for('manage_users'))

@app.route('/toggle_status/<username>', methods=['POST'])
@require_auth
@require_permission(action='can_disable')
def toggle_status(username):
    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, ['userAccountControl', 'distinguishedName'])
        if not user:
            flash("Usuário não encontrado.", "error")
            return redirect(url_for('manage_users'))
        uac = user.userAccountControl.value
        new_uac, action_message = (uac - 2, "ativada") if uac & 2 else (uac + 2, "desativada")

        conn.modify(user.distinguishedName.value, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(new_uac)])]})

        if action_message == "ativada":
            schedules = load_schedules()
            if username in schedules:
                del schedules[username]
                save_schedules(schedules)
                logging.info(f"Agendamento de reativação para '{username}' foi removido devido à reativação manual.")

        logging.info(f"Conta '{username}' foi {action_message} por '{session.get('user_display_name', session.get('ad_user'))}'.")
        flash(f"Conta do usuário foi {action_message} com sucesso.", "success")
    except Exception as e:
        flash(f"Erro ao alterar status da conta: {e}", "error")
        logging.error(f"Erro em toggle_status para {username}: {e}", exc_info=True)
    return redirect(url_for('view_user', username=username))

@app.route('/disable_user_temp/<username>', methods=['POST'])
@require_auth
@require_permission(action='can_disable')
def disable_user_temp(username):
    try:
        days = int(request.args.get('days'))
        if days <= 0:
            flash("O número de dias deve ser positivo.", "error")
            return redirect(url_for('view_user', username=username))

        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, ['userAccountControl', 'distinguishedName'])
        if not user:
            flash("Usuário não encontrado.", "error")
            return redirect(url_for('manage_users'))

        uac = user.userAccountControl.value
        if not (uac & 2):
            conn.modify(user.distinguishedName.value, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(uac + 2)])]})

        schedules = load_schedules()
        reactivation_date = (date.today() + timedelta(days=days)).isoformat()
        schedules[username] = reactivation_date
        save_schedules(schedules)

        logging.info(f"Conta de '{username}' desativada por {days} dias por '{session.get('ad_user')}'. Reativação agendada para {reactivation_date}.")
        flash(f"Conta do usuário desativada com sucesso. A reativação está agendada para {reactivation_date}.", "success")
    except Exception as e:
        flash(f"Erro ao desativar conta temporariamente: {e}", "error")
        logging.error(f"Erro em disable_user_temp para {username}: {e}", exc_info=True)
    return redirect(url_for('view_user', username=username))

@app.route('/schedule_absence/<username>', methods=['POST'])
@require_auth
@require_permission(action='can_disable')
def schedule_absence(username):
    deactivation_date_str = request.form.get('deactivation_date')
    reactivation_date_str = request.form.get('reactivation_date')

    if not deactivation_date_str or not reactivation_date_str:
        flash("Ambas as datas de desativação e reativação são obrigatórias.", "error")
        return redirect(url_for('view_user', username=username))

    try:
        deactivation_date = date.fromisoformat(deactivation_date_str)
        reactivation_date = date.fromisoformat(reactivation_date_str)

        if deactivation_date >= reactivation_date:
            flash("A data de reativação deve ser posterior à data de desativação.", "error")
            return redirect(url_for('view_user', username=username))

        # Salva o agendamento de desativação
        disable_schedules = load_disable_schedules()
        disable_schedules[username] = deactivation_date.isoformat()
        save_disable_schedules(disable_schedules)

        # Salva o agendamento de reativação
        reactivation_schedules = load_schedules()
        reactivation_schedules[username] = reactivation_date.isoformat()
        save_schedules(reactivation_schedules)

        flash(f"Ausência para '{username}' agendada com sucesso.", "success")
        logging.info(f"Ausência para '{username}' agendada por '{session.get('user_display_name')}'. Desativação em: {deactivation_date_str}, Reativação em: {reactivation_date_str}.")

    except ValueError:
        flash("Formato de data inválido.", "error")
    except Exception as e:
        flash(f"Ocorreu um erro ao agendar a ausência: {e}", "error")
        logging.error(f"Erro em schedule_absence para {username}: {e}", exc_info=True)

    return redirect(url_for('view_user', username=username))

@app.route('/delete_user/<username>', methods=['POST'])
@require_auth
@require_permission(action='can_delete_user')
def delete_user(username):
    form = DeleteUserForm()
    if form.validate_on_submit():
        try:
            conn = get_service_account_connection()
            user = get_user_by_samaccountname(conn, username, ['title', 'sAMAccountName', 'distinguishedName'])
            if not user:
                flash("Usuário não encontrado.", "error")
                return redirect(url_for('manage_users'))

            confirm_title = form.confirm_title.data
            confirm_sam = form.confirm_sam.data

            actual_title = get_attr_value(user, 'title') or 'N/A'
            actual_sam = get_attr_value(user, 'sAMAccountName')

            if confirm_title == actual_title and confirm_sam == actual_sam:
                conn.delete(user.distinguishedName.value)
                if conn.result['description'] == 'success':
                    flash(f"Usuário '{username}' foi excluído permanentemente com sucesso.", "success")
                    logging.info(f"Usuário '{username}' foi EXCLUÍDO por '{session.get('user_display_name', session.get('ad_user'))}'.")
                    return redirect(url_for('manage_users'))
                else:
                    flash(f"Falha ao excluir usuário no Active Directory: {conn.result['message']}", "error")
            else:
                flash("A confirmação do cargo ou login falhou. A exclusão foi cancelada.", "error")

        except Exception as e:
            flash(f"Erro ao excluir usuário: {e}", "error")
            logging.error(f"Erro em delete_user para {username}: {e}", exc_info=True)
    else:
        # Se a validação do formulário falhar (ex: CSRF inválido), exibe uma mensagem de erro.
        flash("Erro de validação do formulário. A exclusão foi cancelada.", "danger")

    return redirect(url_for('view_user', username=username))

@app.route('/reset_password/<username>', methods=['POST'])
@require_auth
@require_permission(action='can_reset_password')
def reset_password(username):
    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, ['distinguishedName'])
        if not user:
            flash("Usuário não encontrado.", "error")
            return redirect(url_for('manage_users'))
        config = load_config()
        default_password = config.get('DEFAULT_PASSWORD')
        if not default_password:
            flash("A senha padrão não está definida na configuração.", "error")
            return redirect(url_for('view_user', username=username))

        conn.extend.microsoft.modify_password(user.distinguishedName.value, default_password)
        conn.modify(user.distinguishedName.value, {'pwdLastSet': [(ldap3.MODIFY_REPLACE, [0])]})
        logging.info(f"A senha para '{username}' foi resetada por '{session.get('ad_user')}'.")
        flash(f"Senha do usuário resetada com sucesso. A nova senha temporária é: {default_password}", "success")
    except Exception as e:
        flash(f"Erro ao resetar a senha: {e}", "error")
        logging.error(f"Erro em reset_password para {username}: {e}", exc_info=True)
    return redirect(url_for('view_user', username=username))

@app.route('/edit_user/<username>', methods=['GET', 'POST'])
@require_auth
@require_permission(action='can_edit')
def edit_user(username):
    try:
        conn = get_read_connection() # Alterado para usar a conexão de leitura
        user = get_user_by_samaccountname(conn, username)
        if not user:
            flash("Usuário não encontrado.", "error")
            return redirect(url_for('manage_users'))

        form = EditUserForm()

        editable_fields = {f.name for f in form if f.type not in ('CSRFTokenField', 'SubmitField') and check_permission(field=f.name)}

        # Dynamically remove validators from fields the user cannot edit.
        # This prevents validation errors on required fields that are disabled in the UI.
        if request.method == 'POST':
            for field_name, field in form._fields.items():
                if field_name not in editable_fields and field_name not in ['csrf_token', 'submit']:
                    field.validators = []

        if form.validate_on_submit():
            service_conn = get_service_account_connection()
            changes = {}

            # Mapeamento de campos do formulário para atributos do AD
            field_to_attr = {
                'first_name': 'givenName', 'last_name': 'sn', 'initials': 'initials',
                'display_name': 'displayName', 'description': 'description', 'office': 'physicalDeliveryOfficeName',
                'telephone': 'telephoneNumber', 'email': 'mail', 'web_page': 'wWWHomePage',
                'street': 'streetAddress', 'post_office_box': 'postOfficeBox', 'city': 'l',
                'state': 'st', 'zip_code': 'postalCode', 'home_phone': 'homePhone',
                'pager': 'pager', 'mobile': 'mobile', 'fax': 'facsimileTelephoneNumber',
                'title': 'title', 'department': 'department', 'company': 'company'
            }

            # Itera SOMENTE sobre os campos que o usuário tem permissão para editar.
            # Isso impede que um usuário mal-intencionado envie dados para campos desabilitados.
            for field_name in editable_fields:
                if field_name in field_to_attr:
                    attr_name = field_to_attr[field_name]
                    submitted_value = getattr(form, field_name).data

                    # Formata o número de telefone se for um campo de telefone
                    if attr_name in ['telephoneNumber', 'homePhone', 'pager', 'mobile', 'facsimileTelephoneNumber']:
                        submitted_value = format_phone_number(submitted_value)

                    original_value = get_attr_value(user, attr_name)

                    # Apenas adiciona a alteração se o valor realmente mudou.
                    if submitted_value != original_value:
                        changes[attr_name] = [(ldap3.MODIFY_REPLACE, [submitted_value or ''])]

            if changes:
                changes_to_log = []
                for field_name in editable_fields:
                    if field_name in field_to_attr:
                        attr_name = field_to_attr[field_name]
                        submitted_value = getattr(form, field_name).data
                        if attr_name in ['telephoneNumber', 'homePhone', 'pager', 'mobile', 'facsimileTelephoneNumber']:
                            submitted_value = format_phone_number(submitted_value)
                        original_value = get_attr_value(user, attr_name)
                        if submitted_value != original_value:
                            changes_to_log.append(f"{attr_name}: De '{original_value}' Para '{submitted_value}'")

                service_conn.modify(user.distinguishedName.value, changes)
                if service_conn.result['description'] == 'success':
                    flash('Usuário atualizado com sucesso!', 'success')
                    log_details = "; ".join(changes_to_log)
                    log_message = f"Usuário '{username}' atualizado por '{session.get('user_display_name', session.get('ad_user'))}'. Detalhes: {log_details}"
                    logging.info(log_message)
                else:
                    flash(f"Erro ao atualizar usuário: {service_conn.result['message']}", 'error')
            else:
                flash("Nenhum valor foi alterado.", "info")
            return redirect(url_for('view_user', username=username))

        # Populate form with existing data
        for field in form:
            field_to_attr = {
                'first_name': 'givenName', 'last_name': 'sn', 'initials': 'initials',
                'display_name': 'displayName', 'description': 'description', 'office': 'physicalDeliveryOfficeName',
                'telephone': 'telephoneNumber', 'email': 'mail', 'web_page': 'wWWHomePage',
                'street': 'streetAddress', 'post_office_box': 'postOfficeBox', 'city': 'l',
                'state': 'st', 'zip_code': 'postalCode', 'home_phone': 'homePhone',
                'pager': 'pager', 'mobile': 'mobile', 'fax': 'facsimileTelephoneNumber',
                'title': 'title', 'department': 'department', 'company': 'company'
            }
            attr_name = field_to_attr.get(field.name)
            if attr_name:
                field.data = get_attr_value(user, attr_name)

        return render_template('edit_user.html', form=form, username=username, user_name=get_attr_value(user, 'displayName'), editable_fields=editable_fields)
    except Exception as e:
        flash(f"Ocorreu um erro: {e}", "error")
        logging.error(f"Erro ao editar o usuário {username}: {e}", exc_info=True)
        return redirect(url_for('manage_users'))

# ==============================================================================
# Rotas Apenas para Admin
# ==============================================================================
@app.route('/admin/register', methods=['GET', 'POST'])
def admin_register():
    if load_user() is not None:
        flash('Um usuário administrador já existe.', 'danger')
        return redirect(url_for('admin_login'))
    form = AdminRegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        save_user({'username': form.username.data, 'password_hash': hashed_password})
        flash('Usuário administrador criado com sucesso! Por favor, faça o login.', 'success')
        return redirect(url_for('admin_login'))
    return render_template('admin/register.html', form=form)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    form = AdminLoginForm()
    if form.validate_on_submit():
        admin_user = load_user()
        if admin_user and admin_user['username'] == form.username.data and check_password_hash(admin_user['password_hash'], form.password.data):
            session['master_admin'] = admin_user['username']
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Nome de usuário ou senha do administrador inválidos.', 'danger')
    return render_template('admin/login.html', form=form)

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'master_admin' not in session:
        return redirect(url_for('admin_login'))
    return render_template('admin/dashboard.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('master_admin', None)
    flash('Você foi desconectado do painel de administração.', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin/change_password', methods=['GET', 'POST'])
def admin_change_password():
    if 'master_admin' not in session:
        return redirect(url_for('admin_login'))

    form = AdminChangePasswordForm()
    if form.validate_on_submit():
        admin_user = load_user()
        # Verificar a senha atual
        if check_password_hash(admin_user['password_hash'], form.current_password.data):
            # Gerar o hash da nova senha
            new_hashed_password = generate_password_hash(form.new_password.data)
            admin_user['password_hash'] = new_hashed_password
            save_user(admin_user)
            flash('Sua senha foi alterada com sucesso!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('A senha atual está incorreta.', 'danger')

    return render_template('admin/change_password.html', form=form)

@app.route('/admin/config', methods=['GET', 'POST'])
def config():
    if 'master_admin' not in session:
        return redirect(url_for('admin_login'))

    form = ConfigForm()

    if form.validate_on_submit():
        current_config = load_config()

        new_config = {
            'AD_SERVER': form.ad_server.data,
            'USE_LDAPS': form.use_ldaps.data,
            'AD_DOMAIN': form.ad_domain.data,
            'AD_SEARCH_BASE': form.ad_search_base.data,
            'SSO_ENABLED': form.sso_enabled.data,
            'SERVICE_ACCOUNT_USER': form.service_account_user.data,
        }

        if form.default_password.data:
            new_config['DEFAULT_PASSWORD'] = form.default_password.data
        elif 'DEFAULT_PASSWORD' in current_config:
            new_config['DEFAULT_PASSWORD'] = current_config['DEFAULT_PASSWORD']

        if form.service_account_password.data:
            new_config['SERVICE_ACCOUNT_PASSWORD'] = form.service_account_password.data
        elif 'SERVICE_ACCOUNT_PASSWORD' in current_config:
            new_config['SERVICE_ACCOUNT_PASSWORD'] = current_config['SERVICE_ACCOUNT_PASSWORD']

        save_config(new_config)
        flash('Configuração salva com sucesso!', 'success')
        return redirect(url_for('config'))

    current_config = load_config()
    form.ad_server.data = current_config.get('AD_SERVER')
    form.use_ldaps.data = current_config.get('USE_LDAPS', False)
    form.ad_domain.data = current_config.get('AD_DOMAIN')
    form.ad_search_base.data = current_config.get('AD_SEARCH_BASE')
    form.sso_enabled.data = current_config.get('SSO_ENABLED', False)
    form.service_account_user.data = current_config.get('SERVICE_ACCOUNT_USER')

    return render_template('admin/config.html', form=form)

@app.route('/admin/logs', methods=['GET', 'POST'])
def admin_logs():
    if 'master_admin' not in session:
        return redirect(url_for('admin_login'))

    search_form = LogSearchForm()
    log_content = []

    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        # Log improvement: Capture more details and make them searchable
        log_entries = []
        for line in all_lines:
            match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - (.*)", line)
            if match:
                log_entries.append({"timestamp": match.group(1), "message": match.group(2)})

        query = search_form.search_query.data
        if search_form.validate_on_submit() and query:
            log_entries = [entry for entry in log_entries if query.lower() in entry['message'].lower()]

        # Reverse for chronological order (newest first)
        log_content = list(reversed(log_entries))

    except FileNotFoundError:
        flash("Arquivo de log não encontrado.", "warning")
    except Exception as e:
        flash(f"Erro ao ler o arquivo de log: {e}", "error")

    return render_template('admin/logs.html', logs=log_content, search_form=search_form)

@app.route('/admin/permissions', methods=['GET', 'POST'])
def permissions():
    if 'master_admin' not in session:
        return redirect(url_for('admin_login'))

    search_form = GroupSearchForm()
    permissions_form = FlaskForm()
    groups = []

    available_fields = {
        'first_name': 'Nome', 'last_name': 'Sobrenome', 'initials': 'Iniciais',
        'display_name': 'Nome de Exibição', 'description': 'Descrição', 'office': 'Escritório',
        'telephone': 'Telefone Principal', 'email': 'E-mail', 'web_page': 'Página da Web',
        'street': 'Rua', 'post_office_box': 'Caixa Postal', 'city': 'Cidade',
        'state': 'Estado/Província', 'zip_code': 'CEP', 'home_phone': 'Telefone Residencial',
        'pager': 'Pager', 'mobile': 'Celular', 'fax': 'Fax', 'title': 'Cargo',
        'department': 'Departamento', 'company': 'Empresa'
    }

    try:
        conn = get_service_account_connection()
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE')

        if search_form.validate_on_submit() and search_form.submit.data:
            query = search_form.search_query.data
            search_filter = f"(&(objectClass=group)(cn=*{query}*))"
            conn.search(search_base, search_filter, attributes=['cn'])
            groups = sorted([g.cn.value for g in conn.entries])
            if not groups:
                flash(f"Nenhum grupo encontrado com o nome '{query}'.", "info")

        if permissions_form.validate_on_submit() and request.form.get('save_permissions'):
            permissions_data = load_permissions()
            searched_groups = request.form.getlist('searched_groups')
            for group in searched_groups:
                perm_type = request.form.get(f'{group}_perm_type')
                if perm_type == 'full':
                    permissions_data[group] = {'type': 'full'}
                elif perm_type == 'custom':
                    actions = {
                        'can_create': f'{group}_can_create' in request.form,
                        'can_disable': f'{group}_can_disable' in request.form,
                        'can_reset_password': f'{group}_can_reset_password' in request.form,
                        'can_edit': f'{group}_can_edit' in request.form,
                        'can_manage_groups': f'{group}_can_manage_groups' in request.form,
                        'can_delete_user': f'{group}_can_delete_user' in request.form,
                        'can_move_user': f'{group}_can_move_user' in request.form,
                    }
                    views = {
                        'can_export_data': f'{group}_can_export_data' in request.form,
                        'can_view_user_stats': f'{group}_can_view_user_stats' in request.form,
                        'can_view_deactivated_last_week': f'{group}_can_view_deactivated_last_week' in request.form,
                        'can_view_pending_reactivations': f'{group}_can_view_pending_reactivations' in request.form,
                        'can_view_pending_deactivations': f'{group}_can_view_pending_deactivations' in request.form,
                        'can_view_expiring_passwords': f'{group}_can_view_expiring_passwords' in request.form,
                    }
                    fields = [field for field in available_fields if f'{group}_field_{field}' in request.form]
                    permissions_data[group] = {'type': 'custom', 'actions': actions, 'fields': fields, 'views': views}
                elif perm_type == 'none':
                     permissions_data[group] = {'type': 'none'}

            save_permissions(permissions_data)
            flash('Permissões salvas com sucesso!', 'success')
            search_query = request.form.get('search_query_hidden', '')
            # Re-run the search after saving
            if search_query:
                 search_filter = f"(&(objectClass=group)(cn=*{search_query}*))"
                 conn.search(search_base, search_filter, attributes=['cn'])
                 groups = sorted([g.cn.value for g in conn.entries])


        permissions_data = load_permissions()
        return render_template(
            'admin/permissions.html',
            search_form=search_form,
            permissions_form=permissions_form,
            groups=groups,
            permissions=permissions_data,
            available_fields=available_fields
        )

    except Exception as e:
        flash(f"Erro ao carregar a página de permissões: {e}", "error")
        logging.error(f"Erro em /admin/permissions: {e}", exc_info=True)
        return redirect(url_for('admin_dashboard'))

# ==============================================================================
# Funções do Dashboard
# ==============================================================================
def get_dashboard_stats(conn):
    stats = {'enabled_users': 0, 'disabled_users': 0}
    if not conn:
        return stats
    config = load_config()
    search_base = config.get('AD_SEARCH_BASE')
    if not search_base: return stats
    try:
        user_filter = '(&(objectClass=user)(objectCategory=person))'
        entry_generator = conn.extend.standard.paged_search(search_base, user_filter, attributes=['userAccountControl'], paged_size=500)
        user_count = 0
        for entry in entry_generator:
            user_count += 1
            attributes = entry.get('attributes', {})
            uac = attributes.get('userAccountControl')
            if uac and (int(uac) & 2):
                stats['disabled_users'] += 1
            else:
                stats['enabled_users'] += 1
        logging.info(f"Dashboard: contagem de usuários ativos/desativados processou {user_count} entradas.")
    except Exception as e:
        logging.error(f"Erro ao buscar estatísticas do dashboard: {e}", exc_info=True)
    return stats

def get_deactivated_last_week():
    """Conta usuários desativados na última semana a partir do log."""
    count = 0
    seven_days_ago = datetime.now() - timedelta(days=7)
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - Conta '(.+?)' foi desativada por", line)
                if match:
                    log_time = datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S,%f')
                    if log_time >= seven_days_ago:
                        count += 1
    except FileNotFoundError:
        logging.warning("Arquivo de log não encontrado ao verificar desativações da última semana.")
    except Exception as e:
        logging.error(f"Erro ao ler log para desativações da última semana: {e}", exc_info=True)
    return count

def get_pending_reactivations(days=7):
    schedules = load_schedules()
    count = 0
    today = date.today()
    limit_date = today + timedelta(days=days)
    for username, date_str in schedules.items():
        try:
            reactivation_date = date.fromisoformat(date_str)
            if today <= reactivation_date < limit_date:
                count += 1
        except (ValueError, TypeError):
            continue
    return count

def get_pending_deactivations(days=7):
    """Conta o número de desativações agendadas para os próximos X dias."""
    schedules = load_disable_schedules()
    count = 0
    today = date.today()
    limit_date = today + timedelta(days=days)
    for username, date_str in schedules.items():
        try:
            deactivation_date = date.fromisoformat(date_str)
            if today <= deactivation_date < limit_date:
                count += 1
        except (ValueError, TypeError):
            continue
    return count

def get_expiring_passwords(conn, days=15):
    expiring_users = []
    if not conn:
        return expiring_users
    config = load_config()
    search_base = config.get('AD_SEARCH_BASE')
    if not search_base: return expiring_users
    try:
        search_filter = "(&(objectClass=user)(objectCategory=person)(!(userAccountControl:1.2.840.113556.1.4.803:=2))(!(userAccountControl:1.2.840.113556.1.4.803:=65536)))"
        attributes = ['cn', 'sAMAccountName', 'msDS-UserPasswordExpiryTimeComputed', 'title', 'department', 'l']
        entry_generator = conn.extend.standard.paged_search(search_base, search_filter, attributes=attributes, paged_size=1000)
        now_utc = datetime.now(timezone.utc)
        expiration_limit = now_utc + timedelta(days=days)
        for entry in entry_generator:
            attributes = entry.get('attributes', {})
            expiry_time_ft = attributes.get('msDS-UserPasswordExpiryTimeComputed')
            if expiry_time_ft:
                expiry_datetime = filetime_to_datetime(expiry_time_ft)
                if expiry_datetime and now_utc < expiry_datetime < expiration_limit:
                    delta = expiry_datetime - now_utc
                    expiring_users.append({
                        'cn': attributes.get('cn'),
                        'sam': attributes.get('sAMAccountName'),
                        'expires_in_days': delta.days + 1,
                        'title': attributes.get('title'),
                        'department': attributes.get('department'),
                        'location': attributes.get('l')
                    })
    except Exception as e:
        logging.error(f"Erro ao buscar senhas expirando: {e}", exc_info=True)
        return []
    return sorted(expiring_users, key=lambda x: x['expires_in_days'])

# ==============================================================================
# Rota de Exportação de Dados
# ==============================================================================
@app.route('/export_ad_data')
@require_auth
@require_permission(view='can_export_data')
def export_ad_data():
    try:
        conn = get_service_account_connection()
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE')
        if not search_base:
            flash("Base de busca do AD não configurada.", "error")
            return redirect(url_for('dashboard'))

        # Filtro para exportar apenas usuários reais com sAMAccountName definido
        search_filter = "(&(objectClass=user)(objectCategory=person)(sAMAccountName=*))"

        # Cabeçalhos e atributos conforme solicitado pelo usuário
        header = [
            'Descrição', 'Email', 'Nome', 'Cargo', 'Sobrenome', 'Empresa', 'Escritório',
            'Departamento', 'Nome de Logon Anterior ao Windows 2000', 'Nome de Logon do Usuário',
            'Nome para Exibição'
        ]
        attributes = [
            'description', 'mail', 'givenName', 'title', 'sn', 'company', 'physicalDeliveryOfficeName',
            'department', 'sAMAccountName', 'userPrincipalName', 'displayName'
        ]

        output = io.StringIO()
        output.write('\ufeff')  # BOM para Excel UTF-8
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)
        writer.writerow(header)

        entry_generator = conn.extend.standard.paged_search(
            search_base=search_base,
            search_filter=search_filter,
            attributes=attributes,
            paged_size=500,
            generator=True
        )

        for entry in entry_generator:
            attrs = entry.get('attributes', {})
            # Pula entradas que não são de usuários (sem sAMAccountName)
            if not attrs.get('sAMAccountName'):
                continue

            # Função auxiliar para obter valor com fallback seguro
            def safe_get(attr_name, default=''):
                val = attrs.get(attr_name)
                return str(val) if val is not None else default

            # Construção da linha na ordem correta
            row = [
                safe_get('description'),
                safe_get('mail'),
                safe_get('givenName'),
                safe_get('title'),
                safe_get('sn'),
                safe_get('company'),
                safe_get('physicalDeliveryOfficeName'),
                safe_get('department'),
                safe_get('sAMAccountName'),
                safe_get('userPrincipalName'),
                safe_get('displayName')
            ]

            writer.writerow(row)

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv; charset=utf-8-sig",
            headers={"Content-Disposition": "attachment;filename=export_ad_data.csv"}
        )

    except Exception as e:
        logging.error(f"Erro na exportação de dados: {e}", exc_info=True)
        flash("Erro ao gerar exportação. Verifique os logs.", "error")
        return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)