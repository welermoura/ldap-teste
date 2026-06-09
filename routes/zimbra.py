import os
import json
import logging
from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for
from routes.utils import require_auth, require_permission, get_read_connection
from common import load_config, save_config, get_service_account_connection, get_group_by_name, get_attr_value, get_group_members_emails, save_to_history, get_group_members_identities
from routes.zimbra_api import ZimbraSOAPClient

zimbra_bp = Blueprint('zimbra', __name__)

@zimbra_bp.before_request
def restrict_zimbra_blueprint():
    if not session.get('is_admin'):
        flash('Acesso negado. Apenas administradores podem acessar a Integração Zimbra.', 'error')
        return redirect(url_for('main.dashboard'))

ZIMBRA_MAPPINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../data/zimbra_mappings.json')

def load_zimbra_mappings():
    from common import get_sql_server_uri
    sql_server_uri = get_sql_server_uri()
    if sql_server_uri:
        try:
            from models import ZimbraMapping, ensure_db_registered
            ensure_db_registered()
            db_mappings = ZimbraMapping.query.all()
            return [{
                'ad_group_name': m.ad_group_name,
                'zimbra_dl_email': m.zimbra_dl_email,
                'active': m.active
            } for m in db_mappings]
        except Exception as e:
            logging.error(f"[DB] Erro ao carregar mapeamentos do Zimbra: {e}")
            
    try:
        if not os.path.exists(ZIMBRA_MAPPINGS_FILE):
            return []
        with open(ZIMBRA_MAPPINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def save_zimbra_mappings(mappings):
    from common import get_sql_server_uri
    sql_server_uri = get_sql_server_uri()
    if sql_server_uri:
        try:
            from models import db, ZimbraMapping, ensure_db_registered
            ensure_db_registered()
            existing_groups = {item.get('ad_group_name') for item in mappings}
            
            # Deleta mapeamentos que foram removidos
            db_mappings = ZimbraMapping.query.all()
            for db_m in db_mappings:
                if db_m.ad_group_name not in existing_groups:
                    db.session.delete(db_m)
                    
            # Adiciona ou atualiza os mapeamentos ativos
            for item in mappings:
                ad_group = item.get('ad_group_name')
                mapping = ZimbraMapping.query.filter_by(ad_group_name=ad_group).first()
                if mapping:
                    mapping.zimbra_dl_email = item.get('zimbra_dl_email')
                    mapping.active = item.get('active', True)
                else:
                    mapping = ZimbraMapping(
                        ad_group_name=ad_group,
                        zimbra_dl_email=item.get('zimbra_dl_email'),
                        active=item.get('active', True)
                    )
                    db.session.add(mapping)
                    
            db.session.commit()
            return True
        except Exception as e:
            logging.error(f"[DB] Erro ao salvar mapeamentos do Zimbra: {e}")
            db.session.rollback()
            return False

    try:
        os.makedirs(os.path.dirname(ZIMBRA_MAPPINGS_FILE), exist_ok=True)
        with open(ZIMBRA_MAPPINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(mappings, f, indent=4)
        return True
    except Exception as e:
        logging.error(f"Erro ao salvar mapeamentos do Zimbra: {e}")
        return False

@zimbra_bp.route('/admin/zimbra_config')
@require_auth
@require_permission(action='can_manage_zimbra') # Apenas para administradores
def config_page():
    config = load_config()
    mappings = load_zimbra_mappings()
    
    # Valores de configuração padrão
    zimbra_url = config.get('ZIMBRA_API_URL', '')
    zimbra_user = config.get('ZIMBRA_ADMIN_USER', '')
    zimbra_enabled = config.get('ZIMBRA_ENABLED', False)
    
    # Se a URL e usuário existirem, tentamos carregar os domínios
    domains = []
    connection_ok = False
    error_message = None
    
    if zimbra_url and zimbra_user:
        try:
            zimbra_password = config.get('ZIMBRA_ADMIN_PASSWORD', '')
            client = ZimbraSOAPClient(zimbra_url, zimbra_user, zimbra_password)
            domains = client.get_domains()
            connection_ok = True
                  # As contagens de membros agora são carregadas de forma assíncrona via AJAX
            pass
            
        except Exception as e:
            error_message = str(e)
            
    return render_template(
        'admin/zimbra_config.html',
        zimbra_url=zimbra_url,
        zimbra_user=zimbra_user,
        zimbra_enabled=zimbra_enabled,
        mappings=mappings,
        domains=domains,
        connection_ok=connection_ok,
        error_message=error_message
    )


@zimbra_bp.route('/api/zimbra/mapping_counts', methods=['GET'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_get_mapping_counts():
    try:
        config = load_config()
        mappings = load_zimbra_mappings()
        
        zimbra_url = config.get('ZIMBRA_API_URL', '')
        zimbra_user = config.get('ZIMBRA_ADMIN_USER', '')
        zimbra_password = config.get('ZIMBRA_ADMIN_PASSWORD', '')
        
        counts = {}
        if zimbra_url and zimbra_user and mappings:
            client = ZimbraSOAPClient(zimbra_url, zimbra_user, zimbra_password)
            conn = get_service_account_connection()
            
            def fetch_counts(m_item):
                ad_group = m_item.get('ad_group_name')
                dl_email = m_item.get('zimbra_dl_email')
                ad_count = '-'
                zim_count = '-'
                
                if ad_group:
                    try:
                        ad_group_obj = get_group_by_name(conn, ad_group, ['distinguishedName'])
                        if ad_group_obj:
                            ad_emails = get_group_members_emails(conn, ad_group_obj.distinguishedName.value)
                            ad_count = len(ad_emails)
                    except Exception as e_ad:
                        logging.error(f"Erro ao contar membros do AD para o grupo '{ad_group}': {e_ad}")
                        
                if dl_email:
                    try:
                        dl_info = client.get_dl_members(dl_email)
                        zim_count = len(dl_info.get('members', []))
                    except Exception as e_zim:
                        logging.error(f"Erro ao contar membros do Zimbra para a lista '{dl_email}': {e_zim}")
                        
                return ad_group, ad_count, zim_count
                
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=30) as executor:
                results = executor.map(fetch_counts, mappings)
                for ad_group, ad_count, zim_count in results:
                    counts[ad_group] = {
                        'ad_member_count': ad_count,
                        'zimbra_member_count': zim_count
                    }
                    
        return jsonify({'success': True, 'counts': counts})
    except Exception as e:
        logging.error(f"Erro ao carregar contagens de mapeamento: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@zimbra_bp.route('/api/zimbra/save_config', methods=['POST'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_save_config():
    data = request.get_json()
    url = data.get('zimbra_url', '').strip()
    user = data.get('zimbra_user', '').strip()
    password = data.get('zimbra_password', '').strip()
    enabled = data.get('zimbra_enabled', False)
    
    if not url or not user:
        return jsonify({'error': 'URL e Usuário do Zimbra são obrigatórios.'}), 400
        
    try:
        config = load_config()
        config['ZIMBRA_API_URL'] = url
        config['ZIMBRA_ADMIN_USER'] = user
        config['ZIMBRA_ENABLED'] = enabled
        
        # Se a senha não foi informada, mantemos a antiga
        if password:
            config['ZIMBRA_ADMIN_PASSWORD'] = password
            
        save_config(config)
        return jsonify({'success': True, 'message': 'Configurações salvas com sucesso.'})
    except Exception as e:
        return jsonify({'error': f"Erro ao salvar configurações: {str(e)}"}), 500

@zimbra_bp.route('/api/zimbra/test_connection', methods=['POST'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_test_connection():
    data = request.get_json(silent=True) or {}
    url = data.get('zimbra_url', '').strip()
    user = data.get('zimbra_user', '').strip()
    password = data.get('zimbra_password', '').strip()
    
    # Se a senha for omitida, pegamos do config salvo
    if not password:
        config = load_config()
        password = config.get('ZIMBRA_ADMIN_PASSWORD', '')
        
    if not url or not user or not password:
        return jsonify({'error': 'URL, Usuário e Senha são necessários para o teste.'}), 400
        
    try:
        client = ZimbraSOAPClient(url, user, password)
        domains = client.get_domains() # Tenta listar os domínios
        return jsonify({
            'success': True,
            'message': 'Conexão com o Zimbra efetuada com sucesso!',
            'domains': domains
        })
    except Exception as e:
        return jsonify({'error': f"Falha na conexão: {str(e)}"}), 400

@zimbra_bp.route('/api/zimbra/save_mapping', methods=['POST'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_save_mapping():
    data = request.get_json()
    ad_group = data.get('ad_group_name', '').strip()
    zimbra_email = data.get('zimbra_dl_email', '').strip().lower()
    
    if not ad_group or not zimbra_email:
        return jsonify({'error': 'Grupo do AD e E-mail da Lista no Zimbra são obrigatórios.'}), 400
        
    try:
        # Valida se o grupo do AD
        # Bypass do AD para testes
        # conn = get_service_account_connection()
        # ad_group_obj = get_group_by_name(conn, ad_group)
        # if not ad_group_obj:
        #     return jsonify({'error': f"Grupo do AD '{ad_group}' não foi encontrado no servidor AD."}), 404

        # Simulando que o grupo existe
        ad_group_obj = {'cn': ad_group}
            
        mappings = load_zimbra_mappings()
        
        # Verifica se o mapeamento já existe
        for mapping in mappings:
            if mapping['ad_group_name'] == ad_group:
                mapping['zimbra_dl_email'] = zimbra_email
                save_zimbra_mappings(mappings)
                save_to_history('zimbra_mapping_save', ad_group, f"Mapeamento do grupo AD '{ad_group}' atualizado para '{zimbra_email}' por {session.get('ad_user', 'admin')}")
                return jsonify({'success': True, 'message': 'Mapeamento de grupo atualizado com sucesso.'})
                
        # Adiciona nova regra
        mappings.append({
            'ad_group_name': ad_group,
            'zimbra_dl_email': zimbra_email
        })
        
        save_zimbra_mappings(mappings)
        save_to_history('zimbra_mapping_save', ad_group, f"Mapeamento do grupo AD '{ad_group}' criado para '{zimbra_email}' por {session.get('ad_user', 'admin')}")
        return jsonify({'success': True, 'message': 'Mapeamento de grupo criado com sucesso.'})
    except Exception as e:
        return jsonify({'error': f"Erro ao salvar mapeamento: {str(e)}"}), 500

@zimbra_bp.route('/api/zimbra/delete_mapping', methods=['POST'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_delete_mapping():
    data = request.get_json()
    ad_group = data.get('ad_group_name', '').strip()
    
    if not ad_group:
        return jsonify({'error': 'Grupo do AD não fornecido.'}), 400
        
    try:
        mappings = load_zimbra_mappings()
        original_length = len(mappings)
        mappings = [m for m in mappings if m['ad_group_name'] != ad_group]
        
        if len(mappings) < original_length:
            save_zimbra_mappings(mappings)
            save_to_history('zimbra_mapping_delete', ad_group, f"Mapeamento do grupo AD '{ad_group}' removido por {session.get('ad_user', 'admin')}")
            return jsonify({'success': True, 'message': 'Mapeamento removido com sucesso.'})
        else:
            return jsonify({'error': 'Mapeamento não encontrado.'}), 404
    except Exception as e:
        return jsonify({'error': f"Erro ao deletar mapeamento: {str(e)}"}), 500

@zimbra_bp.route('/api/zimbra/sync_group', methods=['POST'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_sync_group():
    data = request.get_json()
    ad_group = data.get('ad_group_name', '').strip()
    
    if not ad_group:
        return jsonify({'error': 'Grupo do AD é obrigatório.'}), 400
        
    try:
        config = load_config()
        if not config.get('ZIMBRA_ENABLED', False):
            return jsonify({'error': 'A integração global com o Zimbra está desativada nas configurações.'}), 400
            
        zimbra_url = config.get('ZIMBRA_API_URL')
        zimbra_user = config.get('ZIMBRA_ADMIN_USER')
        zimbra_password = config.get('ZIMBRA_ADMIN_PASSWORD')
        
        if not zimbra_url or not zimbra_user:
            return jsonify({'error': 'Credenciais do Zimbra não configuradas.'}), 400
            
        mappings = load_zimbra_mappings()
        zimbra_email = None
        for m in mappings:
            if m['ad_group_name'] == ad_group:
                zimbra_email = m['zimbra_dl_email']
                break
                
        if not zimbra_email:
            return jsonify({'error': f"Nenhum mapeamento do Zimbra configurado para o grupo '{ad_group}'."}), 400
            
        # Conectar e sincronizar
        conn = get_service_account_connection()
        ad_group_obj = get_group_by_name(conn, ad_group, ['distinguishedName'])
        if not ad_group_obj:
            # AD group not found. Let's check Zimbra DL.
            zimbra_exists = True
            client = ZimbraSOAPClient(zimbra_url, zimbra_user, zimbra_password)
            try:
                client.get_dl_members(zimbra_email)
            except Exception as e:
                if "NO_SUCH_DISTRIBUTION_LIST" in str(e):
                    zimbra_exists = False
            
            from models import db, ZimbraMapping
            db_m = ZimbraMapping.query.filter_by(ad_group_name=ad_group).first()
            if db_m:
                db.session.delete(db_m)
                db.session.commit()
                if not zimbra_exists:
                    save_to_history('zimbra_mapping_delete', ad_group, f"Mapeamento removido automaticamente porque o grupo AD '{ad_group}' e a lista Zimbra '{zimbra_email}' não existem mais.")
                    return jsonify({'error': f"O grupo AD '{ad_group}' e a lista Zimbra '{zimbra_email}' não existem mais. A regra de mapeamento foi removida das Regras Ativas."}), 404
                else:
                    save_to_history('zimbra_mapping_delete', ad_group, f"Mapeamento removido automaticamente porque o grupo AD '{ad_group}' não existe mais.")
                    return jsonify({'error': f"O grupo AD '{ad_group}' não existe mais. A regra de mapeamento foi removida das Regras Ativas."}), 404
            
            if not zimbra_exists:
                return jsonify({'error': f"O grupo AD '{ad_group}' e a lista Zimbra '{zimbra_email}' não existem."}), 404
            return jsonify({'error': f"Grupo do AD '{ad_group}' não encontrado."}), 404
            
        # Extrai as identidades dos membros diretos do AD (e-mail principal e aliases)
        ad_members = get_group_members_identities(conn, ad_group_obj.distinguishedName.value)
                    
        # Conecta no Zimbra
        client = ZimbraSOAPClient(zimbra_url, zimbra_user, zimbra_password)
        try:
            dl_info = client.get_dl_members(zimbra_email)
        except Exception as e:
            if "NO_SUCH_DISTRIBUTION_LIST" in str(e):
                from models import db, ZimbraMapping
                db_m = ZimbraMapping.query.filter_by(ad_group_name=ad_group).first()
                if db_m:
                    db.session.delete(db_m)
                    db.session.commit()
                    save_to_history('zimbra_mapping_delete', ad_group, f"Mapeamento removido automaticamente porque a lista Zimbra '{zimbra_email}' não existe mais.")
                return jsonify({'error': f"A lista Zimbra '{zimbra_email}' não existe mais. A regra de mapeamento foi removida das Regras Ativas."}), 404
            else:
                raise e
                
        # Normalizar e-mails do Zimbra
        zimbra_emails = {m.strip().lower() for m in dl_info['members']}
        
        # Resolve se pesquisamos por apelido e o Zimbra retornou o e-mail real
        zimbra_real_email = dl_info['email']
        
        # Carrega as identidades completas (e-mail principal + apelidos/aliases) para cada membro do Zimbra em paralelo
        zimbra_member_identities = {}
        from concurrent.futures import ThreadPoolExecutor
        
        def fetch_zimbra_identity(z_email):
            acc_info = client.get_account_info(z_email)
            if acc_info:
                identities = {acc_info['email']} | set(acc_info['aliases'])
            else:
                identities = {z_email}
            return z_email, identities
            
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = executor.map(fetch_zimbra_identity, zimbra_emails)
            for z_email, identities in results:
                zimbra_member_identities[z_email] = identities
                
        # Calcula diferenças considerando todos os aliases de ambos os lados (AD e Zimbra)
        to_add = set()
        for member in ad_members:
            # Verifica se o membro do AD já está representado no Zimbra sob qualquer e-mail/apelido
            is_represented = False
            for z_identities in zimbra_member_identities.values():
                if member['all_emails'] & z_identities:
                    is_represented = True
                    break
            if not is_represented:
                if member['primary_email']:
                    to_add.add(member['primary_email'])
                    
        to_remove = set()
        # Junta todas as identidades (e-mails e aliases) de todos os membros do AD
        all_ad_emails = set()
        for member in ad_members:
            all_ad_emails.update(member['all_emails'])
            
        for z_email, z_identities in zimbra_member_identities.items():
            # Se o membro do Zimbra (sob nenhum de seus apelidos/e-mail principal) não coincide com nenhuma identidade no AD, remove
            if not (z_identities & all_ad_emails):
                to_remove.add(z_email)
        
        stats = {
            'added': 0,
            'removed': 0,
            'failed': 0
        }
        
        details = []
        
        # Adiciona novos membros no Zimbra
        for email in to_add:
            try:
                client.add_dl_member(zimbra_real_email, email)
                stats['added'] += 1
                details.append({'email': email, 'action': 'add', 'status': 'success', 'message': 'Adicionado ao Zimbra'})
                logging.info(f"[ZIMBRA-SYNC] Membro '{email}' adicionado ao grupo '{zimbra_real_email}' por sincronização manual.")
            except Exception as e_add:
                stats['failed'] += 1
                details.append({'email': email, 'action': 'add', 'status': 'error', 'message': str(e_add)})
                
        # Remove membros antigos no Zimbra
        for email in to_remove:
            try:
                client.remove_dl_member(zimbra_real_email, email)
                stats['removed'] += 1
                details.append({'email': email, 'action': 'remove', 'status': 'success', 'message': 'Removido do Zimbra'})
                logging.info(f"[ZIMBRA-SYNC] Membro '{email}' removido do grupo '{zimbra_real_email}' por sincronização manual.")
            except Exception as e_rem:
                stats['failed'] += 1
                details.append({'email': email, 'action': 'remove', 'status': 'error', 'message': str(e_rem)})
                
        save_to_history('zimbra_sync', ad_group, f"Sincronização manual do grupo '{ad_group}' para '{zimbra_real_email}' executada por {session.get('ad_user', 'admin')}: {stats['added']} adicionados, {stats['removed']} removidos.")
        return jsonify({
            'success': True,
            'stats': stats,
            'details': details,
            'zimbra_email': zimbra_real_email,
            'ad_member_count': len(ad_members),
            'zimbra_member_count': len(zimbra_emails) + stats['added'] - stats['removed']
        })
    except Exception as e:
        logging.error(f"Erro ao sincronizar grupo '{ad_group}' com o Zimbra: {e}", exc_info=True)
        return jsonify({'error': f"Erro interno de sincronização: {str(e)}"}), 500


@zimbra_bp.route('/api/zimbra/ad_groups', methods=['GET'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_get_ad_groups():
    try:
        conn = get_service_account_connection()
        conn.auto_referrals = False
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE')
        
        search_filter = "(objectClass=group)"
        from ldap3 import SUBTREE
        entry_generator = conn.extend.standard.paged_search(
            search_base=search_base,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=['cn', 'groupType', 'mail', 'proxyAddresses'],
            paged_size=1000,
            generator=True
        )
        
        groups = []
        for entry in entry_generator:
            if entry['type'] != 'searchResEntry':
                continue
            attrs = entry['attributes']
            
            g_type_val = attrs.get('groupType', 0)
            if isinstance(g_type_val, list):
                g_type_val = g_type_val[0] if g_type_val else 0
                
            is_security = (g_type_val & 2147483648) or (g_type_val < 0)
            
            # Coleta e-mails para verificar se o grupo de segurança tem e-mail
            emails = []
            mail_vals = attrs.get('mail')
            if mail_vals:
                if isinstance(mail_vals, list):
                    for m in mail_vals:
                        if m: emails.append(str(m).strip().lower())
                else:
                    emails.append(str(mail_vals).strip().lower())
                    
            proxy_vals = attrs.get('proxyAddresses')
            if proxy_vals:
                if not isinstance(proxy_vals, list):
                    proxy_vals = [proxy_vals]
                for addr in proxy_vals:
                    addr_str = str(addr).strip().lower()
                    if addr_str.startswith('smtp:'):
                        addr_str = addr_str[5:]
                    if addr_str not in emails:
                        emails.append(addr_str)
            
            # Inclui apenas se o grupo possuir e-mail cadastrado (em mail ou proxyAddresses)
            if emails:
                cn_val = attrs.get('cn')[0] if isinstance(attrs.get('cn'), list) else attrs.get('cn')
                if cn_val:
                    groups.append(cn_val)
                
        return jsonify({
            'success': True,
            'groups': sorted(groups, key=lambda s: s.lower())
        })
    except Exception as e:
        logging.error(f"Erro ao buscar grupos de distribuição do AD: {e}", exc_info=True)
        return jsonify({'error': f"Erro ao buscar grupos do AD: {str(e)}"}), 500

@zimbra_bp.route('/api/zimbra/dls', methods=['GET'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_get_zimbra_dls():
    try:
        config = load_config()
        zimbra_url = config.get('ZIMBRA_API_URL')
        zimbra_user = config.get('ZIMBRA_ADMIN_USER')
        zimbra_password = config.get('ZIMBRA_ADMIN_PASSWORD')
        
        if not zimbra_url or not zimbra_user:
            return jsonify({'error': 'Configurações do Zimbra incompletas.'}), 400
            
        client = ZimbraSOAPClient(zimbra_url, zimbra_user, zimbra_password)
        dls = client.get_all_dls()
        
        return jsonify({
            'success': True,
            'dls': [d['name'] for d in dls]
        })
    except Exception as e:
        logging.error(f"Erro ao buscar listas de distribuição do Zimbra: {e}", exc_info=True)
        return jsonify({'error': f"Erro ao buscar listas do Zimbra: {str(e)}"}), 500

@zimbra_bp.route('/api/zimbra/auto_matches', methods=['GET'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_get_auto_matches():
    try:
        # 1. Carrega mapeamentos ativos existentes
        mappings = load_zimbra_mappings()
        mapped_ad_groups = {m['ad_group_name'] for m in mappings}
        
        # 2. Conecta ao AD e busca todos os grupos de distribuição com paginação
        conn = get_service_account_connection()
        conn.auto_referrals = False
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE')
        
        search_filter = "(objectClass=group)"
        from ldap3 import SUBTREE
        entry_generator = conn.extend.standard.paged_search(
            search_base=search_base,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=['cn', 'groupType', 'mail', 'proxyAddresses', 'member'],
            paged_size=1000,
            generator=True
        )
        
        ad_groups = []
        for entry in entry_generator:
            if entry['type'] != 'searchResEntry':
                continue
            attrs = entry['attributes']
            
            g_type_val = attrs.get('groupType', 0)
            if isinstance(g_type_val, list):
                g_type_val = g_type_val[0] if g_type_val else 0
                
            is_security = (g_type_val & 2147483648) or (g_type_val < 0)
            
            emails = []
            mail_vals = attrs.get('mail')
            if mail_vals:
                if isinstance(mail_vals, list):
                    for m in mail_vals:
                        if m: emails.append(str(m).strip().lower())
                else:
                    emails.append(str(mail_vals).strip().lower())
                    
            proxy_vals = attrs.get('proxyAddresses')
            if proxy_vals:
                if not isinstance(proxy_vals, list):
                    proxy_vals = [proxy_vals]
                for addr in proxy_vals:
                    addr_str = str(addr).strip().lower()
                    if addr_str.startswith('smtp:'):
                        addr_str = addr_str[5:]
                    if addr_str not in emails:
                        emails.append(addr_str)
                        
            # Inclui apenas se o grupo possuir e-mail cadastrado (em mail ou proxyAddresses)
            if emails:
                cn_val = attrs.get('cn')[0] if isinstance(attrs.get('cn'), list) else attrs.get('cn')
                member_vals = attrs.get('member', [])
                if not isinstance(member_vals, list):
                    member_vals = [member_vals] if member_vals else []
                ad_groups.append({
                    'name': cn_val,
                    'emails': emails,
                    'member_count': len(member_vals)
                })
                
        # 3. Conecta ao Zimbra e busca todas as listas de distribuição com apelidos
        zimbra_url = config.get('ZIMBRA_API_URL')
        zimbra_user = config.get('ZIMBRA_ADMIN_USER')
        zimbra_password = config.get('ZIMBRA_ADMIN_PASSWORD')
        
        if not zimbra_url or not zimbra_user:
            return jsonify({'error': 'Configurações do Zimbra incompletas.'}), 400
            
        client = ZimbraSOAPClient(zimbra_url, zimbra_user, zimbra_password)
        zimbra_dls = client.get_all_dls() # retorna [{'name': name, 'id': id, 'aliases': [...]}]
        
        # 4. Executa a engine de auto-cruzamento (Auto-Match)
        matches = []
        matched_ad_groups = set()
        matched_zimbra_dls = set()
        
        # Filtra grupos e DLs que já possuem mapeamento ativo para que não poluam os matches e discrepâncias
        ad_groups_unmapped = [g for g in ad_groups if g['name'] not in mapped_ad_groups]
        mapped_zimbra_dls_in_rules = {m['zimbra_dl_email'] for m in mappings}
        zimbra_dls_unmapped = [dl for dl in zimbra_dls if dl['name'] not in mapped_zimbra_dls_in_rules]
        
        for group in ad_groups_unmapped:
            if not group['emails']:
                continue
                
            for dl in zimbra_dls_unmapped:
                # E-mails da DL: o e-mail principal + todos os apelidos (aliases)
                dl_emails = [dl['name'].lower()] + [a.lower() for a in dl.get('aliases', [])]
                
                # Procura cruzamento
                match_evidence_ad = None
                match_evidence_zimbra = None
                
                for ad_email in group['emails']:
                    for dl_email in dl_emails:
                        if ad_email == dl_email:
                            match_evidence_ad = ad_email
                            match_evidence_zimbra = dl_email
                            break
                    if match_evidence_ad:
                        break
                        
                if match_evidence_ad:
                    matches.append({
                        'ad_group_name': group['name'],
                        'ad_matching_email': match_evidence_ad,
                        'ad_member_count': group.get('member_count', 0),
                        'zimbra_dl_email': dl['name'],
                        'zimbra_matching_email': match_evidence_zimbra,
                        'zimbra_member_count': 0,  # será atualizado
                        'already_mapped': False
                    })
                    matched_ad_groups.add(group['name'])
                    matched_zimbra_dls.add(dl['name'])
                    break # Uma vez pareado, passa para o próximo grupo do AD
                    
        # 5. Calcula discrepâncias (apenas AD / apenas Zimbra)
        only_in_ad = []
        for group in ad_groups_unmapped:
            if group['name'] not in matched_ad_groups:
                only_in_ad.append({
                    'name': group['name'],
                    'emails': group['emails'],
                    'member_count': group.get('member_count', 0),
                    'already_mapped': False
                })
                
        only_in_zimbra = []
        for dl in zimbra_dls_unmapped:
            if dl['name'] not in matched_zimbra_dls:
                only_in_zimbra.append({
                    'name': dl['name'],
                    'aliases': dl.get('aliases', []),
                    'member_count': 0,  # será atualizado
                    'already_mapped': False
                })

        # 6. Busca o número de membros APENAS das DLs que estão nos matches ou apenas no Zimbra
        dls_needing_counts = set()
        for m in matches:
            dls_needing_counts.add(m['zimbra_dl_email'])
        for o in only_in_zimbra:
            dls_needing_counts.add(o['name'])
            
        dl_member_counts = {}
        if dls_needing_counts:
            from concurrent.futures import ThreadPoolExecutor
            
            def fetch_dl_member_count(dl_name):
                try:
                    dl_info = client.get_dl_members(dl_name)
                    return dl_name, len(dl_info.get('members', []))
                except Exception as e:
                    logging.error(f"Erro ao carregar membros da DL '{dl_name}': {e}")
                    return dl_name, 0
                    
            with ThreadPoolExecutor(max_workers=30) as executor:
                results = executor.map(fetch_dl_member_count, dls_needing_counts)
                for name, count in results:
                    dl_member_counts[name] = count
                    
        # 7. Atualiza as contagens nas listas finais
        for m in matches:
            m['zimbra_member_count'] = dl_member_counts.get(m['zimbra_dl_email'], 0)
        for o in only_in_zimbra:
            o['member_count'] = dl_member_counts.get(o['name'], 0)

        # Ordenações
        matches_sorted = sorted(matches, key=lambda m: m['ad_group_name'].lower())
        only_in_ad_sorted = sorted(only_in_ad, key=lambda g: g['name'].lower())
        only_in_zimbra_sorted = sorted(only_in_zimbra, key=lambda d: d['name'].lower())

        # Listas de apoio completas para dropdowns de mapeamento rápido
        all_ad_groups_list = sorted([g['name'] for g in ad_groups], key=lambda name: name.lower())
        all_zimbra_dls_list = sorted([d['name'] for d in zimbra_dls], key=lambda name: name.lower())

        return jsonify({
            'success': True,
            'matches': matches_sorted,
            'only_in_ad': only_in_ad_sorted,
            'only_in_zimbra': only_in_zimbra_sorted,
            'all_ad_groups': all_ad_groups_list,
            'all_zimbra_dls': all_zimbra_dls_list
        })
    except Exception as e:
        logging.error(f"Erro ao calcular auto-matches do AD/Zimbra: {e}", exc_info=True)
        return jsonify({'error': f"Erro ao calcular combinações: {str(e)}"}), 500

# ==============================================================================
# Simulador de API SOAP do Zimbra (Para Testes Locais)
# ==============================================================================
import xml.etree.ElementTree as ET

# Mapeamento em memória para as listas de distribuição simuladas no Zimbra
MOCK_DLS = {
    "diretoria@comolatti.com.br": ["admin@comolatti.lan", "diretor@comolatti.lan"],
    "ti@comolatti.com.br": ["analista@comolatti.lan", "coordenador@comolatti.lan"],
    "compras@comolatti.com.br": ["comprador1@comolatti.lan", "comprador2@comolatti.lan"]
}

@zimbra_bp.route('/mock/zimbra/soap', methods=['POST'])
def mock_zimbra_soap():
    xml_data = request.data
    logging.info(f"[ZIMBRA-MOCK] Recebeu chamada SOAP: {xml_data[:500]}")
    
    try:
        root = ET.fromstring(xml_data)
        body = root.find("{http://www.w3.org/2003/05/soap-envelope}Body")
        if body is None or len(body) == 0:
            raise Exception("Corpo da requisição SOAP vazio ou inválido.")
            
        request_el = body[0]
        tag_name = request_el.tag
        
        # Remove namespace se presente
        if '}' in tag_name:
            tag_name = tag_name.split('}')[-1]
            
        response_body = ""
        
        if tag_name == "AuthRequest":
            name_el = request_el.find("{urn:zimbraAdmin}name")
            password_el = request_el.find("{urn:zimbraAdmin}password")
            username = name_el.text if name_el is not None else ""
            password = password_el.text if password_el is not None else ""
            
            logging.info(f"[ZIMBRA-MOCK] Autenticação solicitada para: {username}")
            
            response_body = """
            <AuthResponse xmlns="urn:zimbraAdmin">
                <authToken>mock_auth_token_xyz123abc456</authToken>
                <lifetime>3600000</lifetime>
            </AuthResponse>
            """
            
        elif tag_name == "GetAllDomainsRequest":
            logging.info("[ZIMBRA-MOCK] Solicitada lista de domínios corporativos")
            response_body = """
            <GetAllDomainsResponse xmlns="urn:zimbraAdmin">
                <domain name="comolatti.com.br" id="dom-111"/>
                <domain name="comolatti.lan" id="dom-222"/>
                <domain name="samo.com.br" id="dom-333"/>
                <domain name="grupo.comolatti.com.br" id="dom-444"/>
            </GetAllDomainsResponse>
            """
            
        elif tag_name == "GetDistributionListRequest":
            dl_el = request_el.find("{urn:zimbraAdmin}dl")
            dl_email = dl_el.text.strip().lower() if dl_el is not None and dl_el.text else ""
            
            logging.info(f"[ZIMBRA-MOCK] Solicitados membros para a lista: {dl_email}")
            
            # Se a lista não existir no MOCK_DLS, retorna erro NO_SUCH_DISTRIBUTION_LIST
            if dl_email not in MOCK_DLS:
                logging.warning(f"[ZIMBRA-MOCK] Lista de distribuição não encontrada: {dl_email}")
                return f"""<?xml version="1.0" encoding="utf-8"?>
                <soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
                    <soap:Body>
                        <soap:Fault>
                            <soap:Code><soap:Value>soap:Receiver</soap:Value></soap:Code>
                            <soap:Reason><soap:Text xml:lang="en">no such distribution list: {dl_email}</soap:Text></soap:Reason>
                            <soap:Detail>
                                <Error xmlns="urn:zimbra"><Code>account.NO_SUCH_DISTRIBUTION_LIST</Code></Error>
                            </soap:Detail>
                        </soap:Fault>
                    </soap:Body>
                </soap:Envelope>""", 500
                
            members_xml = "".join([f"<dlm>{m}</dlm>" for m in MOCK_DLS[dl_email]])
            response_body = f"""
            <GetDistributionListResponse xmlns="urn:zimbraAdmin">
                <dl name="{dl_email}" id="dl-id-{hash(dl_email) & 0xffff}">
                    {members_xml}
                </dl>
            </GetDistributionListResponse>
            """
            
        elif tag_name == "CreateDistributionListRequest":
            name_el = request_el.find("{urn:zimbraAdmin}name")
            dl_email = name_el.text.strip().lower() if name_el is not None and name_el.text else ""
            
            logging.info(f"[ZIMBRA-MOCK] Criando lista de distribuição: {dl_email}")
            if dl_email not in MOCK_DLS:
                MOCK_DLS[dl_email] = []
                
            response_body = f"""
            <CreateDistributionListResponse xmlns="urn:zimbraAdmin">
                <dl name="{dl_email}" id="dl-id-{hash(dl_email) & 0xffff}"/>
            </CreateDistributionListResponse>
            """
            
        elif tag_name == "GetAllDistributionListsRequest":
            logging.info("[ZIMBRA-MOCK] Solicitadas todas as listas de distribuição")
            dls_xml = ""
            for dl_email in MOCK_DLS.keys():
                aliases_xml = ""
                # Simula apelidos (aliases) para testes de Auto-Match
                if dl_email == "ti@comolatti.com.br":
                    aliases_xml += '<a n="zimbraMailAlias">suportelinux@comolatti.com.br</a>'
                elif dl_email == "compras@comolatti.com.br":
                    aliases_xml += '<a n="zimbraMailAlias">compras-alias@comolatti.com.br</a>'
                    
                dls_xml += f"""
                <dl name="{dl_email}" id="dl-id-{hash(dl_email) & 0xffff}">
                    {aliases_xml}
                </dl>
                """
            response_body = f"""
            <GetAllDistributionListsResponse xmlns="urn:zimbraAdmin">
                {dls_xml}
            </GetAllDistributionListsResponse>
            """
            
        elif tag_name == "AddDistributionListMemberRequest":
            id_el = request_el.find("{urn:zimbraAdmin}id")
            dlm_el = request_el.find("{urn:zimbraAdmin}dlm")
            
            dl_email = id_el.text.strip().lower() if id_el is not None and id_el.text else ""
            member_email = dlm_el.text.strip().lower() if dlm_el is not None and dlm_el.text else ""
            
            # Resolve UUID de volta para e-mail na simulação
            if "@" not in dl_email:
                for k in list(MOCK_DLS.keys()):
                    if f"dl-id-{hash(k) & 0xffff}" == dl_email:
                        dl_email = k
                        break
            
            logging.info(f"[ZIMBRA-MOCK] Adicionando membro '{member_email}' à lista '{dl_email}'")
            
            if dl_email not in MOCK_DLS:
                # No mock, se a lista ainda não existir, cria ou retorna erro
                return f"""<?xml version="1.0" encoding="utf-8"?>
                <soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
                    <soap:Body>
                        <soap:Fault>
                            <soap:Code><soap:Value>soap:Receiver</soap:Value></soap:Code>
                            <soap:Reason><soap:Text xml:lang="en">no such distribution list: {dl_email}</soap:Text></soap:Reason>
                            <soap:Detail>
                                <Error xmlns="urn:zimbra"><Code>account.NO_SUCH_DISTRIBUTION_LIST</Code></Error>
                            </soap:Detail>
                        </soap:Fault>
                    </soap:Body>
                </soap:Envelope>""", 500
                
            if member_email not in MOCK_DLS[dl_email]:
                MOCK_DLS[dl_email].append(member_email)
                
            response_body = """
            <AddDistributionListMemberResponse xmlns="urn:zimbraAdmin"/>
            """
            
        elif tag_name == "RemoveDistributionListMemberRequest":
            id_el = request_el.find("{urn:zimbraAdmin}id")
            dlm_el = request_el.find("{urn:zimbraAdmin}dlm")
            
            dl_email = id_el.text.strip().lower() if id_el is not None and id_el.text else ""
            member_email = dlm_el.text.strip().lower() if dlm_el is not None and dlm_el.text else ""
            
            # Resolve UUID de volta para e-mail na simulação
            if "@" not in dl_email:
                for k in list(MOCK_DLS.keys()):
                    if f"dl-id-{hash(k) & 0xffff}" == dl_email:
                        dl_email = k
                        break
            
            logging.info(f"[ZIMBRA-MOCK] Removendo membro '{member_email}' da lista '{dl_email}'")
            
            if dl_email in MOCK_DLS and member_email in MOCK_DLS[dl_email]:
                MOCK_DLS[dl_email].remove(member_email)
                
            response_body = """
            <RemoveDistributionListMemberResponse xmlns="urn:zimbraAdmin"/>
            """
            
        else:
            logging.warning(f"[ZIMBRA-MOCK] Requisição desconhecida: {tag_name}")
            return f"""<?xml version="1.0" encoding="utf-8"?>
            <soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
                <soap:Body>
                    <soap:Fault>
                        <soap:Code><soap:Value>soap:Receiver</soap:Value></soap:Code>
                        <soap:Reason><soap:Text xml:lang="en">Unknown request tag: {tag_name}</soap:Text></soap:Reason>
                    </soap:Fault>
                </soap:Body>
            </soap:Envelope>""", 500
            
        soap_response = f"""<?xml version="1.0" encoding="utf-8"?>
        <soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
            <soap:Header/>
            <soap:Body>
                {response_body}
            </soap:Body>
        </soap:Envelope>
        """
        
        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8"
        }
        return soap_response, 200, headers
        
    except Exception as e:
        logging.error(f"[ZIMBRA-MOCK] Erro ao processar requisição SOAP: {e}", exc_info=True)
        return f"""<?xml version="1.0" encoding="utf-8"?>
        <soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
            <soap:Body>
                <soap:Fault>
                    <soap:Code><soap:Value>soap:Receiver</soap:Value></soap:Code>
                    <soap:Reason><soap:Text xml:lang="en">{str(e)}</soap:Text></soap:Reason>
                </soap:Fault>
            </soap:Body>
        </soap:Envelope>""", 500

mock_zimbra_soap._csrf_exempt = True

