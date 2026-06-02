from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify, current_app
from routes.utils import (
    require_auth, check_permission, require_permission,
    get_read_connection, get_attr_value,
    get_user_by_dn
)
from common import (
    load_config, save_config, load_permissions, save_permissions,
    get_user_by_samaccountname, HISTORY_FILE, load_schedules, load_disable_schedules,
    get_service_account_connection, save_to_history, filetime_to_datetime
)
from forms.config import ConfigForm, AppearanceForm
from forms.admin import LogSearchForm
from forms.auth import AdminRegistrationForm, AdminLoginForm, AdminChangePasswordForm
from flask_wtf import FlaskForm
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
import logging
import re
from PIL import Image
import ldap3
from ldap3 import SUBTREE, MODIFY_REPLACE

def load_history():
    """Carrega o histórico de ações do arquivo JSON."""
    import json, os
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/login')
def admin_login():
    # Redireciona para o login único do sistema
    return redirect(url_for('auth.login'))

@admin_bp.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('auth.login'))

@admin_bp.route('/admin/register', methods=['GET', 'POST'])
def admin_register():
    from common import load_admin_users, save_admin_users
    admins = load_admin_users()
    
    # Se já existir qualquer admin, redireciona para login
    if admins:
        flash('O administrador já está registrado.', 'warning')
        return redirect(url_for('admin.admin_login'))
    
    form = AdminRegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        users = {form.username.data: hashed_password}
        save_admin_users(users)
        flash('Administrador registrado com sucesso! Agora você pode fazer login.', 'success')
        return redirect(url_for('admin.admin_login'))
    return render_template('admin/register.html', form=form)

@admin_bp.route('/admin/dashboard')
@require_auth
def dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('main.dashboard'))
    return render_template('admin/dashboard.html')

@admin_bp.route('/admin/change_password', methods=['GET', 'POST'])
@require_auth
def admin_change_password():
    if 'master_admin' not in session:
        return redirect(url_for('admin.admin_login'))
    
    form = AdminChangePasswordForm()
    if form.validate_on_submit():
        username = session['master_admin']
        from common import load_admin_users, save_admin_users
        users = load_admin_users()
        
        if username in users and check_password_hash(users[username], form.current_password.data):
            users[username] = generate_password_hash(form.new_password.data)
            save_admin_users(users)
            flash('Senha alterada com sucesso!', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('A senha atual está incorreta.', 'danger')
    return render_template('admin/change_password.html', form=form)

@admin_bp.route('/admin/config', methods=['GET', 'POST'])
@require_auth
@require_permission(action='can_edit_config')
def admin_config():
    config = load_config()
    form = ConfigForm()
    if request.method == 'GET':
        form.ad_server.data = config.get('AD_SERVER')
        form.use_ldaps.data = config.get('USE_LDAPS', False)
        form.ad_domain.data = config.get('AD_DOMAIN')
        form.ad_search_base.data = config.get('AD_SEARCH_BASE')
        form.sso_enabled.data = config.get('SSO_ENABLED', False)
        form.service_account_user.data = config.get('SERVICE_ACCOUNT_USER')
        form.upn_suffixes.data = config.get('upn_suffixes', '')
    if form.validate_on_submit():
        logging.info(f"Formulário de configuração validado. Novos sufixos: {form.upn_suffixes.data}")
        config['AD_SERVER'] = form.ad_server.data
        config['USE_LDAPS'] = form.use_ldaps.data
        config['AD_DOMAIN'] = form.ad_domain.data
        config['AD_SEARCH_BASE'] = form.ad_search_base.data
        config['SSO_ENABLED'] = form.sso_enabled.data
        config['SERVICE_ACCOUNT_USER'] = form.service_account_user.data
        config['upn_suffixes'] = form.upn_suffixes.data
        if form.default_password.data:
            config['DEFAULT_PASSWORD'] = form.default_password.data
        if form.service_account_password.data:
            config['SERVICE_ACCOUNT_PASSWORD'] = form.service_account_password.data
        save_config(config)
        flash('Configurações salvas com sucesso!', 'success')
        logging.info(f"Configurações do sistema alteradas por '{session.get('user_display_name')}'.")
        return redirect(url_for('admin.admin_config'))
    elif request.method == 'POST':
        logging.warning(f"Falha na validação do formulário de configuração: {form.errors}")
        
    db_config = {
        'db_host': config.get('DB_HOST', ''),
        'db_port': config.get('DB_PORT', '1433'),
        'db_name': config.get('DB_NAME', ''),
        'db_user': config.get('DB_USER', ''),
        'use_sql_server': config.get('USE_SQL_SERVER', False)
    }
    return render_template('admin/config.html', form=form, db_config=db_config)

@admin_bp.route('/admin/appearance', methods=['GET', 'POST'])
@require_auth
@require_permission(action='can_edit_config')
def admin_appearance():
    config = load_config()
    form = AppearanceForm()
    if request.method == 'GET':
        form.bg_color.data = config.get('ORGANOGRAM_BG_COLOR', '#f8f9fa')
        form.subtitle.data = config.get('ORGANOGRAM_SUBTITLE', 'Portal de Administração')
    if form.validate_on_submit():
        config['ORGANOGRAM_BG_COLOR'] = form.bg_color.data
        config['ORGANOGRAM_SUBTITLE'] = form.subtitle.data
        upload_folder = os.path.join(current_app.static_folder, 'uploads')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        if form.bg_image.data:
            filename = secure_filename('bg_image.' + form.bg_image.data.filename.rsplit('.', 1)[1].lower())
            form.bg_image.data.save(os.path.join(upload_folder, filename))
            config['ORGANOGRAM_BG_IMAGE'] = url_for('static', filename='uploads/' + filename)
        if form.logo.data:
            ext = form.logo.data.filename.rsplit('.', 1)[1].lower()
            filename = secure_filename('logo.' + ext)
            logo_path = os.path.join(upload_folder, filename)
            form.logo.data.save(logo_path)
            if ext != 'svg':
                try:
                    with Image.open(logo_path) as img:
                        img.thumbnail((400, 200))
                        img.save(logo_path)
                except Exception as e:
                    logging.error(f"Erro ao processar imagem do logo: {e}")
            config['ORGANOGRAM_LOGO'] = url_for('static', filename='uploads/' + filename)
        if form.favicon.data:
            filename = secure_filename('favicon.' + form.favicon.data.filename.rsplit('.', 1)[1].lower())
            form.favicon.data.save(os.path.join(upload_folder, filename))
            config['ORGANOGRAM_FAVICON'] = url_for('static', filename='uploads/' + filename)
        save_config(config)
        flash('Aparência atualizada com sucesso!', 'success')
        return redirect(url_for('admin.admin_appearance'))
    return render_template('admin/appearance.html', form=form, config=config)

AVAILABLE_FIELDS = {
    'first_name': 'Nome',
    'initials': 'Iniciais',
    'last_name': 'Sobrenome',
    'upn_suffix': 'Sufixo UPN',
    'display_name': 'Nome de Exibição',
    'description': 'Descrição',
    'office': 'Escritório',
    'telephone': 'Telefone Principal',
    'email': 'E-mail',
    'web_page': 'Página da Web',
    'street': 'Rua',
    'post_office_box': 'Caixa Postal',
    'city': 'Cidade',
    'state': 'Estado/Província',
    'zip_code': 'CEP',
    'home_phone': 'Telefone Residencial',
    'pager': 'Pager',
    'mobile': 'Celular',
    'fax': 'Fax',
    'title': 'Cargo',
    'department': 'Departamento',
    'company': 'Empresa',
    'manager': 'Gerente (Login)',
    'matricula': 'Matrícula'
}

@admin_bp.route('/admin/permissions', methods=['GET', 'POST'])
@require_auth
@require_permission(action='can_edit_permissions')
def admin_permissions():
    permissions = load_permissions()
    if request.method == 'POST':
        # Se estiver apenas buscando grupos, não salva nada
        if 'search_query' in request.form and 'save_permissions' not in request.form:
             # O template lida com o filtro se passarmos os grupos
             pass 

        if 'save_permissions' in request.form:
            new_permissions = permissions.copy()
            # Identifica todos os grupos presentes no formulário submetido
            submitted_groups = set()
            for key in request.form.keys():
                if '_perm_type' in key:
                    group_name = key.replace('_perm_type', '')
                    submitted_groups.add(group_name)

            for group in submitted_groups:
                perm_type = request.form.get(f"{group}_perm_type", "none")
                
                # Inicializa a estrutura para o grupo
                new_permissions[group] = {
                    "type": perm_type,
                    "actions": {},
                    "fields": [],
                    "views": {}
                }

                if perm_type == 'custom':
                    # Ações
                    actions = ['can_create', 'can_edit', 'can_disable', 'can_reset_password', 'can_manage_groups', 'can_move_user', 'can_delete_user', 'can_manage_exchange', 'can_manage_schedules', 'can_manage_zimbra']
                    for action in actions:
                        new_permissions[group]["actions"][action] = (request.form.get(f"{group}_{action}") == 'on')
                    
                    # Views
                    views = ['can_view_user_stats', 'can_view_deactivated_last_week', 'can_view_pending_reactivations', 'can_view_pending_deactivations', 'can_view_expiring_passwords', 'can_export_data', 'can_view_audit_logs', 'can_view_ad_tree']
                    for view in views:
                        new_permissions[group]["views"][view] = (request.form.get(f"{group}_{view}") == 'on')
                    
                    # Fields
                    for field in AVAILABLE_FIELDS.keys():
                        if request.form.get(f"{group}_field_{field}") == 'on':
                            new_permissions[group]["fields"].append(field)

            save_permissions(new_permissions)
            flash('Permissões atualizadas com sucesso!', 'success')
            logging.info(f"Permissões de acesso alteradas por '{session.get('user_display_name')}'.")
            return redirect(url_for('admin.admin_permissions'))

    # Se houver busca, filtra os grupos (apenas para exibição no template)
    search_query = request.form.get('search_query') or request.args.get('search_query')
    display_groups = []
    if search_query:
        # Carrega grupos do AD ou simplesmente filtra os que já têm permissões
        # Para simplificar e manter compatibilidade, vamos buscar nos grupos que já têm alguma regra
        # e também permitir a busca "cega" se o usuário souber o nome do grupo.
        query = search_query.lower()
        display_groups = [g for g in permissions.keys() if query in g.lower()]
        if search_query not in display_groups:
            # Verifica se o grupo existe no Active Directory antes de permitir adicioná-lo
            try:
                from common import get_group_by_name
                conn = get_read_connection()
                group_entry = get_group_by_name(conn, search_query)
                if group_entry:
                    group_name = group_entry.cn.value if hasattr(group_entry, 'cn') else search_query
                    # Evita duplicados em caso de diferença de maiúsculas/minúsculas
                    if group_name not in display_groups:
                        display_groups.append(group_name)
                else:
                    flash(f"O grupo '{search_query}' não foi encontrado no Active Directory.", 'warning')
            except Exception as e:
                logging.error(f"Erro ao verificar existência do grupo no AD: {e}")
                # Fallback amigável de desenvolvimento offline
                display_groups.append(search_query)

    from forms.groups import GroupSearchForm
    search_form = GroupSearchForm()
    if search_query:
        search_form.search_query.data = search_query

    return render_template('admin/permissions.html', 
                           permissions=permissions, 
                           groups=display_groups, 
                           search_form=search_form,
                           available_fields=AVAILABLE_FIELDS)

@admin_bp.route('/admin/logs', methods=['GET', 'POST'])
@require_auth
@require_permission(action='can_view_logs')
def admin_logs():
    from forms.admin import LogSearchForm
    form = LogSearchForm()
    
    # Busca query do formulário ou da URL
    query = ""
    active_tab = request.form.get('active_tab', 'creation')
    
    if request.method == 'POST':
        query = form.search_query.data.strip() if form.search_query.data else ""
    else:
        query = request.args.get('search_query', '').strip()
        form.search_query.data = query

    log_path = os.path.join(current_app.root_path, 'logs', 'ad_creator.log')
    logs = {
        'creation': [],
        'alteration': [],
        'exclusion': [],
        'movement': []
    }
    
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in reversed(lines):
                    line_strip = line.strip()
                    if not query or query.lower() in line_strip.lower():
                        # Tenta parsear o formato: YYYY-MM-DD HH:MM:SS,mmm - LEVEL - MESSAGE
                        parts = line_strip.split(' - ', 2)
                        if len(parts) >= 3:
                            ts = parts[0]
                            msg = parts[2]
                        else:
                            ts = ""
                            msg = line_strip
                            
                        log_obj = {'timestamp': ts, 'message': msg}
                        
                        if '[CRIAÇÃO]' in line_strip:
                            logs['creation'].append(log_obj)
                        elif '[ALTERAÇÃO]' in line_strip:
                            logs['alteration'].append(log_obj)
                        elif '[EXCLUSÃO]' in line_strip:
                            logs['exclusion'].append(log_obj)
                        elif '[MOVIMENTAÇÃO]' in line_strip:
                            logs['movement'].append(log_obj)
                    
                    # Limita o total de logs para performance
                    if sum(len(v) for v in logs.values()) >= 1000:
                        break
        except Exception as e:
            flash(f"Erro ao ler arquivo de log: {e}", "error")
            
    return render_template('admin/logs.html', logs=logs, search_form=form, active_tab=active_tab)

@admin_bp.route('/admin/history')
@require_auth
@require_permission(action='can_view_logs')
def admin_history():
    history = load_history()
    history.reverse()
    return render_template('admin/history.html', history=history[:500])

@admin_bp.route('/admin/users')
@require_auth
@require_permission(action='can_edit_config')
def admin_users():
    data_dir = os.path.join(current_app.root_path, 'data')
    users_file = os.path.join(data_dir, 'users.json')
    users = {}
    if os.path.exists(users_file):
        with open(users_file, 'r') as f:
            users = json.load(f)
    return render_template('admin/users.html', users=users)

@admin_bp.route('/admin/users/add', methods=['GET', 'POST'])
@require_auth
@require_permission(action='can_edit_config')
def admin_add_user():
    form = AdminRegistrationForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        data_dir = os.path.join(current_app.root_path, 'data')
        users_file = os.path.join(data_dir, 'users.json')
        users = {}
        if os.path.exists(users_file):
            with open(users_file, 'r') as f:
                users = json.load(f)
        if username in users:
            flash('Usuário já existe.', 'error')
        else:
            use_ad_auth = request.form.get('use_ad_auth') == 'on'
            if use_ad_auth:
                users[username] = "AD_AUTH"
                flash('Administrador do AD adicionado com sucesso!', 'success')
            else:
                if not password or len(password) < 8:
                    flash('Erro: Para administradores locais, a senha deve ter pelo menos 8 caracteres.', 'error')
                    return render_template('admin/add_user.html', form=form)
                users[username] = generate_password_hash(password)
                flash('Administrador local adicionado com sucesso!', 'success')
            
            with open(users_file, 'w') as f:
                json.dump(users, f)
            return redirect(url_for('admin.admin_users'))
    return render_template('admin/add_user.html', form=form)

@admin_bp.route('/admin/users/delete/<username>', methods=['POST'])
@require_auth
@require_permission(action='can_edit_config')
def admin_delete_user(username):
    if username == session.get('master_admin'):
        flash('Você não pode excluir a si mesmo.', 'error')
        return redirect(url_for('admin.admin_users'))
    data_dir = os.path.join(current_app.root_path, 'data')
    users_file = os.path.join(data_dir, 'users.json')
    if os.path.exists(users_file):
        with open(users_file, 'r') as f:
            users = json.load(f)
        if username in users:
            del users[username]
            with open(users_file, 'w') as f:
                json.dump(users, f)
            flash('Usuário excluído.', 'success')
    return redirect(url_for('admin.admin_users'))

# API ENDPOINTS — rota sem prefixo /admin para corresponder ao fetch() no dashboard.html
@admin_bp.route('/api/dashboard/stats')
@require_auth
def api_dashboard_stats():
    from datetime import date, timedelta
    data = {
        'total_users': 0,
        'active_users': 0,
        'disabled_users': 0,
        'total_groups': 0,
        'deactivated_last_week': 0,
        'pending_reactivations': 0,
        'pending_deactivations': 0,
        'trends': []
    }
    try:
        conn = get_read_connection()
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE')
        
        # Estatísticas básicas com paginação (para lidar com ADs > 1000 usuários)
        active_count = 0
        disabled_count = 0
        user_generator = conn.extend.standard.paged_search(
            search_base=search_base,
            search_filter='(&(objectClass=user)(objectCategory=person)(userPrincipalName=*))',
            attributes=['userAccountControl'],
            paged_size=1000,
            generator=True
        )
        for entry in user_generator:
            if 'attributes' in entry and 'userAccountControl' in entry['attributes']:
                uac = entry['attributes']['userAccountControl']
                if uac & 2:
                    disabled_count += 1
                else:
                    active_count += 1

        data['total_users'] = active_count + disabled_count
        data['active_users'] = active_count
        data['disabled_users'] = disabled_count
        
        group_count = 0
        group_generator = conn.extend.standard.paged_search(
            search_base=search_base,
            search_filter='(objectClass=group)',
            attributes=['cn'],
            paged_size=1000,
            generator=True
        )
        for _ in group_generator:
            group_count += 1
        data['total_groups'] = group_count

        # Desativações na última semana
        seven_days_ago = date.today() - timedelta(days=7)
        # Tentativa via AD (filtro approximate)
        ad_date_str = seven_days_ago.strftime('%Y%m%d%H%M%S.0Z')
        search_filter = f"(&(objectClass=user)(objectCategory=person)(userAccountControl:1.2.840.113556.1.4.803:=2)(whenChanged>={ad_date_str}))"
        conn.search(search_base, search_filter, attributes=['cn'])
        data['deactivated_last_week'] = len(conn.entries)

        # Agendamentos (Próximos 7 dias)
        today = date.today()
        limit_date = today + timedelta(days=7)
        
        reactivations_count = 0
        for username, date_str in load_schedules().items():
            try:
                sch_date = date.fromisoformat(date_str)
                if today <= sch_date < limit_date:
                    reactivations_count += 1
            except (ValueError, TypeError): continue
        data['pending_reactivations'] = reactivations_count

        deactivations_count = 0
        for username, date_str in load_disable_schedules().items():
            try:
                sch_date = date.fromisoformat(date_str)
                if today <= sch_date < limit_date:
                    deactivations_count += 1
            except (ValueError, TypeError): continue
        data['pending_deactivations'] = deactivations_count

        # Tendências (30 dias)
        trends = {}
        for i in range(30):
            day = (today - timedelta(days=i)).isoformat()
            trends[day] = 0
            
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
                for entry in history:
                    if entry.get('action') == 'deactivation':
                        log_day = entry['timestamp'][:10]
                        if log_day in trends:
                            trends[log_day] += 1
        
        data['trends'] = [{'date': d, 'count': c} for d, c in sorted(trends.items())]
        
        # Senhas expirando (próximos 15 dias)
        expiring_list = []
        try:
            # Busca usuários ativos com msDS-UserPasswordExpiryTimeComputed
            user_exp_generator = conn.extend.standard.paged_search(
                search_base=search_base, 
                search_filter='(&(objectClass=user)(objectCategory=person)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))', 
                attributes=['cn', 'sAMAccountName', 'title', 'department', 'msDS-UserPasswordExpiryTimeComputed'],
                paged_size=1000,
                generator=True
            )
            
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            
            for entry in user_exp_generator:
                attrs = entry.get('attributes', {})
                if not attrs: continue
                
                expiry_ft = attrs.get('msDS-UserPasswordExpiryTimeComputed')
                if expiry_ft and expiry_ft > 0 and expiry_ft != 9223372036854775807:
                    expiry_dt = filetime_to_datetime(expiry_ft)
                    if expiry_dt:
                        diff = expiry_dt - now
                        days = diff.days
                        if 0 <= days <= 15:
                            expiring_list.append({
                                'cn': attrs.get('cn') if attrs.get('cn') else attrs.get('sAMAccountName'),
                                'sam': attrs.get('sAMAccountName'),
                                'title': attrs.get('title') if attrs.get('title') else '',
                                'department': attrs.get('department') if attrs.get('department') else '',
                                'expires_in_days': max(0, days)
                            })
            
            # Ordena por urgência
            expiring_list.sort(key=lambda x: x['expires_in_days'])
            data['expiring_passwords'] = expiring_list
            
        except Exception as e:
            logging.error(f"Erro ao buscar senhas expirando: {e}", exc_info=True)
            data['expiring_passwords'] = []

        return jsonify(data)
    except Exception as e:
        logging.error(f"Erro ao gerar estatísticas do dashboard: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/ous')
@require_auth
def api_ous():
    try:
        from routes.utils import get_all_ous
        conn = get_read_connection()
        tree = get_all_ous(conn)
        return jsonify(tree)
    except Exception as e:
        logging.error(f"Erro na API de OUs: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/search_ad')
@require_auth
def api_search_ad():
    query = request.args.get('q', '')
    if not query: return jsonify([])
    try:
        conn = get_read_connection()
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE')
        search_filter = f"(&(objectCategory=person)(|(sAMAccountName=*{query}*)(displayName=*{query}*)(cn=*{query}*)(extensionAttribute4=*{query}*)))"
        conn.search(search_base, search_filter, SUBTREE, attributes=['displayName', 'cn', 'sAMAccountName', 'objectClass', 'distinguishedName', 'title', 'department'])
        results = []
        for entry in conn.entries:
            try:
                obj_type = 'user' if 'user' in entry.objectClass else 'group' if 'group' in entry.objectClass else 'other'
                name = None
                if 'displayName' in entry and entry.displayName.value:
                    name = entry.displayName.value
                elif 'cn' in entry and entry.cn.value:
                    name = entry.cn.value
                
                results.append({
                    'name': name or entry.sAMAccountName.value if 'sAMAccountName' in entry else 'Desconhecido',
                    'sam': entry.sAMAccountName.value if 'sAMAccountName' in entry else None,
                    'type': obj_type, 
                    'dn': entry.distinguishedName.value if 'distinguishedName' in entry else None,
                    'title': entry.title.value if 'title' in entry else '',
                    'department': entry.department.value if 'department' in entry else ''
                })
            except Exception as e:
                logging.error(f"Erro ao processar entrada do AD: {e}")
                continue
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/dashboard_list/<category>')
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

    if required_permission and not check_permission(view=required_permission):
        return jsonify({'error': 'Permissão negada para visualizar esta categoria.'}), 403

    try:
        conn = get_read_connection()
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE')
        attributes = ['cn', 'sAMAccountName', 'title', 'l', 'department', 'company']

        page = request.args.get('page', 1, type=int)
        per_page = 20
        items = []
        total_pages = 0

        if category == 'deactivated_last_week':
            from datetime import datetime, timedelta, timezone
            usernames = set()
            try:
                seven_days_ago_dt = datetime.now(timezone.utc) - timedelta(days=7)
                ad_date_str = seven_days_ago_dt.strftime('%Y%m%d%H%M%S.0Z')
                search_filter = f"(&(objectClass=user)(objectCategory=person)(userAccountControl:1.2.840.113556.1.4.803:=2)(whenChanged>={ad_date_str}))"
                conn.search(search_base, search_filter, attributes=['sAMAccountName'])
                for entry in conn.entries:
                    usernames.add(entry.sAMAccountName.value)
            except Exception as e:
                logging.error(f"Erro ao buscar desativados via AD: {e}")

            sorted_usernames = sorted(list(usernames))
            items, total_pages = get_paginated_user_details(conn, search_base, sorted_usernames, page, per_page, attributes)

        elif category == 'pending_reactivations':
            from common import load_schedules
            from datetime import date, timedelta
            schedules = load_schedules()
            today = date.today()
            limit_date = today + timedelta(days=7)
            scheduled_users = []
            for username, date_str in schedules.items():
                try:
                    reactivation_date = date.fromisoformat(date_str)
                    if today <= reactivation_date < limit_date:
                        scheduled_users.append({'sam': username, 'date': reactivation_date})
                except (ValueError, TypeError): continue
            sorted_users = sorted(scheduled_users, key=lambda x: x['date'])
            sam_names = [user['sam'] for user in sorted_users]
            items, total_pages = get_paginated_user_details(conn, search_base, sam_names, page, per_page, attributes)
            user_dates = {user['sam'].lower(): user['date'].strftime('%d-%m-%Y') for user in sorted_users}
            for item in items: item['scheduled_date'] = user_dates.get(item['sam'].lower())

        elif category == 'pending_deactivations':
            from common import load_disable_schedules
            from datetime import date, timedelta
            schedules = load_disable_schedules()
            today = date.today()
            limit_date = today + timedelta(days=7)
            scheduled_users = []
            for username, date_str in schedules.items():
                try:
                    deactivation_date = date.fromisoformat(date_str)
                    if today <= deactivation_date < limit_date:
                        scheduled_users.append({'sam': username, 'date': deactivation_date})
                except (ValueError, TypeError): continue
            sorted_users = sorted(scheduled_users, key=lambda x: x['date'])
            sam_names = [user['sam'] for user in sorted_users]
            items, total_pages = get_paginated_user_details(conn, search_base, sam_names, page, per_page, attributes)
            user_dates = {user['sam'].lower(): user['date'].strftime('%d-%m-%Y') for user in sorted_users}
            for item in items: item['scheduled_date'] = user_dates.get(item['sam'].lower())

        elif category in ['active_users', 'disabled_users']:
            import base64
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
            items = [{'cn': get_attr_value(e, 'cn'), 'sam': get_attr_value(e, 'sAMAccountName'), 'title': get_attr_value(e, 'title'), 'location': get_attr_value(e, 'l'), 'department': get_attr_value(e, 'department'), 'company': get_attr_value(e, 'company')} for e in conn.entries]
            paged_results_control = conn.result.get('controls', {}).get('1.2.840.113556.1.4.319', {})
            cookie_bytes = paged_results_control.get('value', {}).get('cookie')
            next_cookie_b64 = base64.b64encode(cookie_bytes).decode('utf-8') if cookie_bytes else None
            return jsonify({'items': items, 'cookie': next_cookie_b64})
        else:
            return jsonify({'error': 'Categoria inválida'}), 404

        return jsonify({'items': items, 'page': page, 'total_pages': total_pages})
    except Exception as e:
        logging.error(f"Erro na API do dashboard para '{category}': {e}", exc_info=True)
        return jsonify({'error': 'Falha ao carregar dados.'}), 500

def get_paginated_user_details(conn, search_base, sam_account_names, page, per_page, attributes):
    from ldap3.utils.conv import escape_filter_chars
    if not sam_account_names: return [], 0
    total_items = len(sam_account_names)
    total_pages = (total_items + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    sams_to_fetch = sam_account_names[start:end]
    if not sams_to_fetch: return [], total_pages
    ldap_filter = "(| " + "".join([f"(sAMAccountName={escape_filter_chars(sam)})" for sam in sams_to_fetch]) + ")"
    final_filter = f"(&(userPrincipalName=*){ldap_filter})"
    conn.search(search_base, final_filter, attributes=attributes)
    user_details_map = {get_attr_value(e, 'sAMAccountName'): e for e in conn.entries}
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


# ==============================================================================
# APIs de Configuração e Migração do Banco de Dados
# ==============================================================================
@admin_bp.route('/api/admin/database/test', methods=['POST'])
@require_auth
@require_permission(action='can_edit_config')
def api_test_db_connection():
    try:
        data = request.get_json() or {}
        db_host = data.get('db_host', '').strip()
        db_port = data.get('db_port', '1433').strip()
        db_user = data.get('db_user', '').strip()
        db_password = data.get('db_password', '').strip()
        db_name = data.get('db_name', '').strip()
        
        if not db_host or not db_user or not db_password or not db_name:
            return jsonify({'success': False, 'error': 'Preencha todos os campos obrigatórios (Host, Usuário, Senha e Nome do Banco).'}), 400
            
        # Se a senha for mascarada, recuperamos a senha salva
        if db_password == '********':
            from common import load_config
            config = load_config()
            db_password = config.get('DB_PASSWORD', '')

        # Tenta conectar usando pymssql
        uri = f"mssql+pymssql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        from sqlalchemy import create_engine
        engine = create_engine(uri, connect_args={'login_timeout': 4})
        with engine.connect() as connection:
            pass
            
        return jsonify({'success': True, 'message': 'Conexão estabelecida com sucesso!'})
    except Exception as e:
        logging.error(f"[DB] Falha no teste de conexão com o SQL Server: {e}")
        return jsonify({'success': False, 'error': f"Falha de Conexão: {str(e)}"}), 500

@admin_bp.route('/api/admin/database/migrate', methods=['POST'])
@require_auth
@require_permission(action='can_edit_config')
def api_migrate_to_db():
    try:
        data = request.get_json() or {}
        db_host = data.get('db_host', '').strip()
        db_port = data.get('db_port', '1433').strip()
        db_user = data.get('db_user', '').strip()
        db_password = data.get('db_password', '').strip()
        db_name = data.get('db_name', '').strip()
        use_sql_server = data.get('use_sql_server', False)
        
        if not db_host or not db_user or not db_password or not db_name:
            return jsonify({'success': False, 'error': 'Preencha todos os campos para efetuar a migração.'}), 400
            
        # Carrega a configuração existente para tratar senha mascarada ou carregar credenciais criptografadas
        from common import save_config, load_config, save_to_history
        config = load_config()
        
        # Se a senha for mascarada, recuperamos a senha salva
        if db_password == '********':
            db_password = config.get('DB_PASSWORD', '')

        uri = f"mssql+pymssql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        
        # 1. Valida a conexão antes de salvar
        from sqlalchemy import create_engine
        engine = create_engine(uri, connect_args={'login_timeout': 4})
        try:
            with engine.connect() as connection:
                pass
        except Exception as e:
            return jsonify({'success': False, 'error': f"Não foi possível conectar ao banco. Migração abortada. Detalhe: {str(e)}"}), 400
            
        # 2. Salva a configuração no arquivo config.json
        config['DB_HOST'] = db_host
        config['DB_PORT'] = db_port
        config['DB_NAME'] = db_name
        config['DB_USER'] = db_user
        config['DB_PASSWORD'] = db_password
        config['SQL_SERVER_URI'] = uri
        config['USE_SQL_SERVER'] = use_sql_server
        save_config(config)
        
        # 3. Se estiver ativo, reconfigura a app em runtime para usar o SQL Server,
        # roda create_all e seed_database_from_json
        if use_sql_server:
            current_app.config['SQLALCHEMY_DATABASE_URI'] = uri
            from models import db, seed_database_from_json
            from sqlalchemy import create_engine
            
            app_obj = current_app._get_current_object()
            
            # Instancia o motor do SQL Server manualmente para fazer o "hot-plug" no cache do Flask-SQLAlchemy 3.x
            engine_options = current_app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {})
            new_engine = create_engine(uri, **engine_options)
            
            if app_obj not in db._app_engines:
                db._app_engines[app_obj] = {}
            else:
                db._app_engines[app_obj].clear()
            
            # Substitui diretamente o motor padrão (chave None) no dicionário interno
            db._app_engines[app_obj][None] = new_engine
            
            db.create_all()
            seed_database_from_json(db)
            
            save_to_history('database_migration', session.get('ad_user', 'admin'), f"Migração de dados realizada com sucesso para o SQL Server {db_host}/{db_name}.")
            logging.info(f"[DB] Migração e ativação do SQL Server concluídas para {db_host}/{db_name}.")
            
        return jsonify({'success': True, 'message': 'Configurações salvas e dados locais migrados com sucesso para o SQL Server!'})
    except Exception as e:
        logging.error(f"[DB] Erro durante a migração para o SQL Server: {e}")
        return jsonify({'success': False, 'error': f"Ocorreu um erro interno durante a migração: {str(e)}"}), 500

