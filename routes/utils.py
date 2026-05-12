from functools import wraps
from flask import session, flash, redirect, url_for, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from common import load_permissions, load_config
from ldap3 import SUBTREE, LEVEL
import logging

# Instância global do Limiter para ser usada em Blueprints
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

def is_authenticated():
    return 'ad_user' in session or 'is_admin' in session

def check_permission(action=None, field=None, view=None):
    if session.get('is_admin'):
        return True
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
        group_norm = group.strip()
        # Tenta buscar com o nome exato e com o nome normalizado (case-insensitive fallback)
        rule = permissions.get(group_norm)
        if not rule:
            # Busca case-insensitive
            for p_key, p_val in permissions.items():
                if p_key.lower() == group_norm.lower():
                    rule = p_val
                    break
        
        if not rule: continue
        
        if rule.get('type') == 'full': return True
        if rule.get('type') == 'custom':
            if action and rule.get('actions', {}).get(action): return True
            if field and field in rule.get('fields', []): return True
            if view and rule.get('views', {}).get(view): return True
    return False

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_authenticated():
            flash("Sua sessão expirou. Por favor, faça login novamente.", "error")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def require_permission(action=None, field=None, view=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not check_permission(action=action, field=field, view=view):
                flash('Você não tem permissão para realizar esta ação.', 'error')
                return redirect(url_for('main.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_api_permission(action=None, field=None, view=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not check_permission(action=action, field=field, view=view):
                return jsonify({'error': 'Acesso negado. Permissão insuficiente.'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Helpers de AD e Utilitários ---

def get_user_status(user_entry):
    if not hasattr(user_entry, 'userAccountControl') or user_entry.userAccountControl is None:
        return "Desconhecido"
    uac = user_entry.userAccountControl.value
    if uac & 2:
        return "Desativado"
    return "Ativo"

def get_attr_value(entry, attr_name, default=""):
    if not hasattr(entry, attr_name) or getattr(entry, attr_name) is None:
        return default
    val = getattr(entry, attr_name).value
    if isinstance(val, list):
        return val[0] if val else default
    return val

def get_read_connection():
    from flask import has_app_context, g
    from common import get_ad_connection
    if has_app_context():
        if 'read_conn' not in g:
            g.read_conn = get_ad_connection(read_only=True)
        return g.read_conn
    return get_ad_connection(read_only=True)

def get_password_reset_error_message(e):
    error_str = str(e)
    if '532' in error_str:
        return "A senha expirou e deve ser alterada."
    elif '533' in error_str:
        return "A conta está desativada."
    elif '701' in error_str:
        return "A conta expirou."
    elif '773' in error_str:
        return "O usuário deve alterar a senha no próximo logon."
    elif '775' in error_str:
        return "A conta está bloqueada."
    elif 'Constraint Violation' in error_str:
        return "A senha não atende aos requisitos de complexidade, histórico ou tamanho mínimo."
    return f"Erro ao alterar senha: {error_str}"

def get_upn_suffix_from_base(base_dn):
    # Ex: OU=Users,DC=empresa,DC=com -> @empresa.com
    parts = base_dn.split(',')
    dc_parts = [p.split('=')[1] for p in parts if p.upper().startswith('DC=')]
    if dc_parts:
        return "@" + ".".join(dc_parts)
    return ""

def get_all_ous(conn):
    """Busca todas as OUs e containers e os retorna em uma estrutura de árvore hierárquica."""
    config = load_config()
    search_base = config.get('AD_SEARCH_BASE')
    if not search_base:
        return []

    # Filtro expandido para garantir que pegamos todos os tipos de containers relevantes
    ldap_filter = "(|(objectClass=organizationalUnit)(objectClass=container)(objectClass=builtinDomain))"

    nodes = {}
    count = 0

    try:
        # Usa paged_search para garantir que todos os resultados sejam retornados, superando o limite de 1000
        entry_generator = conn.extend.standard.paged_search(
            search_base=search_base,
            search_filter=ldap_filter,
            search_scope=SUBTREE,
            attributes=['ou', 'cn', 'distinguishedName', 'objectClass'],
            paged_size=1000,
            generator=True
        )

        for entry in entry_generator:
            if entry['type'] != 'searchResEntry':
                continue

            count += 1
            dn = entry['dn']
            attrs = entry['attributes']

            cn_val = attrs.get('cn')
            if isinstance(cn_val, list): cn_val = cn_val[0] if cn_val else ''

            # Pula o container "ForeignSecurityPrincipals"
            if 'ForeignSecurityPrincipals' in str(cn_val):
                continue

            obj_class = attrs.get('objectClass', [])
            ou_val = attrs.get('ou')
            if isinstance(ou_val, list): ou_val = ou_val[0] if ou_val else ''

            # O nome vem do atributo 'ou' para OUs e 'cn' para Containers/Builtin
            node_name = str(ou_val) if 'organizationalUnit' in obj_class else str(cn_val)

            # Store nodes with lowercase DN keys to handle case-insensitivity of AD
            nodes[dn.lower()] = {
                'text': node_name,
                'dn': dn,
                'nodes': []
            }

        logging.info(f"Total de OUs/Containers recuperados: {count}")

    except Exception as e:
        logging.error(f"Erro durante a busca de OUs (paged_search): {e}", exc_info=True)
        return []

    tree_roots = []
    # Second pass: link nodes together.
    for dn_lower, node in nodes.items():
        # Determine the parent DN by removing the first component of the current DN (lowercase key).
        parts = dn_lower.split(',')
        parent_dn_lower = ','.join(parts[1:]) if len(parts) > 1 else None

        # If the parent DN exists in our dictionary, it's a child of that parent.
        if parent_dn_lower and parent_dn_lower in nodes:
            nodes[parent_dn_lower]['nodes'].append(node)
        # Otherwise, it's a root node in our hierarchy.
        else:
            tree_roots.append(node)

    # Sort the tree and all sub-nodes alphabetically by 'text' for a clean UI.
    def sort_tree_nodes_recursively(node_list):
        node_list.sort(key=lambda x: x['text'].lower())
        for node in node_list:
            if node['nodes']:
                sort_tree_nodes_recursively(node['nodes'])

    sort_tree_nodes_recursively(tree_roots)

    return tree_roots

def search_general_users(conn, query):
    try:
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE', conn.server.info.other['defaultNamingContext'][0])
        safe_query = query.replace('*', '')
        search_filter = f"(&(objectClass=user)(objectCategory=person)(|(displayName=*{safe_query}*)(sAMAccountName=*{safe_query}*)(extensionAttribute4=*{safe_query}*)))"
        attributes_to_get = ['displayName', 'name', 'mail', 'sAMAccountName', 'title', 'l', 'userAccountControl', 'distinguishedName']
        conn.search(search_base, search_filter, SUBTREE, attributes=attributes_to_get)
        return conn.entries
    except Exception as e:
        logging.error(f"Erro ao buscar usuários com a query '{query}': {str(e)}")
        return []

def get_user_by_dn(conn, user_dn, attributes=None):
    """Busca um usuário diretamente pelo seu Distinguished Name."""
    from ldap3 import BASE
    import ldap3
    if attributes is None:
        attributes = ldap3.ALL_ATTRIBUTES
    try:
        conn.search(user_dn, '(objectClass=*)', BASE, attributes=attributes)
        if conn.entries:
            return conn.entries[0]
    except ldap3.core.exceptions.LDAPNoSuchObjectResult:
        return None
    return None

def get_ou_from_dn(dn):
    parts = dn.split(',')
    return ','.join(parts[1:])

def get_ou_path(dn):
    parts = dn.split(',')
    ou_parts = [p.split('=')[1] for p in parts if p.startswith(('OU=', 'CN='))]
    ou_parts.reverse()
    return " > ".join(ou_parts[:-1]) # Remove o nome do próprio usuário do caminho

def get_ou_members(conn, ou_dn):
    """Retorna os membros (usuários, grupos, computadores) e sub-OUs de uma OU."""
    try:
        # 1. Busca Sub-OUs e Containers
        conn.search(ou_dn, '(|(objectClass=organizationalUnit)(objectClass=container))', search_scope=LEVEL, attributes=['ou', 'cn', 'distinguishedName'])
        sub_ous = []
        for entry in conn.entries:
            sub_ous.append({
                'name': get_attr_value(entry, 'ou') or get_attr_value(entry, 'cn'),
                'dn': entry.distinguishedName.value,
                'type': 'ou'
            })

        # 2. Busca Usuários, Grupos e Computadores
        # Filtro para usuários (pessoa), grupos e computadores
        search_filter = '(|(&(objectClass=user)(objectCategory=person))(objectClass=group)(objectClass=computer))'
        # Usamos paged_search caso a OU tenha muitos objetos
        entry_generator = conn.extend.standard.paged_search(
            search_base=ou_dn,
            search_filter=search_filter,
            search_scope=LEVEL,
            attributes=['displayName', 'cn', 'sAMAccountName', 'objectClass', 'distinguishedName', 'title', 'userAccountControl'],
            paged_size=1000,
            generator=True
        )

        members = []
        for entry in entry_generator:
            if entry['type'] != 'searchResEntry': continue
            attrs = entry['attributes']
            obj_classes = attrs.get('objectClass', [])
            
            obj_type = 'user'
            if 'group' in obj_classes:
                obj_type = 'group'
            elif 'computer' in obj_classes:
                obj_type = 'computer'
            
            # Determina o status se for usuário
            status = 'Ativo'
            if obj_type == 'user' or obj_type == 'computer':
                uac = attrs.get('userAccountControl', 0)
                if uac & 2:
                    status = 'Desativado'

            members.append({
                'name': attrs.get('displayName') or attrs.get('cn') or attrs.get('sAMAccountName'),
                'sam': attrs.get('sAMAccountName'),
                'dn': entry['dn'],
                'type': obj_type,
                'status': status,
                'title': attrs.get('title', '')
            })

        # Combina e ordena
        all_members = sorted(sub_ous, key=lambda x: x['name'].lower()) + sorted(members, key=lambda x: x['name'].lower())
        return all_members
    except Exception as e:
        logging.error(f"Erro ao buscar membros da OU {ou_dn}: {e}")
        return []

def get_recycle_bin_items(conn):
    """Busca itens na lixeira do AD (se habilitada)."""
    try:
        config = load_config()
        domain_dn = conn.server.info.other.get('defaultNamingContext')[0]
        deleted_objects_dn = f"CN=Deleted Objects,{domain_dn}"
        
        # Filtro para objetos excluídos
        search_filter = "(isDeleted=TRUE)"
        
        # É necessário o controle LDAP_SERVER_SHOW_DELETED_OID (1.2.840.113556.1.4.417)
        conn.search(
            search_base=deleted_objects_dn,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=['cn', 'displayName', 'sAMAccountName', 'objectClass', 'distinguishedName', 'whenChanged', 'lastKnownParent', 'msDS-LastKnownRDN', 'title'],
            controls=[('1.2.840.113556.1.4.417', True)]
        )
        
        items = []
        from common import filetime_to_datetime
        for entry in conn.entries:
            obj_classes = entry.objectClass.values
            obj_type = 'user' if 'user' in obj_classes else 'group' if 'group' in obj_classes else 'computer' if 'computer' in obj_classes else 'other'
            
            # Data de exclusão aproximada pelo whenChanged
            deleted_date = entry.whenChanged.value.strftime('%d/%m/%Y %H:%M') if entry.whenChanged else 'N/A'
            
            items.append({
                'name': get_attr_value(entry, 'displayName') or get_attr_value(entry, 'cn') or get_attr_value(entry, 'msDS-LastKnownRDN'),
                'sam': get_attr_value(entry, 'sAMAccountName'),
                'dn': entry.distinguishedName.value,
                'type': obj_type,
                'status': 'Excluído',
                'deletedDate': deleted_date,
                'originalOU': get_ou_path(entry.lastKnownParent.value) if 'lastKnownParent' in entry else 'Desconhecida',
                'title': get_attr_value(entry, 'title', '')
            })
            
        return sorted(items, key=lambda x: x['deletedDate'], reverse=True)
    except Exception as e:
        logging.error(f"Erro ao buscar itens da lixeira: {e}")
        return []
