from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify
from routes.utils import (
    require_auth, get_attr_value, check_permission,
    require_permission, require_api_permission,
    get_user_by_dn
)
from common import (
    load_config, get_user_by_samaccountname, get_group_by_name,
    get_service_account_connection, search_groups_for_user_addition,
    load_group_schedules, save_group_schedules
)
from forms.groups import GroupSearchForm, CreateScheduleForm, ManageMemberForm
from flask_wtf import FlaskForm
import ldap3
from ldap3 import BASE
from ldap3.utils.conv import escape_filter_chars
import logging
import re
import uuid
from datetime import datetime, date, timedelta

groups_bp = Blueprint('groups', __name__)

@groups_bp.route('/group_management', methods=['GET', 'POST'])
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
            search_filter = f"(&(objectClass=group)(cn=*{escape_filter_chars(query)}*))"
            conn.search(search_base, search_filter, attributes=['cn', 'description', 'member'])
            groups = conn.entries
            if not groups:
                flash(f"Nenhum grupo encontrado com o nome '{query}'.", "info")
        except Exception as e:
            flash(f"Erro ao buscar grupos: {e}", "error")
            logging.error(f"Erro ao buscar grupos com a query '{form.search_query.data}': {e}", exc_info=True)
    return render_template('manage_groups.html', form=form, groups=groups)

@groups_bp.route('/view_group/<group_name>')
@require_auth
@require_permission(action='can_manage_groups')
def view_group(group_name):
    form = FlaskForm()
    try:
        conn = get_service_account_connection()
        group = get_group_by_name(conn, group_name, attributes=['cn', 'description'])
        if not group:
            flash(f"Grupo '{group_name}' não encontrado.", 'error')
            return redirect(url_for('groups.group_management'))
        return render_template('view_group.html', group=group, form=form)
    except Exception as e:
        flash(f"Erro ao carregar a página do grupo: {e}", "error")
        logging.error(f"Erro ao carregar a view do grupo '{group_name}': {e}", exc_info=True)
        return redirect(url_for('groups.group_management'))

@groups_bp.route('/add_member/<group_name>', methods=['POST'])
@require_auth
@require_permission(action='can_manage_groups')
def add_member(group_name):
    try:
        user_sam = request.form.get('user_sam')
        if not user_sam:
            flash("Login do usuário não fornecido.", 'error')
            return redirect(url_for('groups.view_group', group_name=group_name))
        conn = get_service_account_connection()
        user_to_add = get_user_by_samaccountname(conn, user_sam, ['distinguishedName'])
        group_to_modify = get_group_by_name(conn, group_name, ['distinguishedName'])
        if user_to_add and group_to_modify:
            conn.extend.microsoft.add_members_to_groups([user_to_add.distinguishedName.value], group_to_modify.distinguishedName.value)
            if conn.result['description'] == 'success':
                flash(f"Usuário '{user_sam}' adicionado ao grupo '{group_name}' com sucesso.", 'success')
                logging.info(f"[ALTERAÇÃO] Usuário '{user_sam}' adicionado permanentemente ao grupo '{group_name}' por '{session.get('ad_user')}'.")
                try:
                    schedules = load_group_schedules()
                    schedules_to_keep = [s for s in schedules if not (s.get('user_sam') == user_sam and s.get('group_name') == group_name)]
                    if len(schedules_to_keep) < len(schedules):
                        save_group_schedules(schedules_to_keep)
                        logging.info(f"Agendamentos pendentes para '{user_sam}' no grupo '{group_name}' foram removidos devido à adição permanente.")
                except Exception as e:
                    logging.error(f"Erro ao limpar agendamentos para '{user_sam}' no grupo '{group_name}': {e}")
            else:
                flash(f"Falha ao adicionar usuário: {conn.result['message']}", 'error')
        else:
            flash("Usuário ou grupo não encontrado.", 'error')
    except Exception as e:
        flash(f"Erro ao adicionar usuário ao grupo: {e}", "error")
        logging.error(f"Erro ao adicionar usuário '{user_sam}' ao grupo '{group_name}': {e}", exc_info=True)
    return redirect(url_for('groups.view_group', group_name=group_name))

@groups_bp.route('/remove_member/<group_name>/<user_sam>', methods=['POST'])
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
                logging.info(f"[ALTERAÇÃO] Usuário '{user_sam}' removido permanentemente do grupo '{group_name}' por '{session.get('ad_user')}'.")
                try:
                    schedules = load_group_schedules()
                    schedules_to_keep = [s for s in schedules if not (s.get('user_sam') == user_sam and s.get('group_name') == group_name)]
                    if len(schedules_to_keep) < len(schedules):
                        save_group_schedules(schedules_to_keep)
                        logging.info(f"Agendamentos pendentes para '{user_sam}' no grupo '{group_name}' foram removidos devido à remoção permanente.")
                except Exception as e:
                    logging.error(f"Erro ao limpar agendamentos para '{user_sam}' no grupo '{group_name}': {e}")
            else:
                flash(f"Falha ao remover usuário: {conn.result['message']}", 'error')
        else:
            flash("Usuário ou grupo não encontrado.", 'error')
    except Exception as e:
        flash(f"Erro ao remover usuário do grupo: {e}", "error")
        logging.error(f"Erro ao remover usuário '{user_sam}' do grupo '{group_name}': {e}", exc_info=True)
    return redirect(url_for('groups.view_group', group_name=group_name))

@groups_bp.route('/group_schedules')
@require_auth
@require_permission(action='can_manage_groups')
def group_schedules():
    schedules = load_group_schedules()
    return render_template('group_schedules.html', schedules=schedules)

# API ENDPOINTS
@groups_bp.route('/api/group_members/<group_name>')
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
        paginated_dns = sorted(member_dns)[start:end]
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
        return jsonify({'error': str(e)}), 500

@groups_bp.route('/api/user_groups/<username>')
@require_auth
def api_user_groups(username):
    try:
        conn = get_read_connection()
        user = get_user_by_samaccountname(conn, username, attributes=['memberOf'])
        if not user:
            return jsonify([])
        group_dns = user.memberOf.values if 'memberOf' in user and user.memberOf.values else []
        groups_details = []
        for dn in group_dns:
            conn.search(dn, '(objectClass=group)', BASE, attributes=['cn', 'description'])
            if conn.entries:
                group_entry = conn.entries[0]
                groups_details.append({
                    'cn': get_attr_value(group_entry, 'cn'),
                    'description': get_attr_value(group_entry, 'description')
                })
        sorted_groups = sorted(groups_details, key=lambda g: g.get('cn', '').lower())
        return jsonify(sorted_groups)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@groups_bp.route('/api/search_groups', methods=['GET'])
@require_auth
@require_api_permission(action='can_manage_groups')
def api_search_groups():
    query = request.args.get('q', '')
    username = request.args.get('username', '')
    if not query or len(query) < 3:
        return jsonify([])
    try:
        conn = get_service_account_connection()
        groups = search_groups_for_user_addition(conn, query, username)
        return jsonify(groups)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@groups_bp.route('/api/add_user_to_group', methods=['POST'])
@require_auth
@require_api_permission(action='can_manage_groups')
def api_add_user_to_group():
    data = request.get_json()
    username = data.get('username')
    group_name = data.get('group_name')
    if not username or not group_name:
        return jsonify({'error': 'Nome de usuário e nome do grupo são obrigatórios.'}), 400
    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, ['distinguishedName'])
        group = get_group_by_name(conn, group_name, ['distinguishedName'])
        if not user or not group:
            return jsonify({'error': 'Usuário ou grupo não encontrado.'}), 404
        conn.extend.microsoft.add_members_to_groups([user.distinguishedName.value], group.distinguishedName.value)
        if conn.result['description'] == 'success':
            logging.info(f"[ALTERAÇÃO] Usuário '{username}' adicionado permanentemente ao grupo '{group_name}' por '{session.get('user_display_name')}'.")
            try:
                schedules = load_group_schedules()
                schedules_to_keep = [s for s in schedules if not (s.get('user_sam') == username and s.get('group_name') == group_name)]
                if len(schedules_to_keep) < len(schedules):
                    save_group_schedules(schedules_to_keep)
            except Exception as e:
                logging.error(f"Erro ao limpar agendamentos para '{username}' no grupo '{group_name}': {e}")
            return jsonify({'success': True, 'message': 'Usuário adicionado ao grupo com sucesso.'})
        else:
            raise Exception(f"Falha do LDAP: {conn.result['message']}")
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@groups_bp.route('/api/remove_user_from_group', methods=['POST'])
@require_auth
@require_api_permission(action='can_manage_groups')
def api_remove_user_from_group():
    data = request.get_json()
    username = data.get('username')
    group_name = data.get('group_name')
    if not username or not group_name:
        return jsonify({'error': 'Nome de usuário e nome do grupo são obrigatórios.'}), 400
    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, ['distinguishedName'])
        group = get_group_by_name(conn, group_name, ['distinguishedName'])
        if not user or not group:
            return jsonify({'error': 'Usuário ou grupo não encontrado.'}), 404
        conn.extend.microsoft.remove_members_from_groups([user.distinguishedName.value], group.distinguishedName.value)
        if conn.result['description'] == 'success':
            logging.info(f"[ALTERAÇÃO] Usuário '{username}' removido permanentemente do grupo '{group_name}' por '{session.get('user_display_name')}'.")
            try:
                schedules = load_group_schedules()
                schedules_to_keep = [s for s in schedules if not (s.get('user_sam') == username and s.get('group_name') == group_name)]
                if len(schedules_to_keep) < len(schedules):
                    save_group_schedules(schedules_to_keep)
            except Exception as e:
                logging.error(f"Erro ao limpar agendamentos para '{username}' no grupo '{group_name}': {e}")
            return jsonify({'success': True, 'message': 'Usuário removido do grupo com sucesso.'})
        else:
            raise Exception(f"Falha do LDAP: {conn.result['message']}")
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@groups_bp.route('/api/add_user_to_group_temp', methods=['POST'])
@require_auth
@require_api_permission(action='can_manage_groups')
def api_add_user_to_group_temp():
    data = request.get_json()
    username = data.get('username')
    group_name = data.get('group_name')
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    if not all([username, group_name, start_date_str, end_date_str]):
        return jsonify({'error': 'Todos os campos são obrigatórios.'}), 400
    try:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        today = date.today()
        if start_date > end_date:
            return jsonify({'error': 'A data de início não pode ser posterior à data de fim.'}), 400
        conn = get_service_account_connection()
        user_to_add = get_user_by_samaccountname(conn, username, ['distinguishedName'])
        group_to_modify = get_group_by_name(conn, group_name, ['distinguishedName'])
        if not user_to_add or not group_to_modify:
            return jsonify({'error': 'Usuário ou grupo não encontrado.'}), 404
        schedules = load_group_schedules()
        schedule_id = str(uuid.uuid4())
        add_schedule = {'id': schedule_id, 'user_sam': username, 'group_name': group_name, 'action': 'add', 'execution_date': start_date.isoformat()}
        schedules.append(add_schedule)
        if start_date <= today:
            conn.extend.microsoft.add_members_to_groups([user_to_add.distinguishedName.value], group_to_modify.distinguishedName.value)
            if conn.result['description'] != 'success':
                schedules.pop()
                raise Exception(f"Falha do LDAP: {conn.result['message']}")
        remove_schedule = {'id': schedule_id, 'user_sam': username, 'group_name': group_name, 'action': 'remove', 'execution_date': end_date.isoformat()}
        schedules.append(remove_schedule)
        save_group_schedules(schedules)
        return jsonify({'success': True, 'message': 'Agendamento realizado com sucesso.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@groups_bp.route('/api/remove_group_schedule', methods=['POST'])
@require_auth
@require_api_permission(action='can_manage_groups')
def api_remove_group_schedule():
    data = request.get_json()
    user_sam = data.get('user_sam')
    group_name = data.get('group_name')
    remove_now = data.get('remove_now', False)
    try:
        schedules = load_group_schedules()
        new_schedules = [s for s in schedules if not (s['user_sam'] == user_sam and s['group_name'] == group_name)]
        if len(new_schedules) == len(schedules):
            return jsonify({'error': 'Agendamento não encontrado.'}), 404
        save_group_schedules(new_schedules)
        msg = "Agendamento removido."
        if remove_now:
            conn = get_service_account_connection()
            user = get_user_by_samaccountname(conn, user_sam, ['distinguishedName'])
            group = get_group_by_name(conn, group_name, ['distinguishedName'])
            if user and group:
                conn.extend.microsoft.remove_members_from_groups([user.distinguishedName.value], group.distinguishedName.value)
                msg += " Usuário removido do grupo imediatamente."
        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@groups_bp.route('/api/search_users_for_group/<group_name>')
@require_auth
@require_api_permission(action='can_manage_groups')
def api_search_users_for_group(group_name):
    query = request.args.get('query', '')
    if len(query) < 3:
        return jsonify([])
    try:
        conn = get_read_connection()
        from common import search_groups_for_user_addition
        # Aqui, na verdade, queremos buscar usuários que NÃO estão no grupo
        # O helper search_groups_for_user_addition faz o oposto (busca grupos para um usuário)
        # Vamos implementar a busca de usuários aqui
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE')
        
        # Primeiro pegamos os membros do grupo para excluir
        group = get_group_by_name(conn, group_name, ['member'])
        current_members = set(group.member.values) if group and 'member' in group and group.member.values else set()
        
        search_filter = f"(&(objectClass=user)(objectCategory=person)(|(displayName=*{query}*)(sAMAccountName=*{query}*)))"
        conn.search(search_base, search_filter, attributes=['displayName', 'sAMAccountName', 'distinguishedName', 'title', 'l'])
        
        results = []
        for entry in conn.entries:
            if entry.distinguishedName.value not in current_members:
                results.append({
                    'displayName': entry.displayName.value or entry.sAMAccountName.value,
                    'sAMAccountName': entry.sAMAccountName.value,
                    'title': entry.title.value if 'title' in entry else 'N/A',
                    'city': entry.l.value if 'l' in entry else 'N/A'
                })
        return jsonify(results)
    except Exception as e:
        logging.error(f"Erro na busca de usuários para grupo: {e}")
        return jsonify({'error': str(e)}), 500

@groups_bp.route('/api/export_group_members/<group_name>')
@require_auth
@require_permission(action='can_export_data')
def api_export_group_members(group_name):
    import csv
    import io
    from flask import Response
    
    try:
        conn = get_read_connection()
        group = get_group_by_name(conn, group_name, ['member'])
        if not group or 'member' not in group or not group.member.values:
            return "Grupo não encontrado ou sem membros.", 404
            
        member_dns = group.member.values
        # Busca detalhes dos membros
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow(['Nome', 'Login', 'Email', 'Cargo', 'Departamento', 'Unidade'])
        
        # Busca em lotes para evitar filtros gigantes
        batch_size = 50
        for i in range(0, len(member_dns), batch_size):
            batch = member_dns[i:i+batch_size]
            ldap_filter = "(| " + "".join([f"(distinguishedName={dn})" for dn in batch]) + ")"
            conn.search(conn.server.info.other['defaultNamingContext'][0], ldap_filter, attributes=['displayName', 'sAMAccountName', 'mail', 'title', 'department', 'l'])
            for entry in conn.entries:
                writer.writerow([
                    entry.displayName.value or '',
                    entry.sAMAccountName.value or '',
                    entry.mail.value or '',
                    entry.title.value if 'title' in entry else '',
                    entry.department.value if 'department' in entry else '',
                    entry.l.value if 'l' in entry else ''
                ])
                
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename=membros_{group_name}.csv"}
        )
    except Exception as e:
        logging.error(f"Erro ao exportar membros do grupo {group_name}: {e}")
        return f"Erro ao exportar: {str(e)}", 500
