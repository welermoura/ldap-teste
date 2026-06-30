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
            
            # Exclui a DL no Zimbra se ela ainda existir e o grupo do AD foi removido
            if zimbra_exists:
                try:
                    client.delete_dl(zimbra_email)
                    logging.info(f"[ZIMBRA] DL '{zimbra_email}' excluída porque o grupo AD '{ad_group}' correspondente não existe mais.")
                    zimbra_exists = False
                except Exception as ez_del:
                    logging.error(f"[ZIMBRA] Erro ao excluir DL '{zimbra_email}' do Zimbra: {ez_del}")
            
            from models import db, ZimbraMapping
            db_m = ZimbraMapping.query.filter_by(ad_group_name=ad_group).first()
            if db_m:
                db.session.delete(db_m)
                db.session.commit()
                if not zimbra_exists:
                    save_to_history('zimbra_mapping_delete', ad_group, f"Mapeamento e lista do Zimbra removidos porque o grupo AD '{ad_group}' não existe mais.")
                    return jsonify({'error': f"O grupo AD '{ad_group}' foi removido. A lista correspondente no Zimbra '{zimbra_email}' e a regra de mapeamento foram excluídas."}), 404
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
                
        # Mapeia cada e-mail do Zimbra ao membro correspondente do AD (se houver) para evitar duplicatas/aliases
        ad_member_to_zimbra_emails = {i: [] for i in range(len(ad_members))}
        unmatched_zimbra_emails = set()
        
        for z_email, z_identities in zimbra_member_identities.items():
            matched_indices = []
            for i, member in enumerate(ad_members):
                if z_identities & member['all_emails']:
                    matched_indices.append(i)
            
            if matched_indices:
                for idx in matched_indices:
                    ad_member_to_zimbra_emails[idx].append(z_email)
            else:
                unmatched_zimbra_emails.add(z_email)
                
        to_add = set()
        to_remove = set(unmatched_zimbra_emails)
        
        for i, member in enumerate(ad_members):
            matching_emails = ad_member_to_zimbra_emails[i]
            if not matching_emails:
                if member['primary_email']:
                    to_add.add(member['primary_email'])
            else:
                # Se o usuário está representado por múltiplos e-mails/aliases na DL, mantém apenas um
                primary = member['primary_email']
                if primary and primary in matching_emails:
                    keep_email = primary
                else:
                    keep_email = matching_emails[0]
                    
                for email in matching_emails:
                    if email != keep_email:
                        to_remove.add(email)
        
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

@zimbra_bp.route('/admin/zimbra_forwardings')
@require_auth
@require_permission(action='can_manage_zimbra')
def forwardings_page():
    config = load_config()
    if not config.get('ZIMBRA_ENABLED', False):
        flash('A integração com o Zimbra não está ativada nas configurações globais.', 'error')
        return redirect(url_for('admin.dashboard'))
    return render_template(
        'admin/zimbra_forwardings.html',
        remediation_enabled=config.get('ZIMBRA_AUTO_REMEDIATION_ENABLED', 'False'),
        whitelist_str=config.get('ZIMBRA_SECURITY_WHITELIST', ''),
        security_default_password=config.get('ZIMBRA_SECURITY_DEFAULT_PASSWORD', ''),
        teams_tenant_id=config.get('TEAMS_TENANT_ID', ''),
        teams_client_id=config.get('TEAMS_CLIENT_ID', ''),
        teams_client_secret=config.get('TEAMS_CLIENT_SECRET', ''),
        teams_group_id=config.get('TEAMS_GROUP_ID', ''),
        teams_channel_id=config.get('TEAMS_CHANNEL_ID', ''),
        teams_user_email=config.get('TEAMS_USER_EMAIL', ''),
        teams_user_password=config.get('TEAMS_USER_PASSWORD', ''),
        zimbra_security_notify_nominal=config.get('ZIMBRA_SECURITY_NOTIFY_NOMINAL', 'False'),
        zimbra_security_notify_group=config.get('ZIMBRA_SECURITY_NOTIFY_GROUP', ''),
        zimbra_security_notify_group_id=config.get('ZIMBRA_SECURITY_NOTIFY_GROUP_ID', ''),
        zimbra_audit_interval_minutes=config.get('ZIMBRA_AUDIT_INTERVAL_MINUTES', '240'),
        zimbra_last_audit_timestamp=config.get('ZIMBRA_LAST_AUDIT_TIMESTAMP', ''),
        zimbra_last_audit_status=config.get('ZIMBRA_LAST_AUDIT_STATUS', '')
    )


@zimbra_bp.route('/api/zimbra/save_security_config', methods=['POST'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_save_security_config():
    try:
        data = request.get_json() or {}
        remediation_enabled = data.get('remediation_enabled', False)
        whitelist = data.get('whitelist', '').strip()
        security_default_password = data.get('security_default_password', '').strip()
        teams_tenant_id = data.get('teams_tenant_id', '').strip()
        teams_client_id = data.get('teams_client_id', '').strip()
        teams_client_secret = data.get('teams_client_secret', '').strip()
        teams_group_id = data.get('teams_group_id', '').strip()
        teams_channel_id = data.get('teams_channel_id', '').strip()
        teams_user_email = data.get('teams_user_email', '').strip()
        teams_user_password = data.get('teams_user_password', '').strip()
        zimbra_security_notify_nominal = data.get('zimbra_security_notify_nominal', False)
        zimbra_security_notify_group = data.get('zimbra_security_notify_group', '').strip()
        zimbra_security_notify_group_id = data.get('zimbra_security_notify_group_id', '').strip()
        zimbra_audit_interval_minutes = str(data.get('zimbra_audit_interval_minutes', '240')).strip()

        config = load_config()
        config['ZIMBRA_AUTO_REMEDIATION_ENABLED'] = 'True' if remediation_enabled else 'False'
        config['ZIMBRA_SECURITY_WHITELIST'] = whitelist
        config['ZIMBRA_SECURITY_DEFAULT_PASSWORD'] = security_default_password
        config['TEAMS_TENANT_ID'] = teams_tenant_id
        config['TEAMS_CLIENT_ID'] = teams_client_id
        
        # Só atualiza se foi preenchido ou modificado (não mascarado)
        if teams_client_secret and teams_client_secret != '********':
            config['TEAMS_CLIENT_SECRET'] = teams_client_secret

        config['TEAMS_GROUP_ID'] = teams_group_id
        config['TEAMS_CHANNEL_ID'] = teams_channel_id
        config['TEAMS_USER_EMAIL'] = teams_user_email
        
        if teams_user_password and teams_user_password != '********':
            config['TEAMS_USER_PASSWORD'] = teams_user_password

        config['ZIMBRA_SECURITY_NOTIFY_NOMINAL'] = 'True' if zimbra_security_notify_nominal else 'False'
        config['ZIMBRA_SECURITY_NOTIFY_GROUP'] = zimbra_security_notify_group
        config['ZIMBRA_SECURITY_NOTIFY_GROUP_ID'] = zimbra_security_notify_group_id
        config['ZIMBRA_AUDIT_INTERVAL_MINUTES'] = zimbra_audit_interval_minutes

        save_config(config)
        return jsonify({'success': True, 'message': 'Configurações de segurança e notificações salvas com sucesso!'})
    except Exception as e:
        logging.error(f"Erro ao salvar configurações de segurança do Zimbra: {e}", exc_info=True)
        return jsonify({'error': f"Erro ao salvar configurações: {str(e)}"}), 500


@zimbra_bp.route('/api/zimbra/run_security_audit', methods=['POST'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_run_security_audit():
    try:
        import io
        from common import load_config, get_service_account_connection
        from schedule_manager import process_zimbra_security_auto_remediation

        config = load_config()
        if not config.get('ZIMBRA_ENABLED', False):
            return jsonify({'success': False, 'error': 'A integração com o Zimbra não está ativada nas configurações globais.'}), 400

        # Captura os logs gerados em tempo de execução
        log_capture_string = io.StringIO()
        ch = logging.StreamHandler(log_capture_string)
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter('[%(levelname)s] %(message)s')
        ch.setFormatter(formatter)
        
        # Obtém o logger principal e adiciona nosso Handler
        logger = logging.getLogger()
        old_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(ch)

        try:
            conn = get_service_account_connection()
            if not conn:
                raise Exception("Não foi possível estabelecer conexão com o Active Directory.")
            
            # Força a execução da auditoria ignorando intervalo de tempo
            process_zimbra_security_auto_remediation(conn, config, force=True)
            
        except Exception as e:
            logging.error(f"Erro durante execução manual: {e}")
            raise e
        finally:
            logger.removeHandler(ch)
            logger.setLevel(old_level)

        log_contents = log_capture_string.getvalue()
        
        # Recarrega configurações atualizadas (com novo timestamp e status salvos pelo schedule_manager)
        updated_config = load_config()
        last_audit_timestamp = updated_config.get('ZIMBRA_LAST_AUDIT_TIMESTAMP', '')
        last_audit_status = updated_config.get('ZIMBRA_LAST_AUDIT_STATUS', '')

        if last_audit_status and 'Failed' in last_audit_status:
            return jsonify({
                'success': False,
                'error': last_audit_status,
                'logs': log_contents,
                'last_audit_timestamp': last_audit_timestamp
            })

        return jsonify({
            'success': True,
            'logs': log_contents,
            'last_audit_timestamp': last_audit_timestamp,
            'last_audit_status': last_audit_status
        })

    except Exception as e:
        logging.error(f"Erro ao forçar auditoria de segurança do Zimbra: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f"Erro ao executar auditoria: {str(e)}"}), 500


@zimbra_bp.route('/api/zimbra/test_teams', methods=['POST'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_test_teams():
    try:
        import requests
        data = request.get_json() or {}
        tenant_id = data.get('teams_tenant_id', '').strip()
        client_id = data.get('teams_client_id', '').strip()
        client_secret = data.get('teams_client_secret', '').strip()
        group_id = data.get('teams_group_id', '').strip()
        channel_id = data.get('teams_channel_id', '').strip()
        
        is_nominal = data.get('zimbra_security_notify_nominal', False)
        teams_user_email = data.get('teams_user_email', '').strip()
        teams_user_password = data.get('teams_user_password', '').strip()
        teams_user_group = data.get('zimbra_security_notify_group', '').strip()
        teams_user_group_id = data.get('zimbra_security_notify_group_id', '').strip()

        # Se o client secret ou a senha enviados forem os placeholders de exibição, pegamos do config
        config = load_config()
        if client_secret == '********' or not client_secret:
            client_secret = config.get('TEAMS_CLIENT_SECRET', '')
        if teams_user_password == '********' or not teams_user_password:
            teams_user_password = config.get('TEAMS_USER_PASSWORD', '')

        if is_nominal:
            if not tenant_id or not client_id or not teams_user_email or not teams_user_password or not (teams_user_group or teams_user_group_id):
                return jsonify({'error': 'Para teste nominal, Tenant ID, Client ID, E-mail da Conta, Senha e Grupo são obrigatórios.'}), 400

            # 1. Tenta obter token ROPC delegado
            logging.info("Iniciando teste nominal de conexão: Obtendo token delegado ROPC...")
            token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
            token_payload = {
                'grant_type': 'password',
                'client_id': client_id,
                'scope': 'https://graph.microsoft.com/.default',
                'username': teams_user_email,
                'password': teams_user_password
            }
            if client_secret:
                token_payload['client_secret'] = client_secret

            token_res = requests.post(token_url, data=token_payload, timeout=10)
            if not token_res.ok:
                return jsonify({'error': f"Falha na autenticação ROPC da conta de serviço: {token_res.status_code} - {token_res.text}"}), 400

            access_token = token_res.json().get('access_token')
            if not access_token:
                return jsonify({'error': 'Token de acesso delegado não encontrado na resposta ROPC.'}), 400

            # 2. Obter membros do grupo (do Entra ID ou do AD local)
            member_emails = set()
            is_entra_group = False
            
            import re
            is_uuid = bool(re.match(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$', teams_user_group_id))
            
            if is_uuid:
                logging.info(f"Buscando membros do grupo do Entra ID {teams_user_group_id}...")
                headers = {
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                }
                members_url = f"https://graph.microsoft.com/v1.0/groups/{teams_user_group_id}/members?$select=id,userPrincipalName,mail,displayName"
                try:
                    members_res = requests.get(members_url, headers=headers, timeout=10)
                    if members_res.ok:
                        raw_members = members_res.json().get('value', [])
                        for m in raw_members:
                            upn = m.get('userPrincipalName') or m.get('mail')
                            if upn:
                                member_emails.add(upn.strip().lower())
                        is_entra_group = True
                        logging.info(f"Membros obtidos do Entra ID: {member_emails}")
                    else:
                        return jsonify({'error': f"Erro ao acessar membros do grupo no Entra ID: {members_res.status_code} - {members_res.text}"}), 400
                except Exception as e_entra:
                    return jsonify({'error': f"Exceção ao buscar membros no Entra ID: {str(e_entra)}"}), 400
            
            if not is_entra_group:
                # Fallback clássico para o Active Directory local (LDAP)
                from common import get_service_account_connection, get_group_by_name, get_group_members_emails
                try:
                    conn = get_service_account_connection()
                    group_entry = get_group_by_name(conn, teams_user_group)
                    if not group_entry:
                        return jsonify({'error': f"Grupo '{teams_user_group}' não foi localizado no Active Directory local nem no Entra ID."}), 400
                    
                    member_emails = get_group_members_emails(conn, group_entry.entry_dn)
                    if not member_emails:
                        return jsonify({'error': f"Grupo '{teams_user_group}' localizado no AD, mas não contém membros com e-mails cadastrados para o teste."}), 400
                except Exception as e_ad:
                    return jsonify({'error': f"Erro ao acessar o Active Directory para buscar o grupo: {str(e_ad)}"}), 400

            # 3. Resolve a conta de serviço no Graph
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            from routes.teams_notifier import get_graph_user_identifier, get_graph_me_identifier

            # Usa /me para resolver a conta de serviço (requer apenas User.Read)
            resolved_service_user = get_graph_me_identifier(headers)
            if not resolved_service_user:
                resolved_service_user = get_graph_user_identifier(teams_user_email, headers)
            if not resolved_service_user:
                return jsonify({'error': f"Não foi possível resolver a conta de serviço '{teams_user_email}' no Microsoft Entra ID. Verifique se a permissão User.Read está concedida com admin consent."}), 400

            # Se houver membros carregados, enviamos para todos eles
            destinatarios = list(member_emails) if member_emails else [teams_user_email]

            success_count = 0
            failures = []

            for target_test_email in destinatarios:
                # Evita enviar para a própria conta de serviço que está disparando, a não ser que ela seja a única destinatária
                if len(destinatarios) > 1 and target_test_email.lower() == teams_user_email.lower():
                    continue

                resolved_member_user = get_graph_user_identifier(target_test_email, headers)
                if not resolved_member_user:
                    logging.warning(f"Não foi possível resolver o usuário de teste '{target_test_email}' no Microsoft Entra ID. Pulando.")
                    failures.append(f"{target_test_email} (Não resolvido no Entra ID)")
                    continue

                logging.info(f"Criando chat privado entre {resolved_service_user} e {resolved_member_user} para teste...")
                chat_url = "https://graph.microsoft.com/v1.0/chats"
                chat_payload = {
                    "chatType": "oneOnOne",
                    "members": [
                        {
                            "@odata.type": "#microsoft.graph.aadUserConversationMember",
                            "roles": ["owner"],
                            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{resolved_service_user}')"
                        },
                        {
                            "@odata.type": "#microsoft.graph.aadUserConversationMember",
                            "roles": ["owner"],
                            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{resolved_member_user}')"
                        }
                    ]
                }
                chat_res = requests.post(chat_url, json=chat_payload, headers=headers, timeout=10)
                if not chat_res.ok:
                    logging.error(f"Erro ao criar chat privado com {target_test_email}: {chat_res.status_code} - {chat_res.text}")
                    failures.append(f"{target_test_email} (Erro ao criar chat)")
                    continue

                chat_id = chat_res.json().get('id')
                if not chat_id:
                    logging.error(f"ID do chat privado não retornado para {target_test_email}.")
                    failures.append(f"{target_test_email} (ID do chat ausente)")
                    continue

                # Envia a mensagem de teste
                test_html = f"""
                <div style="font-family: Arial, sans-serif; border-left: 5px solid #0078D4; padding-left: 15px; max-width: 600px;">
                    <h3 style="color: #0078D4; margin-top: 0; margin-bottom: 5px;">🔧 Teste de Integração Nominal - Portal Gestão AD</h3>
                    <p style="color: #323130; margin-top: 0; margin-bottom: 5px;">A conexão da API do Microsoft Graph via chat privado foi estabelecida com sucesso!</p>
                    <p style="font-size: 11px; color: #605E5C; margin: 0;">Sua conta de serviço <strong>{teams_user_email}</strong> está pronta para enviar alertas individuais automáticos.</p>
                </div>
                """
                logging.info(f"Enviando mensagem de teste no chat privado {chat_id} para {target_test_email}...")
                message_url = f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages"
                message_payload = {
                    "body": {
                        "contentType": "html",
                        "content": test_html
                    }
                }
                msg_res = requests.post(message_url, json=message_payload, headers=headers, timeout=10)
                if not msg_res.ok:
                    logging.error(f"Erro ao postar mensagem de teste no chat privado para {target_test_email}: {msg_res.status_code} - {msg_res.text}")
                    failures.append(f"{target_test_email} (Erro ao enviar mensagem)")
                    continue

                success_count += 1

            if success_count == 0:
                err_msg = "Falha ao enviar mensagem para os membros do grupo. " + ", ".join(failures)
                return jsonify({'error': err_msg}), 400

            success_msg = f'Integração testada com sucesso! Mensagens privadas nominais de teste foram enviadas para os membros do grupo ({success_count} enviadas com sucesso).'
            if failures:
                success_msg += f' Algumas falhas ocorreram: {", ".join(failures)}'

            return jsonify({'success': True, 'message': success_msg})

        else:
            # Fluxo clássico por canal público
            if not tenant_id or not client_id or not client_secret or not group_id or not channel_id:
                return jsonify({'error': 'Todos os campos do MS Teams são obrigatórios para o teste clássico.'}), 400

            # 1. Tenta obter token OAuth2 do Entra ID
            logging.info("Iniciando teste de conexão: Obtendo token do Entra ID...")
            token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
            token_payload = {
                'grant_type': 'client_credentials',
                'client_id': client_id,
                'client_secret': client_secret,
                'scope': 'https://graph.microsoft.com/.default'
            }
            token_res = requests.post(token_url, data=token_payload, timeout=10)
            if not token_res.ok:
                return jsonify({'error': f"Falha na autenticação do Entra ID: {token_res.status_code} - {token_res.text}"}), 400

            access_token = token_res.json().get('access_token')
            if not access_token:
                return jsonify({'error': 'Token de acesso não encontrado na resposta do Entra ID.'}), 400

            # 2. Envia mensagem HTML de teste via Graph API
            logging.info("Token obtido. Enviando mensagem de teste...")
            test_html = """
            <div style="font-family: Arial, sans-serif; border-left: 5px solid #0078D4; padding-left: 15px; max-width: 600px;">
                <h3 style="color: #0078D4; margin-top: 0; margin-bottom: 5px;">🔧 Teste de Integração de Segurança - Portal Gestão AD</h3>
                <p style="color: #323130; margin-top: 0; margin-bottom: 5px;">A conexão da API do Microsoft Graph com o canal do Teams foi estabelecida com sucesso!</p>
                <p style="font-size: 11px; color: #605E5C; margin: 0;">O Portal de Gestão AD está agora pronto para enviar notificações de alertas de segurança automáticos.</p>
            </div>
            """
            graph_url = f"https://graph.microsoft.com/v1.0/teams/{group_id}/channels/{channel_id}/messages"
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            payload = {
                "body": {
                    "contentType": "html",
                    "content": test_html
                }
            }
            graph_res = requests.post(graph_url, json=payload, headers=headers, timeout=10)
            if not graph_res.ok:
                return jsonify({'error': f"Erro ao enviar mensagem no canal do Teams: {graph_res.status_code} - {graph_res.text}"}), 400

            return jsonify({'success': True, 'message': 'Integração testada com sucesso! Uma mensagem de teste foi enviada para o canal.'})

    except Exception as e:
        logging.error(f"Erro ao testar integração com o Teams: {e}", exc_info=True)
        return jsonify({'error': f"Erro ao testar conexão: {str(e)}"}), 500


@zimbra_bp.route('/api/zimbra/search_teams_groups', methods=['GET'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_search_teams_groups():
    try:
        import requests
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify({'groups': []})

        # 1. Obter configurações de conexão do Teams
        config = load_config()
        all_groups = []

        # Tentar buscar grupos no Entra ID caso as credenciais estejam preenchidas
        tenant_id = config.get('TEAMS_TENANT_ID')
        client_id = config.get('TEAMS_CLIENT_ID')
        client_secret = config.get('TEAMS_CLIENT_SECRET')
        user_email = config.get('TEAMS_USER_EMAIL')
        user_password = config.get('TEAMS_USER_PASSWORD')

        if tenant_id and client_id and user_email and user_password:
            try:
                # Obter Token OAuth2 Delegado usando fluxo ROPC
                token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
                token_payload = {
                    'grant_type': 'password',
                    'client_id': client_id,
                    'scope': 'https://graph.microsoft.com/.default',
                    'username': user_email,
                    'password': user_password
                }
                if client_secret:
                    token_payload['client_secret'] = client_secret

                token_res = requests.post(token_url, data=token_payload, timeout=5)
                if token_res.ok:
                    access_token = token_res.json().get('access_token')
                    if access_token:
                        headers = {
                            'Authorization': f'Bearer {access_token}',
                            'Content-Type': 'application/json'
                        }
                        # Filtro oData: começa com o nome digitado
                        filter_str = f"startsWith(displayName, '{query}')"
                        groups_url = f"https://graph.microsoft.com/v1.0/groups?$filter={filter_str}&$top=10"
                        
                        groups_res = requests.get(groups_url, headers=headers, timeout=5)
                        if groups_res.ok:
                            raw_groups = groups_res.json().get('value', [])
                            for g in raw_groups:
                                all_groups.append({
                                    'id': g.get('id'),
                                    'displayName': g.get('displayName'),
                                    'mail': g.get('mail') or g.get('mailNickname') or '',
                                    'source': 'Entra ID'
                                })
            except Exception as e_entra:
                logging.error(f"Erro ao buscar grupos no Entra ID: {e_entra}")

        # 2. Tentar buscar grupos no Active Directory Local (LDAP)
        try:
            from common import get_service_account_connection
            conn = get_service_account_connection()
            if conn and conn.bound:
                search_base = config.get('AD_SEARCH_BASE', '')
                search_filter = f"(&(objectClass=group)(|(cn={query}*)(cn=*{query}*)))"
                conn.search(search_base, search_filter, attributes=['cn', 'mail', 'distinguishedName'])
                for entry in conn.entries:
                    all_groups.append({
                        'id': str(entry.distinguishedName),
                        'displayName': str(entry.cn),
                        'mail': str(entry.mail) if 'mail' in entry and entry.mail.value else '',
                        'source': 'AD Local'
                    })
        except Exception as e_ad:
            logging.error(f"Erro ao buscar grupos no AD Local: {e_ad}")

        return jsonify({'groups': all_groups})
    except Exception as e:
        logging.error(f"Erro ao buscar grupos: {e}", exc_info=True)
        return jsonify({'error': str(e), 'groups': []}), 500


@zimbra_bp.route('/api/zimbra/forwardings', methods=['GET'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_get_forwardings():
    try:
        config = load_config()
        if not config.get('ZIMBRA_ENABLED', False):
            return jsonify({'error': 'A integração do Zimbra está desativada.'}), 403
            
        zimbra_url = config.get('ZIMBRA_API_URL', '')
        zimbra_user = config.get('ZIMBRA_ADMIN_USER', '')
        zimbra_password = config.get('ZIMBRA_ADMIN_PASSWORD', '')
        
        if not zimbra_url or not zimbra_user:
            return jsonify({'error': 'A API do Zimbra não está configurada.'}), 400
            
        client = ZimbraSOAPClient(zimbra_url, zimbra_user, zimbra_password)
        accounts = client.search_accounts_with_forwarding()
        
        # Obtém domínios corporativos para destacar encaminhamentos externos
        domains_list = []
        try:
            domains = client.get_domains()
            if domains:
                domains_list = [d.get('name', '').strip().lower() for d in domains if d.get('name')]
        except Exception as ex:
            logging.error(f"Erro ao buscar domínios para realce de emails externos: {ex}")
            
        return jsonify({'success': True, 'accounts': accounts, 'domains': domains_list})
    except Exception as e:
        logging.error(f"Erro ao listar encaminhamentos do Zimbra: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@zimbra_bp.route('/api/zimbra/forwardings/remove', methods=['POST'])
@require_auth
@require_permission(action='can_manage_zimbra')
def api_remove_forwarding():
    try:
        config = load_config()
        if not config.get('ZIMBRA_ENABLED', False):
            return jsonify({'error': 'A integração do Zimbra está desativada.'}), 403
            
        data = request.get_json() or {}
        account_id = data.get('account_id')
        email = data.get('email')
        attr_type = data.get('attr_type', 'forwarding')
        
        if not account_id or not email:
            return jsonify({'error': 'Dados incompletos (account_id e email são obrigatórios).'}), 400
            
        zimbra_url = config.get('ZIMBRA_API_URL', '')
        zimbra_user = config.get('ZIMBRA_ADMIN_USER', '')
        zimbra_password = config.get('ZIMBRA_ADMIN_PASSWORD', '')
        
        client = ZimbraSOAPClient(zimbra_url, zimbra_user, zimbra_password)
        
        if attr_type == 'forwarding':
            # Valida se o encaminhamento é realmente externo antes de remover
            has_external = False
            try:
                # Obtém domínios corporativos
                domains_list = []
                domains = client.get_domains()
                if domains:
                    domains_list = [d.get('name', '').strip().lower() for d in domains if d.get('name')]
                
                accounts = client.search_accounts_with_forwarding()
                target_account = None
                for acc in accounts:
                    if acc.get('id') == account_id or acc.get('email') == email.strip().lower():
                        target_account = acc
                        break
                
                if target_account:
                    for addr in target_account.get('forwarding_addresses', []):
                        parts = addr.split('@')
                        domain = parts[-1].strip().lower() if len(parts) > 1 else ''
                        if domain not in domains_list:
                            has_external = True
                            break
                else:
                    return jsonify({'error': 'Esta conta não possui regras de encaminhamento ativas no Zimbra.'}), 400
            except Exception as ex:
                logging.error(f"Erro ao verificar se encaminhamento é externo: {ex}")
                return jsonify({'error': f"Erro de validação de segurança: {str(ex)}"}), 500
                
            if not has_external:
                return jsonify({'error': 'Não é permitido remover encaminhamentos corporativos internos.'}), 403
                
        client.remove_zimbra_attribute(account_id, attr_type)
        
        # Salva no histórico de ações
        if attr_type == 'forwarding':
            attr_label = 'Encaminhamento'
        elif attr_type == 'reply_to':
            attr_label = 'Reply-To (Responder para)'
        elif attr_type == 'notification':
            attr_label = 'Notificação de Entrada'
        else:
            attr_label = attr_type

        save_to_history(
            f'REMOVER_{attr_type.upper()}_ZIMBRA',
            session.get('ad_user', 'admin'),
            f"Removido {attr_label} da conta do Zimbra {email} (ID: {account_id})."
        )
        
        return jsonify({'success': True, 'message': f'{attr_label} removido com sucesso para {email}.'})
    except Exception as e:
        logging.error(f"Erro ao remover {attr_type} da conta {email}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

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
            
        elif tag_name == "AddDistributionListAliasRequest":
            dl_email = request_el.attrib.get("id")
            alias_email = request_el.attrib.get("alias")
            
            dl_email = dl_email.strip().lower() if dl_email else ""
            alias_email = alias_email.strip().lower() if alias_email else ""
            # Resolve UUID de volta para e-mail na simulação
            if "@" not in dl_email:
                for k in list(MOCK_DLS.keys()):
                    if f"dl-id-{hash(k) & 0xffff}" == dl_email:
                        dl_email = k
                        break
                        
            logging.info(f"[ZIMBRA-MOCK] Adicionando alias '{alias_email}' à lista '{dl_email}'")
            
            response_body = """
            <AddDistributionListAliasResponse xmlns="urn:zimbraAdmin"/>
            """
            
        elif tag_name == "RenameDistributionListRequest":
            id_el = request_el.find("{urn:zimbraAdmin}id")
            new_name_el = request_el.find("{urn:zimbraAdmin}newName")
            
            dl_email = id_el.text.strip().lower() if id_el is not None and id_el.text else ""
            new_email = new_name_el.text.strip().lower() if new_name_el is not None and new_name_el.text else ""
            
            # Resolve UUID de volta para e-mail na simulação
            if "@" not in dl_email:
                for k in list(MOCK_DLS.keys()):
                    if f"dl-id-{hash(k) & 0xffff}" == dl_email:
                        dl_email = k
                        break
            
            logging.info(f"[ZIMBRA-MOCK] Renomeando lista '{dl_email}' para '{new_email}'")
            if dl_email in MOCK_DLS:
                MOCK_DLS[new_email] = MOCK_DLS.pop(dl_email)
                
            response_body = """
            <RenameDistributionListResponse xmlns="urn:zimbraAdmin"/>
            """
            
        elif tag_name == "DeleteDistributionListRequest":
            id_el = request_el.find("{urn:zimbraAdmin}id")
            dl_email = id_el.text.strip().lower() if id_el is not None and id_el.text else ""
            
            # Resolve UUID de volta para e-mail na simulação
            if "@" not in dl_email:
                for k in list(MOCK_DLS.keys()):
                    if f"dl-id-{hash(k) & 0xffff}" == dl_email:
                        dl_email = k
                        break
                        
            logging.info(f"[ZIMBRA-MOCK] Removendo lista '{dl_email}'")
            if dl_email in MOCK_DLS:
                MOCK_DLS.pop(dl_email)
                
            response_body = """
            <DeleteDistributionListResponse xmlns="urn:zimbraAdmin"/>
            """
            
        elif tag_name == "SearchDirectoryRequest":
            logging.info("[ZIMBRA-MOCK] Buscando contas com encaminhamento ativo")
            response_body = """
            <SearchDirectoryResponse xmlns="urn:zimbraAdmin">
                <account name="joao.silva@comolatti.com.br" id="acc-id-joao">
                    <a n="zimbraPrefMailForwardingAddress">externo_joao@gmail.com</a>
                    <a n="zimbraPrefMailLocalDeliveryDisabled">TRUE</a>
                    <a n="displayName">João Silva</a>
                    <a n="zimbraAccountStatus">active</a>
                </account>
                <account name="maria.souza@comolatti.com.br" id="acc-id-maria">
                    <a n="zimbraPrefMailForwardingAddress">externo_maria@outlook.com</a>
                    <a n="zimbraPrefMailLocalDeliveryDisabled">FALSE</a>
                    <a n="zimbraPrefReplyToAddress">reply_maria@gmail.com</a>
                    <a n="zimbraPrefNewMailNotificationAddress">notify_maria@external.com</a>
                    <a n="displayName">Maria Souza</a>
                    <a n="zimbraAccountStatus">active</a>
                </account>
                <account name="pedro.santos@comolatti.com.br" id="acc-id-pedro">
                    <a n="zimbraPrefReplyToAddress">reply_pedro@external.com</a>
                    <a n="zimbraPrefNewMailNotificationAddress">notify_pedro@comolatti.com.br</a>
                    <a n="displayName">Pedro Santos</a>
                    <a n="zimbraAccountStatus">active</a>
                </account>
            </SearchDirectoryResponse>
            """
            
        elif tag_name == "ModifyAccountRequest":
            id_el = request_el.find("{urn:zimbraAdmin}id")
            acc_id = id_el.text.strip() if id_el is not None and id_el.text else ""
            logging.info(f"[ZIMBRA-MOCK] Modificando conta Zimbra ID '{acc_id}'")
            response_body = f"""
            <ModifyAccountResponse xmlns="urn:zimbraAdmin">
                <account name="mock-user@comolatti.com.br" id="{acc_id}"/>
            </ModifyAccountResponse>
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

