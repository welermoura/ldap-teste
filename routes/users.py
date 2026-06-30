from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify, Response, send_from_directory
from routes.utils import (
    require_auth, get_user_status, get_attr_value, check_permission,
    get_read_connection, get_password_reset_error_message,
    search_general_users, require_permission, require_api_permission,
    get_user_by_dn, get_ou_path
)
from common import (
    load_config, get_user_by_samaccountname, create_ad_user,
    get_service_account_connection, filetime_to_datetime,
    load_schedules, save_schedules, load_disable_schedules,
    save_disable_schedules, save_to_history, format_phone_number,
    get_ad_upn_suffixes
)
from forms.users import UserSearchForm, CreateUserForm, EditUserForm, DeleteUserForm
from flask_wtf import FlaskForm
import ldap3
from ldap3 import MODIFY_REPLACE, SUBTREE
import logging
import csv
import os
import re
import json
import re
import io
import uuid
from datetime import datetime, date, timedelta, timezone
from PIL import Image

users_bp = Blueprint('users', __name__)

@users_bp.route('/manage_users', methods=['GET', 'POST'])
@require_auth
def manage_users():
    if not check_permission(action='can_edit'):
        flash('Você não tem permissão para acessar esta página.', 'error')
        return redirect(url_for('main.dashboard'))
    form = UserSearchForm()
    users = []
    if form.validate_on_submit():
        try:
            conn = get_read_connection()
            users = search_general_users(conn, form.search_query.data.strip())
        except Exception as e:
            flash(f"Erro ao conectar ou buscar usuários: {e}", "error")
    return render_template('manage_users.html', form=form, users=users)

@users_bp.route('/create_user_form', methods=['GET', 'POST'])
@require_auth
@require_permission(action='can_create')
def create_user_form():
    form = CreateUserForm()
    config = load_config()
    
    # 1. Puxa sufixos manuais (removido, campo obsoleto)
    manual_suffixes = []
    
    # 2. Puxa sufixos automaticamente do AD
    auto_suffixes = []
    try:
        conn = get_read_connection()
        auto_suffixes = get_ad_upn_suffixes(conn)
    except Exception as e:
        logging.error(f"Erro ao buscar sufixos automáticos: {e}")
        
    # 3. Une e remove duplicatas, garantindo o prefixo @
    all_suffixes = set()
    for s in manual_suffixes + auto_suffixes:
        if not s.startswith('@'): s = '@' + s
        all_suffixes.add(s)
        
    if all_suffixes:
        # Ordena alfabeticamente
        sorted_suffixes = sorted(list(all_suffixes))
        form.upn_suffix.choices = [(s, s) for s in sorted_suffixes]
    else:
        # Fallback de última instância
        default_upn = '@' + '.'.join([part.split('=')[1] for part in config.get('AD_SEARCH_BASE', '').split(',') if part.strip().upper().startswith('DC=')])
        form.upn_suffix.choices = [(default_upn, default_upn)]

    if form.validate_on_submit():
        try:
            conn = get_read_connection()
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
                'upn_suffix': form.upn_suffix.data,
                'matricula': form.matricula.data,
                'telephone': form.telephone.data
            }
            session['found_users_sams'] = [u.sAMAccountName.value for u in users]
            return redirect(url_for('users.select_model'))
        except Exception as e:
            flash(f"Erro ao buscar modelo: {e}", 'error')
    return render_template('create_user_form.html', form=form)

@users_bp.route('/select_model', methods=['GET', 'POST'])
@require_auth
@require_permission(action='can_create')
def select_model():
    form_data = session.get('form_data')
    if not form_data:
        return redirect(url_for('main.dashboard'))
    users = []
    try:
        conn = get_read_connection()
        for sam_name in session.get('found_users_sams', []):
            user_entry = get_user_by_samaccountname(conn, sam_name, ['name', 'sAMAccountName', 'distinguishedName', 'physicalDeliveryOfficeName'])
            if user_entry:
                users.append({
                    'name': user_entry.name.value,
                    'sam_account': user_entry.sAMAccountName.value,
                    'office': str(user_entry.physicalDeliveryOfficeName.value) if 'physicalDeliveryOfficeName' in user_entry and user_entry.physicalDeliveryOfficeName.value else 'N/A',
                    'ou_path': get_ou_path(user_entry.entry_dn)
                })
    except Exception as e:
        flash(f"Erro ao carregar lista de modelos: {e}", 'error')
        return redirect(url_for('main.dashboard'))
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
            return redirect(url_for('main.dashboard'))
    return render_template('select_model.html', users=users, form_data=form_data, form=form)

@users_bp.route('/result')
@require_auth
def result():
    return redirect(url_for('main.dashboard'))

@users_bp.route('/ad-tree')
@require_auth
@require_permission(view='can_view_ad_tree')
def ad_tree():
    basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    try:
        manifest_path = os.path.join(basedir, 'frontend', 'dist', '.vite', 'manifest.json')
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        possible_keys = ['index.html', 'src/main.jsx', 'src/main.tsx', 'src/main.js']
        entry_point_key = next((key for key in possible_keys if key in manifest), None)

        if not entry_point_key:
            entry_point_key = next((key for key, value in manifest.items() if value.get('isEntry')), None)

        if not entry_point_key:
             entry_point_key = next(iter(manifest))

        entry_point = manifest[entry_point_key]
        js_file = entry_point.get('file')
        css_files = entry_point.get('css', [])
        css_file = css_files[0] if css_files else None

        return render_template('ad_tree.html', js_file=js_file, css_file=css_file)
    except Exception as e:
        logging.error(f"Erro ao carregar o manifesto do Vite: {e}", exc_info=True)
        return "Erro ao carregar a aplicação. Verifique os logs.", 500

@users_bp.route('/ad-tree/assets/<path:filename>')
def ad_tree_assets(filename):
    basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    return send_from_directory(os.path.join(basedir, 'frontend', 'dist', 'assets'), filename)

@users_bp.route('/view_user/<username>')
@require_auth
def view_user(username):
    try:
        conn = get_read_connection()
        attributes = ['*', 'msDS-UserPasswordExpiryTimeComputed', 'thumbnailPhoto']
        user = get_user_by_samaccountname(conn, username, attributes=attributes)
        if not user:
            flash("Usuário não encontrado ou você não tem permissão para ver os detalhes.", "error")
            return redirect(url_for('users.manage_users'))
        
        password_expiry_info = "Não aplicável (senha nunca expira ou não foi possível calcular)."
        if 'msDS-UserPasswordExpiryTimeComputed' in user and user['msDS-UserPasswordExpiryTimeComputed'].value:
            expiry_time_ft = user['msDS-UserPasswordExpiryTimeComputed'].value
            expiry_datetime = filetime_to_datetime(expiry_time_ft)
            if expiry_datetime:
                delta = expiry_datetime - datetime.now(timezone.utc)
                if delta.days >= 0:
                    password_expiry_info = f"Expira em {delta.days} dia(s) (em {expiry_datetime.strftime('%d-%m-%Y')})"
                else:
                    password_expiry_info = f"Expirou há {-delta.days} dia(s) (em {expiry_datetime.strftime('%d-%m-%Y')})"
            elif int(expiry_time_ft) == 9223372036854775807 or int(expiry_time_ft) == 0:
                 password_expiry_info = "A senha está configurada para nunca expirar."

        disable_schedules = {k.lower(): v for k, v in load_disable_schedules().items()}
        reactivation_schedules = {k.lower(): v for k, v in load_schedules().items()}
        username_lower = username.lower()
        absence_scheduled = username_lower in disable_schedules and username_lower in reactivation_schedules
        absence_info = None
        if absence_scheduled:
            try:
                deactivation_date = datetime.strptime(disable_schedules[username_lower], '%Y-%m-%d').strftime('%d-%m-%Y')
                reactivation_date = datetime.strptime(reactivation_schedules[username_lower], '%Y-%m-%d').strftime('%d-%m-%Y')
                absence_info = {
                    'deactivation': deactivation_date,
                    'reactivation': reactivation_date
                }
            except (ValueError, KeyError):
                absence_scheduled = False

        manager_info = None
        direct_reports_info = []
        try:
            manager_dn = get_attr_value(user, 'manager')
            if manager_dn:
                m_entry = get_user_by_dn(conn, manager_dn, ['displayName', 'sAMAccountName'])
                if m_entry:
                    manager_info = {
                        'name': get_attr_value(m_entry, 'displayName') or 'N/A',
                        'sam': get_attr_value(m_entry, 'sAMAccountName')
                    }

            direct_reports_dns = []
            if 'directReports' in user and user.directReports:
                if isinstance(user.directReports.value, list):
                    direct_reports_dns = user.directReports.value
                else:
                    direct_reports_dns = [user.directReports.value]

            for dr_dn in direct_reports_dns[:50]:
                dr_entry = get_user_by_dn(conn, dr_dn, ['displayName', 'sAMAccountName'])
                if dr_entry:
                    direct_reports_info.append({
                        'name': get_attr_value(dr_entry, 'displayName') or 'N/A',
                        'sam': get_attr_value(dr_entry, 'sAMAccountName')
                    })
            direct_reports_info.sort(key=lambda x: x['name'])
        except Exception as e:
            logging.error(f"Erro ao buscar info de hierarquia para {username}: {e}")

        has_photo = 'thumbnailPhoto' in user and user.thumbnailPhoto.value is not None
        form = EditUserForm()
        delete_form = DeleteUserForm()
        today_date = date.today().isoformat()
        return render_template('view_user.html', user=user, form=form, delete_form=delete_form, password_expiry_info=password_expiry_info, absence_scheduled=absence_scheduled, absence_info=absence_info, manager_info=manager_info, direct_reports_info=direct_reports_info, has_photo=has_photo, today_date=today_date)
    except Exception as e:
        flash(f"Erro ao buscar detalhes do usuário: {e}", "error")
        logging.error(f"Erro ao buscar detalhes do usuário para {username}: {e}", exc_info=True)
        return redirect(url_for('users.manage_users'))

@users_bp.route('/edit_user/<username>', methods=['GET', 'POST'])
@require_auth
@require_permission(action='can_edit')
def edit_user(username):
    try:
        conn = get_read_connection()
        user = get_user_by_samaccountname(conn, username)
        if not user:
            flash("Usuário não encontrado.", "error")
            return redirect(url_for('users.manage_users'))

        form = EditUserForm()
        auto_suffixes = get_ad_upn_suffixes(conn)
        if auto_suffixes:
            form.upn_suffix.choices = [(s, s) for s in auto_suffixes]
        else:
            current_upn = get_attr_value(user, 'userPrincipalName') or ""
            parts = current_upn.split('@', 1)
            suffix = '@' + parts[1] if len(parts) == 2 else '@'
            form.upn_suffix.choices = [(suffix, suffix)]
        config = load_config()
        
        editable_fields = {f.name for f in form if f.type not in ('CSRFTokenField', 'SubmitField') and check_permission(field=f.name)}
        # Remove email de editable_fields para que não seja processado no POST da aba Geral
        if 'email' in editable_fields:
            editable_fields.remove('email')

        if request.method == 'POST':
            for field_name, field in form._fields.items():
                if field_name not in editable_fields and field_name not in ['csrf_token', 'submit']:
                    field.validators = []

        if form.validate_on_submit():
            service_conn = get_service_account_connection()
            changes = {}
            changes_to_log = []

            if 'manager' in editable_fields:
                manager_sam = form.manager.data
                if manager_sam:
                    m_user = get_user_by_samaccountname(service_conn, manager_sam, ['distinguishedName'])
                    if not m_user:
                        flash(f"Gerente '{manager_sam}' não encontrado. Alteração cancelada.", 'error')
                        return redirect(url_for('users.edit_user', username=username))
                    new_manager_dn = m_user.distinguishedName.value
                    current_manager_dn = get_attr_value(user, 'manager')
                    if new_manager_dn != current_manager_dn:
                        changes['manager'] = [(ldap3.MODIFY_REPLACE, [new_manager_dn])]
                        changes_to_log.append(f"manager: alterado para '{manager_sam}'")
                else:
                    current_manager_dn = get_attr_value(user, 'manager')
                    if current_manager_dn:
                        changes['manager'] = [(ldap3.MODIFY_REPLACE, [])]
                        changes_to_log.append(f"manager: removido")

            field_to_attr = {
                'first_name': 'givenName', 'last_name': 'sn', 'initials': 'initials',
                'display_name': 'displayName', 'cn': 'cn', 'description': 'description', 'office': 'physicalDeliveryOfficeName',
                'telephone': 'telephoneNumber', 'email': 'mail', 'web_page': 'wWWHomePage',
                'street': 'streetAddress', 'post_office_box': 'postOfficeBox', 'city': 'l',
                'state': 'st', 'zip_code': 'postalCode', 'home_phone': 'homePhone',
                'pager': 'pager', 'mobile': 'mobile', 'fax': 'facsimileTelephoneNumber',
                'title': 'title', 'department': 'department', 'company': 'company',
                'matricula': 'extensionAttribute4'
            }

            # Remove 'cn' from regular changes, since RDN is handled via modify_dn
            cn_changed = False
            new_cn = ""
            original_cn = get_attr_value(user, 'cn')
            if 'cn' in editable_fields:
                new_cn = form.cn.data.strip() if form.cn.data else ""
                if new_cn and new_cn != original_cn:
                    cn_changed = True

            # Process UPN prefix/suffix modification
            if 'upn_prefix' in editable_fields or 'upn_suffix' in editable_fields:
                submitted_prefix = form.upn_prefix.data.strip() if 'upn_prefix' in editable_fields else None
                submitted_suffix = form.upn_suffix.data if 'upn_suffix' in editable_fields else None
                current_upn = get_attr_value(user, 'userPrincipalName') or ""
                parts = current_upn.split('@', 1)
                current_prefix = parts[0] if len(parts) >= 1 else ""
                current_suffix = '@' + parts[1] if len(parts) == 2 else ""
                final_prefix = submitted_prefix if submitted_prefix is not None else current_prefix
                final_suffix = submitted_suffix if submitted_suffix is not None else current_suffix
                new_upn = f"{final_prefix}{final_suffix}"
                if new_upn != current_upn:
                    changes['userPrincipalName'] = [(ldap3.MODIFY_REPLACE, [new_upn])]
                    changes_to_log.append(f"userPrincipalName: De '{current_upn}' Para '{new_upn}'")

            for field_name in editable_fields:
                if field_name in ['cn', 'upn_prefix', 'upn_suffix']:
                    continue
                if field_name in field_to_attr:
                    attr_name = field_to_attr[field_name]
                    submitted_value = getattr(form, field_name).data
                    if attr_name in ['telephoneNumber', 'homePhone', 'pager', 'mobile', 'facsimileTelephoneNumber']:
                        submitted_value = format_phone_number(submitted_value)
                    original_value = get_attr_value(user, attr_name)
                    if submitted_value != original_value:
                        changes[attr_name] = [(ldap3.MODIFY_REPLACE, [submitted_value or ''])]
                        changes_to_log.append(f"{attr_name}: De '{original_value}' Para '{submitted_value}'")

            if changes or cn_changed:
                modify_success = True
                if changes:
                    service_conn.modify(user.distinguishedName.value, changes)
                    modify_success = (service_conn.result['description'] == 'success')
                
                if modify_success:
                    flash('Usuário atualizado com sucesso!', 'success')
                    
                    # Renomeia o CN (Nome Completo) do usuário se o campo foi alterado
                    if cn_changed:
                        new_rdn = f"CN={new_cn}"
                        logging.info(f"Alteração de Nome Completo (CN) detectada. Renomeando CN do usuário '{username}' de '{original_cn}' para '{new_cn}'")
                        service_conn.modify_dn(user.distinguishedName.value, new_rdn)
                        if service_conn.result['description'] == 'success':
                            changes_to_log.append(f"cn: alterado de '{original_cn}' para '{new_cn}'")
                        else:
                            flash(f"Aviso: Atributos salvos, mas não foi possível renomear o Nome Completo (CN) no AD: {service_conn.result['message']}", 'warning')
                            logging.warning(f"Erro ao renomear CN do usuário '{username}' para '{new_cn}': {service_conn.result['message']}")
                            
                    log_details = "; ".join(changes_to_log)
                    log_message = f"[ALTERAÇÃO] Usuário '{username}' atualizado por '{session.get('user_display_name', session.get('ad_user'))}'. Detalhes: {log_details}"
                    logging.info(log_message)
                    save_to_history('alteration', username, f"Atualizado: {log_details}")
                else:
                    flash(f"Erro ao atualizar usuário: {service_conn.result['message']}", 'error')
            else:
                flash("Nenhum valor foi alterado.", "info")
            return redirect(url_for('users.view_user', username=username))

        for field in form:
            if field.name == 'manager':
                manager_dn = get_attr_value(user, 'manager')
                if manager_dn:
                    m_entry = get_user_by_dn(conn, manager_dn, ['sAMAccountName'])
                    if m_entry:
                        field.data = get_attr_value(m_entry, 'sAMAccountName')
                continue

            if field.name == 'upn_prefix':
                current_upn = get_attr_value(user, 'userPrincipalName') or ""
                parts = current_upn.split('@', 1)
                field.data = parts[0] if parts else ""
                continue

            if field.name == 'upn_suffix':
                current_upn = get_attr_value(user, 'userPrincipalName') or ""
                parts = current_upn.split('@', 1)
                field.data = '@' + parts[1] if len(parts) == 2 else ""
                continue

            field_to_attr = {
                'first_name': 'givenName', 'last_name': 'sn', 'initials': 'initials',
                'display_name': 'displayName', 'cn': 'cn', 'description': 'description', 'office': 'physicalDeliveryOfficeName',
                'telephone': 'telephoneNumber', 'email': 'mail', 'web_page': 'wWWHomePage',
                'street': 'streetAddress', 'post_office_box': 'postOfficeBox', 'city': 'l',
                'state': 'st', 'zip_code': 'postalCode', 'home_phone': 'homePhone',
                'pager': 'pager', 'mobile': 'mobile', 'fax': 'facsimileTelephoneNumber',
                'title': 'title', 'department': 'department', 'company': 'company',
                'matricula': 'extensionAttribute4'
            }
            attr_name = field_to_attr.get(field.name)
            if attr_name:
                field.data = get_attr_value(user, attr_name)
            


        # Fetch hierarchy info for the interactive Organograma tab
        manager_info = None
        direct_reports_info = []
        try:
            manager_dn = get_attr_value(user, 'manager')
            if manager_dn:
                m_entry = get_user_by_dn(conn, manager_dn, ['displayName', 'sAMAccountName'])
                if m_entry:
                    manager_info = {
                        'name': get_attr_value(m_entry, 'displayName') or 'N/A',
                        'sam': get_attr_value(m_entry, 'sAMAccountName')
                    }

            direct_reports_dns = []
            if 'directReports' in user and user.directReports:
                if isinstance(user.directReports.value, list):
                    direct_reports_dns = user.directReports.value
                else:
                    direct_reports_dns = [user.directReports.value]

            for dr_dn in direct_reports_dns[:50]:
                dr_entry = get_user_by_dn(conn, dr_dn, ['displayName', 'sAMAccountName'])
                if dr_entry:
                    direct_reports_info.append({
                        'name': get_attr_value(dr_entry, 'displayName') or 'N/A',
                        'sam': get_attr_value(dr_entry, 'sAMAccountName')
                    })
            direct_reports_info.sort(key=lambda x: x['name'])
        except Exception as e:
            logging.error(f"Erro ao buscar info de hierarquia para {username} em edit_user: {e}")

        return render_template('edit_user.html', 
                               form=form, 
                               username=username, 
                               user_name=get_attr_value(user, 'displayName'), 
                               editable_fields=editable_fields,
                               manager_info=manager_info,
                               direct_reports_info=direct_reports_info)
    except Exception as e:
        flash(f"Ocorreu um erro: {e}", "error")
        logging.error(f"Erro ao editar o usuário {username}: {e}", exc_info=True)
        return redirect(url_for('users.manage_users'))

@users_bp.route('/toggle_status/<username>', methods=['POST'])
@require_auth
@require_permission(action='can_disable')
def toggle_status(username):
    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, ['userAccountControl', 'distinguishedName'])
        if not user:
            flash("Usuário não encontrado.", "error")
            return redirect(url_for('users.manage_users'))
        uac = user.userAccountControl.value
        new_uac, action_message = (uac - 2, "ativada") if uac & 2 else (uac + 2, "desativada")
        conn.modify(user.distinguishedName.value, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(new_uac)])]})
        if action_message == "ativada":
            schedules = load_schedules()
            if username in schedules:
                del schedules[username]
                save_schedules(schedules)
        logging.info(f"[ALTERAÇÃO] Conta '{username}' foi {action_message} por '{session.get('user_display_name', session.get('ad_user'))}'.")
        save_to_history('deactivation' if action_message == 'desativada' else 'activation', username, f"Ação manual: {action_message} por {session.get('user_display_name')}")
        flash(f"Conta do usuário foi {action_message} com sucesso.", "success")
    except Exception as e:
        flash(f"Erro ao alterar status da conta: {e}", "error")
        logging.error(f"Erro em toggle_status for {username}: {e}", exc_info=True)
    return redirect(url_for('users.view_user', username=username))

@users_bp.route('/delete_user/<username>', methods=['POST'])
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
                return redirect(url_for('users.manage_users'))
            if form.confirm_title.data == (get_attr_value(user, 'title') or 'N/A') and form.confirm_sam.data == get_attr_value(user, 'sAMAccountName'):
                conn.delete(user.distinguishedName.value)
                if conn.result['description'] == 'success':
                    flash(f"Usuário '{username}' foi excluído permanentemente com sucesso.", "success")
                    logging.info(f"[EXCLUSÃO] Usuário '{username}' foi EXCLUÍDO por '{session.get('user_display_name', session.get('ad_user'))}'.")
                    save_to_history('exclusion', username, f"Usuário excluído por {session.get('user_display_name')}")
                    return redirect(url_for('users.manage_users'))
                else:
                    flash(f"Falha ao excluir usuário no Active Directory: {conn.result['message']}", "error")
            else:
                flash("A confirmação do cargo ou login falhou. A exclusão foi cancelada.", "error")
        except Exception as e:
            flash(f"Erro ao excluir usuário: {e}", "error")
            logging.error(f"Erro em delete_user for {username}: {e}", exc_info=True)
    else:
        flash("Erro de validação do formulário. A exclusão foi cancelada.", "danger")
    return redirect(url_for('users.view_user', username=username))

# API ENDPOINTS
@users_bp.route('/api/user_details/<username>')
@require_auth
@require_api_permission(action='can_edit')
def api_user_details(username):
    try:
        conn = get_read_connection()
        attributes_to_fetch = [
            'givenName', 'sn', 'initials', 'displayName', 'description',
            'physicalDeliveryOfficeName', 'telephoneNumber', 'mail', 'wWWHomePage',
            'streetAddress', 'postOfficeBox', 'l', 'st', 'postalCode',
            'homePhone', 'pager', 'mobile', 'facsimileTelephoneNumber',
            'title', 'department', 'company', 'extensionAttribute4'
        ]
        user = get_user_by_samaccountname(conn, username, attributes=attributes_to_fetch)
        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404
        user_details = {attr: get_attr_value(user, attr) for attr in attributes_to_fetch}
        return jsonify(user_details)
    except Exception as e:
        logging.error(f"Erro ao buscar detalhes para o usuário '{username}': {e}", exc_info=True)
        return jsonify({'error': 'Falha ao buscar detalhes do usuário.'}), 500

@users_bp.route('/api/edit_user/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_edit')
def api_edit_user(username):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Dados não fornecidos.'}), 400
    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, attributes=['*'])
        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404
        changes = {}
        field_to_attr = {
            'givenName': 'givenName', 'sn': 'sn', 'initials': 'initials',
            'displayName': 'displayName', 'description': 'description', 'physicalDeliveryOfficeName': 'physicalDeliveryOfficeName',
            'telephoneNumber': 'telephoneNumber', 'mail': 'mail', 'wWWHomePage': 'wWWHomePage',
            'streetAddress': 'streetAddress', 'post_office_box': 'postOfficeBox', 'l': 'l',
            'st': 'st', 'postalCode': 'postalCode', 'homePhone': 'homePhone',
            'pager': 'pager', 'mobile': 'mobile', 'facsimileTelephoneNumber': 'facsimileTelephoneNumber',
            'title': 'title', 'department': 'department', 'company': 'company',
            'matricula': 'extensionAttribute4'
        }
        changes_to_log = []
        for field, attr_name in field_to_attr.items():
            if field in data:
                submitted_value = data[field]
                if attr_name in ['telephoneNumber', 'homePhone', 'pager', 'mobile', 'facsimileTelephoneNumber']:
                    submitted_value = format_phone_number(submitted_value)
                original_value = get_attr_value(user, attr_name)
                if submitted_value != original_value:
                    changes[attr_name] = [(ldap3.MODIFY_REPLACE, [submitted_value or ''])]
                    changes_to_log.append(f"{attr_name}: de '{original_value}' para '{submitted_value}'")
        if not changes:
            return jsonify({'success': True, 'message': 'Nenhuma alteração detectada.'})
        conn.modify(user.distinguishedName.value, changes)
        if conn.result['description'] == 'success':
            log_details = "; ".join(changes_to_log)
            logging.info(f"[ALTERAÇÃO] Usuário '{username}' atualizado via API por '{session.get('user_display_name')}'. Detalhes: {log_details}")
            save_to_history('alteration', username, f"Atualizado via API por '{session.get('user_display_name')}': {log_details}")
            return jsonify({'success': True, 'message': 'Usuário updated successfully!'})
        else:
            raise Exception(f"Falha do LDAP: {conn.result['message']}")
    except Exception as e:
        logging.error(f"Erro ao editar o usuário '{username}' via API: {e}", exc_info=True)
        return jsonify({'error': f'Falha ao salvar alterações: {e}'}), 500

@users_bp.route('/api/reset_password/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_reset_password')
def api_reset_password(username):
    try:
        conn = get_service_account_connection()
        user = None
        sam_username = username
        if '@' in username:
            from ldap3.utils.conv import escape_filter_chars
            config = load_config()
            search_base = config.get('AD_SEARCH_BASE')
            if not search_base:
                if conn.server.info and conn.server.info.other:
                    search_base = conn.server.info.other['defaultNamingContext'][0]
                else:
                    raise Exception("AD_SEARCH_BASE não configurado.")
            search_filter = f"(|(mail={escape_filter_chars(username)})(userPrincipalName={escape_filter_chars(username)}))"
            conn.search(search_base, search_filter, attributes=['distinguishedName', 'sAMAccountName'])
            if conn.entries:
                user = conn.entries[0]
                sam_username = user.sAMAccountName.value if hasattr(user, 'sAMAccountName') and user.sAMAccountName else username
        else:
            user = get_user_by_samaccountname(conn, username)
            sam_username = username

        if not user:
            return jsonify({'success': False, 'error': 'Usuário não encontrado.'}), 404
        data = request.get_json()
        new_password = data.get('new_password')
        if not new_password:
            return jsonify({'success': False, 'error': 'A nova senha não pode estar em branco.'}), 400
        password_value = f'"{new_password}"'.encode('utf-16-le')
        conn.modify(user.distinguishedName.value, {'unicodePwd': [(MODIFY_REPLACE, [password_value])]})
        if conn.result['description'] == 'success':
            conn.modify(user.distinguishedName.value, {'pwdLastSet': [(MODIFY_REPLACE, [0])]})
            logging.info(f"[ALTERAÇÃO] A senha para '{sam_username}' foi resetada via API por '{session.get('user_display_name')}'.")
            save_to_history('alteration', sam_username, f"Senha resetada via API por '{session.get('user_display_name')}'")
            return jsonify({'success': True, 'message': 'Senha resetada com sucesso.'})
        else:
            error_message = get_password_reset_error_message(conn, conn.result['message'])
            return jsonify({'success': False, 'error': error_message}), 500
    except Exception as e:
        logging.error(f"Exceção em api_reset_password para {username}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@users_bp.route('/api/disable_user_temp/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_disable')
def api_disable_user_temp(username):
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
        if not (uac & 2):
            conn.modify(user.distinguishedName.value, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(uac + 2)])]})
        schedules = load_schedules()
        reactivation_date = (date.today() + timedelta(days=days))
        schedules[username.lower()] = reactivation_date.isoformat()
        save_schedules(schedules)
        logging.info(f"[ALTERAÇÃO] Conta de '{username}' desativada por {days} dias via API por '{session.get('user_display_name')}'. Reativação agendada para {reactivation_date.isoformat()}.")
        save_to_history('deactivation', username, f"Conta desativada por {days} dias via API por '{session.get('user_display_name')}'. Reativação agendada para {reactivation_date.isoformat()}.")
        return jsonify({'success': True, 'message': f"Usuário desativado. Reativação agendada para {reactivation_date.strftime('%d-%m-%Y')}."})
    except Exception as e:
        logging.error(f"Erro em api_disable_user_temp para '{username}': {e}", exc_info=True)
        return jsonify({'error': f'Falha ao desativar temporariamente: {e}'}), 500

@users_bp.route('/api/schedule_absence/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_disable')
def api_schedule_absence(username):
    data = request.get_json()
    deactivation_date_str = data.get('deactivation_date')
    reactivation_date_str = data.get('reactivation_date')
    if not deactivation_date_str or not reactivation_date_str:
        return jsonify({'error': 'Datas de desativação e reativação são obrigatórias.'}), 400
    try:
        deactivation_date = date.fromisoformat(deactivation_date_str)
        reactivation_date = date.fromisoformat(reactivation_date_str)
        today = date.today()
        if deactivation_date >= reactivation_date:
            return jsonify({'error': 'A data de reativação deve ser posterior à de desativação.'}), 400
        message = ""
        if deactivation_date <= today:
            conn = get_service_account_connection()
            user = get_user_by_samaccountname(conn, username, ['userAccountControl', 'distinguishedName'])
            if not user:
                return jsonify({'error': 'Usuário não encontrado.'}), 404
            uac = user.userAccountControl.value
            if not (uac & 2):
                conn.modify(user.distinguishedName.value, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(uac + 2)])]})
                logging.info(f"[ALTERAÇÃO] Conta de '{username}' desativada IMEDIATAMENTE (agendamento de ausência) por '{session.get('user_display_name')}'.")
                save_to_history('deactivation', username, f"Desativado imediatamente via agendamento de ausência por {session.get('user_display_name')}")
                message = "Usuário desativado imediatamente. "
            else:
                message = "Usuário já estava desativado. "
        else:
            disable_schedules = load_disable_schedules()
            disable_schedules[username.lower()] = deactivation_date.isoformat()
            save_disable_schedules(disable_schedules)
            logging.info(f"[AGENDAMENTO] Desativação de '{username}' agendada para {deactivation_date_str} por '{session.get('user_display_name')}'.")
            save_to_history('alteration', username, f"Desativação de ausência agendada para {deactivation_date_str} por '{session.get('user_display_name')}'")
            message = f"Desativação agendada para {deactivation_date.strftime('%d-%m-%Y')}. "
        reactivation_schedules = load_schedules()
        reactivation_schedules[username.lower()] = reactivation_date.isoformat()
        save_schedules(reactivation_schedules)
        logging.info(f"[AGENDAMENTO] Reativação de '{username}' agendada para {reactivation_date_str} por '{session.get('user_display_name')}'.")
        save_to_history('alteration', username, f"Reativação de ausência agendada para {reactivation_date_str} por '{session.get('user_display_name')}'")
        message += f"Reativação agendada para {reactivation_date.strftime('%d-%m-%Y')}."
        return jsonify({'success': True, 'message': message})
    except ValueError:
        return jsonify({'error': 'Formato de data inválido. Use AAAA-MM-DD.'}), 400
    except Exception as e:
        logging.error(f"Erro em api_schedule_absence para '{username}': {e}", exc_info=True)
        return jsonify({'error': f'Falha ao agendar ausência: {e}'}), 500

@users_bp.route('/api/schedule_reactivation/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_disable')
def api_schedule_reactivation(username):
    data = request.get_json()
    reactivation_date_str = data.get('reactivation_date')
    if not reactivation_date_str:
        return jsonify({'error': 'A data de reativação é obrigatória.'}), 400
    try:
        reactivation_date = date.fromisoformat(reactivation_date_str)
        today = date.today()
        
        if reactivation_date <= today:
            # Reativar IMEDIATAMENTE
            conn = get_service_account_connection()
            user = get_user_by_samaccountname(conn, username, ['userAccountControl', 'distinguishedName'])
            if not user:
                return jsonify({'error': 'Usuário não encontrado.'}), 404
            
            uac = user.userAccountControl.value
            if uac & 2: # Se a conta estiver desativada
                new_uac = uac - 2
                conn.modify(user.distinguishedName.value, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(new_uac)])]})
                if conn.result['description'] == 'success':
                    # Limpa qualquer agendamento de reativação pendente
                    schedules = load_schedules()
                    username_lower = username.lower()
                    if username_lower in schedules:
                        del schedules[username_lower]
                        save_schedules(schedules)
                    
                    logging.info(f"[ALTERAÇÃO] Conta '{username}' reativada IMEDIATAMENTE por '{session.get('user_display_name')}'.")
                    save_to_history('activation', username, f"Reativado manualmente por {session.get('user_display_name')}")
                    return jsonify({'success': True, 'message': 'Conta reativada com sucesso!'})
                else:
                    return jsonify({'error': f"Falha ao reativar no AD: {conn.result['message']}"}), 500
            else:
                return jsonify({'success': True, 'message': 'A conta já está ativa.'})
        else:
            # Agendar para o FUTURO
            schedules = load_schedules()
            schedules[username.lower()] = reactivation_date.isoformat()
            save_schedules(schedules)
            logging.info(f"[AGENDAMENTO] Reativação de '{username}' agendada para {reactivation_date_str} por '{session.get('user_display_name')}'.")
            save_to_history('alteration', username, f"Reativação agendada para {reactivation_date_str} por '{session.get('user_display_name')}'")
            return jsonify({'success': True, 'message': f"Reativação agendada para {reactivation_date.strftime('%d-%m-%Y')}."})
            
    except ValueError:
        return jsonify({'error': 'Formato de data inválido. Use AAAA-MM-DD.'}), 400
    except Exception as e:
        logging.error(f"Erro em api_schedule_reactivation para '{username}': {e}", exc_info=True)
        return jsonify({'error': f'Falha ao processar reativação: {e}'}), 500

@users_bp.route('/api/cancel_absence/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_disable')
def api_cancel_absence(username):
    try:
        disable_schedules = load_disable_schedules()
        reactivation_schedules = load_schedules()
        username_lower = username.lower()
        deactivation_scheduled = username_lower in disable_schedules
        reactivation_scheduled = username_lower in reactivation_schedules
        if not deactivation_scheduled and not reactivation_scheduled:
            return jsonify({'error': 'Nenhum agendamento de ausência encontrado para este usuário.'}), 404
        message = ""
        if deactivation_scheduled:
            del disable_schedules[username_lower]
            save_disable_schedules(disable_schedules)
            logging.info(f"[AGENDAMENTO CANCELADO] A desativação futura de '{username}' foi cancelada por '{session.get('user_display_name')}'.")
            save_to_history('alteration', username, f"Agendamento de desativação cancelado por '{session.get('user_display_name')}'")
            message += "Agendamento de desativação cancelado. "
        if reactivation_scheduled:
            del reactivation_schedules[username_lower]
            save_schedules(reactivation_schedules)
            conn = get_service_account_connection()
            user = get_user_by_samaccountname(conn, username, ['userAccountControl', 'distinguishedName'])
            if user:
                uac = user.userAccountControl.value
                if uac & 2:
                    conn.modify(user.distinguishedName.value, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(uac - 2)])]})
                    logging.info(f"[ALTERAÇÃO] Conta de '{username}' foi reativada imediatamente devido ao cancelamento da ausência por '{session.get('user_display_name')}'.")
                    save_to_history('activation', username, f"Conta reativada (ausência cancelada) por '{session.get('user_display_name')}'")
                    message += "Usuário foi reativado. "
                else:
                    message += "Agendamento de reativação removido (usuário já estava ativo). "
        return jsonify({'success': True, 'message': f'Agendamento de ausência cancelado. {message}'})
    except Exception as e:
        logging.error(f"Erro em api_cancel_absence para '{username}': {e}", exc_info=True)
        return jsonify({'error': f'Falha ao cancelar o agendamento: {e}'}), 500

@users_bp.route('/api/upload_photo/<username>', methods=['POST'])
@require_auth
@require_permission(action='can_edit')
def api_upload_photo(username):
    if 'photo' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado.'}), 400
    photo_file = request.files['photo']
    if not photo_file or photo_file.filename == '':
        return jsonify({'error': 'Nenhum arquivo selecionado.'}), 400
    try:
        raw_bytes = photo_file.read()
        img = Image.open(io.BytesIO(raw_bytes))
        img = img.convert('RGB')
        img.thumbnail((200, 200), Image.LANCZOS)
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        jpeg_bytes = output.getvalue()
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, attributes=['distinguishedName'])
        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404
        conn.modify(user.distinguishedName.value, {'thumbnailPhoto': [(ldap3.MODIFY_REPLACE, [jpeg_bytes])]})
        if conn.result['description'] == 'success':
            logging.info(f"[FOTO] Foto do usuário '{username}' atualizada por '{session.get('user_display_name')}'.")
            save_to_history('alteration', username, f"Foto atualizada por '{session.get('user_display_name')}'")
            return jsonify({'success': True, 'message': 'Foto atualizada com sucesso!'})
        else:
            raise Exception(f"Erro no LDAP: {conn.result['description']}")
    except Exception as e:
        logging.error(f"Erro ao fazer upload de foto para {username}: {e}", exc_info=True)
        return jsonify({'error': f'Erro ao processar a imagem: {str(e)}'}), 500

@users_bp.route('/api/user_photo/<username>')
@require_auth
def api_user_photo(username):
    try:
        conn = get_read_connection()
        user = get_user_by_samaccountname(conn, username, attributes=['thumbnailPhoto'])
        if not user or 'thumbnailPhoto' not in user or not user.thumbnailPhoto.value:
            return "No photo", 404
        return Response(user.thumbnailPhoto.value, mimetype='image/jpeg')
    except Exception as e:
        return "Error", 404

@users_bp.route('/api/remove_photo/<username>', methods=['DELETE'])
@require_auth
@require_permission(action='can_edit')
def api_remove_photo(username):
    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, attributes=['distinguishedName'])
        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404
        conn.modify(user.distinguishedName.value, {'thumbnailPhoto': [(ldap3.MODIFY_REPLACE, [])]})
        if conn.result['description'] == 'success':
            logging.info(f"[FOTO] Foto do usuário '{username}' removida por '{session.get('user_display_name')}'.")
            save_to_history('alteration', username, f"Foto removida por '{session.get('user_display_name')}'")
            return jsonify({'success': True, 'message': 'Foto removida com sucesso!'})
        else:
            raise Exception(f"Erro no LDAP: {conn.result['description']}")
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/ad-tree/data')
@require_auth
@require_permission(view='can_view_ad_tree')
def api_ad_tree_data():
    try:
        conn = get_read_connection()
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE')
        attributes = ['cn', 'displayName', 'sAMAccountName', 'title', 'department', 'manager', 'distinguishedName', 'l', 'thumbnailPhoto']
        search_filter = '(&(objectClass=user)(objectCategory=person)(userPrincipalName=*)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))'
        
        entry_generator = conn.extend.standard.paged_search(
            search_base=search_base,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=attributes,
            paged_size=1000,
            generator=True
        )
        
        nodes = []
        for entry in entry_generator:
            if entry['type'] != 'searchResEntry':
                continue
            
            attrs = entry['attributes']
            # Safely extract single values from lists
            def get_val(key, default=''):
                val = attrs.get(key)
                if isinstance(val, list):
                    return val[0] if val else default
                return val or default
                
            nodes.append({
                'id': entry['dn'],
                'name': get_val('displayName') or get_val('cn'),
                'username': get_val('sAMAccountName'),
                'title': get_val('title', 'Colaborador'),
                'department': get_val('department'),
                'location': get_val('l'),
                'managerId': get_val('manager', None),
                'hasPhoto': bool(attrs.get('thumbnailPhoto'))
            })
            
        return jsonify(nodes)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/action_permissions')
@require_auth
def api_action_permissions():
    """Retorna as permissões de ações para o usuário logado."""
    actions = ['can_create', 'can_disable', 'can_reset_password', 'can_edit', 'can_manage_groups', 'can_delete_user', 'can_move_user', 'can_edit_users']
    user_permissions = {action: check_permission(action=action) for action in actions}
    # Adiciona aliases se necessário para compatibilidade com o frontend
    user_permissions['can_manage_hierarchy'] = user_permissions['can_edit_users']
    return jsonify(user_permissions)

@users_bp.route('/export_ad_data', methods=['GET', 'POST'])
@require_auth
@require_permission(view='can_export_data')
def export_ad_data():
    available_attributes = {
        'description': 'Descrição',
        'mail': 'Email',
        'givenName': 'Nome',
        'sn': 'Sobrenome',
        'title': 'Cargo',
        'company': 'Empresa',
        'physicalDeliveryOfficeName': 'Escritório',
        'department': 'Departamento',
        'sAMAccountName': 'Login (Pre-2k)',
        'userPrincipalName': 'Login (UPN)',
        'displayName': 'Nome para Exibição',
        'extensionAttribute4': 'Matrícula',
        'whenCreated': 'Data de Criação',
        'whenChanged': 'Última Alteração'
    }

    if request.method == 'GET':
        try:
            conn = get_read_connection()
            config = load_config()
            default_search_base = config.get('AD_SEARCH_BASE')
            
            form = FlaskForm()
            return render_template('export_setup.html', 
                                 form=form,
                                 available_attributes=available_attributes,
                                 default_search_base=default_search_base)
        except Exception as e:
            logging.error(f"Erro ao carregar setup de exportação: {e}")
            flash("Erro ao carregar configurações de exportação.", "error")
            return redirect(url_for('main.dashboard'))

    # Processamento do POST (Download)
    try:
        conn = get_service_account_connection()
        config = load_config()
        
        selected_search_base = request.form.get('search_base', config.get('AD_SEARCH_BASE'))
        selected_attrs = request.form.getlist('attributes')
        only_active = request.form.get('only_active') == 'on'
        export_format = request.form.get('export_format', 'csv')

        if not selected_attrs:
            flash("Selecione pelo menos um campo para exportar.", "error")
            return redirect(url_for('users.export_ad_data'))

        # Filtro base
        search_filter = "(&(objectClass=user)(objectCategory=person)(sAMAccountName=*))"
        if only_active:
            search_filter = "(&(objectClass=user)(objectCategory=person)(sAMAccountName=*)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))"

        # Cabeçalhos baseados na seleção
        header = [available_attributes[attr] for attr in selected_attrs]

        # Garantir que sAMAccountName seja buscado para validação, mesmo que não selecionado
        search_attrs = list(set(selected_attrs) | {'sAMAccountName'})

        entry_generator = conn.extend.standard.paged_search(
            search_base=selected_search_base,
            search_filter=search_filter,
            attributes=search_attrs,
            paged_size=500,
            generator=True
        )

        rows = []
        for entry in entry_generator:
            if entry['type'] != 'searchResEntry': continue
            attrs = entry.get('attributes', {})
            if not attrs.get('sAMAccountName'): continue

            row = []
            for attr in selected_attrs:
                val = attrs.get(attr)
                # Remove os [] de listas e converte para string amigável
                if isinstance(val, (list, tuple)):
                    val = "; ".join(map(str, val))
                elif hasattr(val, '__iter__') and not isinstance(val, (str, bytes)):
                    # Caso seja um objeto iterável do ldap3 mas não list/tuple
                    val = "; ".join(map(str, val))
                
                row.append(str(val) if val is not None else '')
            rows.append(row)

        if export_format == 'xlsx':
            import openpyxl
            from openpyxl.styles import Font
            
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Exportação AD"
            
            # Escreve cabeçalho com negrito
            ws.append(header)
            for cell in ws[1]:
                cell.font = Font(bold=True)
            
            # Escreve dados
            for row in rows:
                ws.append(row)
            
            # Ajusta largura das colunas (aproximado)
            for col in ws.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except: pass
                adjusted_width = (max_length + 2)
                ws.column_dimensions[column].width = min(adjusted_width, 50)

            output = io.BytesIO()
            wb.save(output)
            content = output.getvalue()
            output.close()
            
            return Response(
                content,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": "attachment;filename=export_ad_custom.xlsx"}
            )
        else:
            # Gerar CSV
            output = io.StringIO()
            output.write('\ufeff')  # BOM para Excel UTF-8
            writer = csv.writer(output, quoting=csv.QUOTE_ALL)
            writer.writerow(header)
            writer.writerows(rows)
            
            content = output.getvalue()
            output.close()
            
            return Response(
                content,
                mimetype="text/csv",
                headers={
                    "Content-Disposition": "attachment;filename=export_ad_custom.csv",
                    "Content-Type": "text/csv; charset=utf-8-sig"
                }
            )

    except Exception as e:
        logging.error(f"Erro na exportação customizada: {e}", exc_info=True)
        flash(f"Erro ao gerar exportação: {e}", "error")
        return redirect(url_for('users.export_ad_data'))

# --- AD EXPLORER API ENDPOINTS ---

@users_bp.route('/api/ou_members/<path:ou_dn>')
@require_auth
def api_ou_members(ou_dn):
    try:
        from routes.utils import get_ou_members
        conn = get_read_connection()
        members = get_ou_members(conn, ou_dn)
        return jsonify(members)
    except Exception as e:
        logging.error(f"Erro ao buscar membros para {ou_dn}: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/recycle_bin')
@require_auth
def api_recycle_bin():
    try:
        from routes.utils import get_recycle_bin_items
        conn = get_read_connection()
        items = get_recycle_bin_items(conn)
        return jsonify(items)
    except Exception as e:
        logging.error(f"Erro ao buscar itens da lixeira: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/move_object', methods=['POST'])
@require_auth
@require_permission(action='can_move_user')
def api_move_object():
    data = request.get_json()
    object_dn = data.get('object_dn')
    target_ou_dn = data.get('target_ou_dn')
    
    if not object_dn or not target_ou_dn:
        return jsonify({'success': False, 'error': 'DN do objeto e da OU de destino são obrigatórios.'}), 400
        
    try:
        conn = get_service_account_connection()
        # Extrai o RDN (ex: CN=Nome)
        rdn = object_dn.split(',')[0]
        conn.modify_dn(object_dn, rdn, new_superior=target_ou_dn)
        
        if conn.result['description'] == 'success':
            logging.info(f"[MOVIMENTAÇÃO] Objeto '{object_dn}' movido para '{target_ou_dn}' por '{session.get('user_display_name')}'.")
            name_val = rdn.split('=')[1] if '=' in rdn else rdn
            save_to_history('movement', name_val, f"Objeto movido de '{object_dn}' para '{target_ou_dn}' por '{session.get('user_display_name')}'")
            return jsonify({'success': True, 'message': 'Objeto movido com sucesso.'})
        else:
            return jsonify({'success': False, 'error': conn.result['description']}), 500
    except Exception as e:
        logging.error(f"Erro ao mover objeto: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@users_bp.route('/api/toggle_object_status', methods=['POST'])
@require_auth
@require_permission(action='can_disable')
def api_toggle_object_status():
    data = request.get_json()
    dn = data.get('dn')
    sam = data.get('sam')
    
    try:
        conn = get_service_account_connection()
        user = get_user_by_dn(conn, dn, ['userAccountControl'])
        if not user:
            return jsonify({'error': 'Objeto não encontrado.'}), 404
            
        uac = user.userAccountControl.value
        new_uac = uac ^ 2 # Toggle bit 2 (ADS_UF_ACCOUNTDISABLE)
        action_message = "ativada" if not (new_uac & 2) else "desativada"
        
        conn.modify(dn, {'userAccountControl': [(MODIFY_REPLACE, [new_uac])]})
        
        if conn.result['description'] == 'success':
            logging.info(f"[ALTERAÇÃO] Conta '{sam or dn}' foi {action_message} por '{session.get('user_display_name')}'.")
            save_to_history('deactivation' if action_message == 'desativada' else 'activation', sam or dn, f"Conta {action_message} via toggle por '{session.get('user_display_name')}'")
            return jsonify({'success': True, 'message': f"Conta {action_message} com sucesso."})
        else:
            return jsonify({'success': False, 'error': conn.result['description']}), 500
    except Exception as e:
        logging.error(f"Erro em api_toggle_object_status: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/restore_object', methods=['POST'])
@require_auth
@require_permission(action='can_delete_user')
def api_restore_object():
    data = request.get_json()
    dn = data.get('dn')
    
    if not dn:
        return jsonify({'error': 'DN é obrigatório.'}), 400
        
    try:
        conn = get_service_account_connection()
        # Busca o item para pegar o lastKnownParent
        conn.search(dn, '(isDeleted=TRUE)', attributes=['lastKnownParent', 'msDS-LastKnownRDN'], controls=[('1.2.840.113556.1.4.417', True)])
        if not conn.entries:
            return jsonify({'error': 'Objeto não encontrado na lixeira.'}), 404
            
        entry = conn.entries[0]
        last_parent = entry.lastKnownParent.value
        last_rdn = entry['msDS-LastKnownRDN'].value
        
        # Para restaurar, modificamos o isDeleted para FALSE e movemos para o lastKnownParent
        # Isso geralmente requer controles específicos e permissões elevadas.
        conn.modify(dn, {'isDeleted': [(MODIFY_REPLACE, [])]}, controls=[('1.2.840.113556.1.4.417', True)])
        save_to_history('activation', dn, f"Objeto restaurado da lixeira por '{session.get('user_display_name')}'")
        return jsonify({'success': True, 'message': 'Comando de restauração enviado.'})
    except Exception as e:
        logging.error(f"Erro ao restaurar objeto: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/delete_object', methods=['DELETE'])
@require_auth
@require_permission(action='can_delete_user')
def api_delete_object():
    data = request.get_json()
    dn = data.get('dn')
    name = data.get('name')
    
    if not dn:
        return jsonify({'error': 'DN é obrigatório.'}), 400
        
    try:
        conn = get_service_account_connection()
        
        # Verifica se o objeto deletado é um grupo e pega seu sAMAccountName antes de deletar
        is_group = False
        sam_name = None
        try:
            conn.search(dn, '(objectClass=group)', attributes=['sAMAccountName'])
            if conn.entries:
                is_group = True
                sam_name = conn.entries[0].sAMAccountName.value
        except Exception as e_search:
            logging.warning(f"Erro ao verificar se o objeto a ser deletado é um grupo: {e_search}")
            
        conn.delete(dn)
        
        if conn.result['description'] == 'success':
            logging.info(f"[EXCLUSÃO] Objeto '{name or dn}' excluído por '{session.get('user_display_name')}'.")
            save_to_history('exclusion', name or dn, f"Objeto excluído via API por '{session.get('user_display_name')}'")
            
            # Se for um grupo e a integração com o Zimbra estiver ativa, exclui a DL correspondente no Zimbra
            if is_group and sam_name:
                config = load_config()
                if config.get('ZIMBRA_ENABLED', False):
                    try:
                        from routes.zimbra import load_zimbra_mappings, save_zimbra_mappings
                        mappings = load_zimbra_mappings()
                        target_mapping = None
                        for m in mappings:
                            if m.get('ad_group_name') == sam_name:
                                target_mapping = m
                                break
                                
                        if target_mapping:
                            zimbra_email = target_mapping.get('zimbra_dl_email')
                            if zimbra_email:
                                zimbra_url = config.get('ZIMBRA_API_URL')
                                zimbra_user = config.get('ZIMBRA_ADMIN_USER')
                                zimbra_password = config.get('ZIMBRA_ADMIN_PASSWORD')
                                if zimbra_url and zimbra_user and zimbra_password:
                                    from routes.zimbra_api import ZimbraSOAPClient
                                    client = ZimbraSOAPClient(zimbra_url, zimbra_user, zimbra_password)
                                    try:
                                        client.delete_dl(zimbra_email)
                                        logging.info(f"[ZIMBRA] DL '{zimbra_email}' excluída automaticamente após exclusão do grupo AD '{sam_name}'.")
                                    except Exception as ez_del:
                                        logging.error(f"[ZIMBRA] Erro ao excluir DL '{zimbra_email}' do Zimbra: {ez_del}")
                            
                            # Remove o mapeamento
                            mappings = [m for m in mappings if m.get('ad_group_name') != sam_name]
                            save_zimbra_mappings(mappings)
                    except Exception as ez:
                        logging.error(f"[ZIMBRA] Erro ao limpar mapeamento do Zimbra após exclusão do grupo '{sam_name}': {ez}")
            
            return jsonify({'success': True, 'message': 'Objeto excluído com sucesso.'})
        else:
            return jsonify({'success': False, 'error': conn.result['description']}), 500
    except Exception as e:
        logging.error(f"Erro ao excluir objeto: {e}")
        return jsonify({'error': str(e)}), 500

# --- HIERARCHY MANAGEMENT ENDPOINTS ---

@users_bp.route('/api/set_manager', methods=['POST'])
@require_auth
@require_permission(action='can_edit_users')
def api_set_manager():
    data = request.get_json()
    user_sam = data.get('user_sam')
    manager_sam = data.get('manager_sam')
    
    if not user_sam or not manager_sam:
        return jsonify({'error': 'SAM do usuário e do gerente são obrigatórios.'}), 400
        
    try:
        service_conn = get_service_account_connection()
        user_entry = get_user_by_samaccountname(service_conn, user_sam, ['distinguishedName'])
        manager_entry = get_user_by_samaccountname(service_conn, manager_sam, ['distinguishedName'])
        
        if not user_entry:
            return jsonify({'error': f"Usuário '{user_sam}' não encontrado."}), 404
        if not manager_entry:
            return jsonify({'error': f"Gerente '{manager_sam}' não encontrado."}), 404
            
        manager_dn = manager_entry.distinguishedName.value
        service_conn.modify(user_entry.distinguishedName.value, {'manager': [(MODIFY_REPLACE, [manager_dn])]})
        
        if not service_conn.result['description'] == 'success':
            return jsonify({'error': service_conn.result['description']}), 500
            
        logging.info(f"Gerente de '{user_sam}' definido como '{manager_sam}' por '{session.get('user_display_name')}'.")
        save_to_history('alteration', user_sam, f"Gerente definido como '{manager_sam}' por '{session.get('user_display_name')}'")
        return jsonify({'message': 'Gerente atualizado com sucesso.'})
    except Exception as e:
        logging.error(f"Erro ao definir gerente: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/add_subordinate', methods=['POST'])
@require_auth
@require_permission(action='can_edit_users')
def api_add_subordinate():
    data = request.get_json()
    manager_sam = data.get('manager_sam')
    subordinate_sam = data.get('subordinate_sam')
    
    if not manager_sam or not subordinate_sam:
        return jsonify({'error': 'SAM do gerente e do subordinado são obrigatórios.'}), 400
        
    try:
        service_conn = get_service_account_connection()
        manager_entry = get_user_by_samaccountname(service_conn, manager_sam, ['distinguishedName'])
        subordinate_entry = get_user_by_samaccountname(service_conn, subordinate_sam, ['distinguishedName'])
        
        if not manager_entry:
            return jsonify({'error': f"Gerente '{manager_sam}' não encontrado."}), 404
        if not subordinate_entry:
            return jsonify({'error': f"Subordinado '{subordinate_sam}' não encontrado."}), 404
            
        manager_dn = manager_entry.distinguishedName.value
        service_conn.modify(subordinate_entry.distinguishedName.value, {'manager': [(MODIFY_REPLACE, [manager_dn])]})
        
        if not service_conn.result['description'] == 'success':
            return jsonify({'error': service_conn.result['description']}), 500
            
        logging.info(f"'{subordinate_sam}' definido como subordinado de '{manager_sam}' por '{session.get('user_display_name')}'.")
        save_to_history('alteration', subordinate_sam, f"Gerente definido como '{manager_sam}' (subordinado adicionado) por '{session.get('user_display_name')}'")
        return jsonify({'message': 'Subordinado adicionado com sucesso.'})
    except Exception as e:
        logging.error(f"Erro ao adicionar subordinado: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/remove_subordinate', methods=['POST'])
@require_auth
@require_permission(action='can_edit_users')
def api_remove_subordinate():
    data = request.get_json()
    subordinate_sam = data.get('subordinate_sam')
    
    if not subordinate_sam:
        return jsonify({'error': 'SAM do subordinado é obrigatório.'}), 400
        
    try:
        service_conn = get_service_account_connection()
        subordinate_entry = get_user_by_samaccountname(service_conn, subordinate_sam, ['distinguishedName'])
        
        if not subordinate_entry:
            return jsonify({'error': f"Subordinado '{subordinate_sam}' não encontrado."}), 404
            
        from ldap3 import MODIFY_DELETE
        service_conn.modify(subordinate_entry.distinguishedName.value, {'manager': [(MODIFY_DELETE, [])]})
        
        if not service_conn.result['description'] == 'success':
            if 'no such attribute' in service_conn.result['description'].lower():
                 return jsonify({'message': 'O usuário já não possuía gerente.'})
            return jsonify({'error': service_conn.result['description']}), 500
            
        logging.info(f"Gerente de '{subordinate_sam}' removido por '{session.get('user_display_name')}'.")
        save_to_history('alteration', subordinate_sam, f"Gerente removido por '{session.get('user_display_name')}'")
        return jsonify({'message': 'Subordinado removido com sucesso.'})
    except Exception as e:
        logging.error(f"Erro ao remover subordinado: {e}")
        return jsonify({'error': str(e)}), 500



# --- EXCHANGE MANAGEMENT ENDPOINTS ---

@users_bp.route('/api/user_exchange/<username>', methods=['GET'])
@require_auth
@require_api_permission(action='can_manage_exchange')
def api_user_exchange(username):
    try:
        conn = get_read_connection()
        user = get_user_by_samaccountname(conn, username, attributes=[
            'proxyAddresses', 'mail', 'msExchHideFromAddressLists', 
            'msExchRecipientTypeDetails', 'msExchRemoteRecipientType'
        ])
        
        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404
            
        proxy_addresses = user['proxyAddresses'].values if 'proxyAddresses' in user else []
        
        primary = None
        aliases = []
        for addr in proxy_addresses:
            if addr.startswith('SMTP:'):
                primary = addr[5:]
            elif addr.startswith('smtp:'):
                aliases.append(addr[5:])
                
        mail = get_attr_value(user, 'mail') or ''
        hide_from_address_lists = user['msExchHideFromAddressLists'].value if 'msExchHideFromAddressLists' in user and user['msExchHideFromAddressLists'].value else False
        
        ms_exch_recipient_type_details = user['msExchRecipientTypeDetails'].value if 'msExchRecipientTypeDetails' in user else None
        ms_exch_remote_recipient_type = user['msExchRemoteRecipientType'].value if 'msExchRemoteRecipientType' in user else None
        
        return jsonify({
            'primary': primary,
            'aliases': aliases,
            'mail': mail,
            'hide_from_address_lists': hide_from_address_lists,
            'ms_exch_recipient_type_details': ms_exch_recipient_type_details,
            'ms_exch_remote_recipient_type': ms_exch_remote_recipient_type
        })
    except Exception as e:
        logging.error(f"Erro em api_user_exchange: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logging.error(f"Erro em api_user_exchange: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/convert_user_shared/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_manage_exchange')
def api_convert_user_shared(username):
    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, attributes=[
            'distinguishedName', 'userAccountControl', 'msExchRecipientTypeDetails', 'msExchRemoteRecipientType',
            'userPrincipalName', 'mail', 'targetAddress', 'proxyAddresses', 'mailNickname'
        ])
        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404
            
        upn = get_attr_value(user, 'userPrincipalName')
        if not upn:
            return jsonify({'error': 'O usuário não possui UPN (User Principal Name) definido. A conversão necessita do UPN como base.'}), 400
            
        uac = user.userAccountControl.value if 'userAccountControl' in user else 512
        new_uac = uac | 2 # Desabilita a conta localmente (ACCOUNTDISABLE)
        
        modifications = {
            'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(new_uac)])],
            'msExchRecipientTypeDetails': [(ldap3.MODIFY_REPLACE, [34359738368])],
            'msExchRemoteRecipientType': [(ldap3.MODIFY_REPLACE, [97])]
        }
        
        # Validar e ajustar e-mail principal
        current_mail = get_attr_value(user, 'mail')
        final_mail = current_mail if current_mail else upn
        if not current_mail:
            modifications['mail'] = [(ldap3.MODIFY_REPLACE, [final_mail])]
            
        # Validar e ajustar targetAddress
        current_target = get_attr_value(user, 'targetAddress')
        if not current_target or current_target != final_mail:
            modifications['targetAddress'] = [(ldap3.MODIFY_REPLACE, [final_mail])]
            
        # Validar e ajustar mailNickname (Alias no Exchange)
        current_nickname = get_attr_value(user, 'mailNickname')
        if not current_nickname:
            nickname = final_mail.split('@')[0] if '@' in final_mail else username
            modifications['mailNickname'] = [(ldap3.MODIFY_REPLACE, [nickname])]
            
        # Validar e ajustar proxyAddresses
        current_proxies = user['proxyAddresses'].values if 'proxyAddresses' in user else []
        has_primary = False
        for addr in current_proxies:
            if addr.startswith('SMTP:'):
                has_primary = True
                break
                
        if not has_primary:
            new_proxies = [str(p) for p in current_proxies]
            new_proxies.append('SMTP:' + final_mail)
            modifications['proxyAddresses'] = [(ldap3.MODIFY_REPLACE, new_proxies)]
            
        conn.modify(user.distinguishedName.value, modifications)
        if conn.result['description'] == 'success':
            logging.info(f"[EXCHANGE] Usuário '{username}' convertido para Caixa Compartilhada por '{session.get('user_display_name')}'.")
            save_to_history('exchange_change', username, f"Convertido para Caixa Compartilhada por '{session.get('user_display_name')}'")
            return jsonify({'success': True})
        else:
            return jsonify({'error': f"Falha no LDAP: {conn.result['message']}"}), 400
    except Exception as e:
        logging.error(f"Erro ao converter {username} para caixa compartilhada: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/update_user_hide_status/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_manage_exchange')
def api_update_user_hide_status(username):
    data = request.get_json()
    hide = data.get('hide', False)
    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, attributes=['distinguishedName'])
        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404
            
        conn.modify(user.distinguishedName.value, {'msExchHideFromAddressLists': [(ldap3.MODIFY_REPLACE, [hide])]})
        if conn.result['description'] == 'success':
            logging.info(f"[EXCHANGE] Status ocultação de '{username}' alterado para {hide} por '{session.get('user_display_name')}'.")
            save_to_history('exchange_change', username, f"Status ocultação alterado para {hide} por '{session.get('user_display_name')}'")
            return jsonify({'success': True})
        else:
            return jsonify({'error': f"Falha no LDAP: {conn.result['message']}"}), 400
    except Exception as e:
        logging.error(f"Erro ao atualizar status de ocultação para {username}: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/add_alias/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_manage_exchange')
def api_add_alias(username):
    data = request.get_json()
    new_alias = data.get('alias')
    if not new_alias or '@' not in new_alias:
        return jsonify({'error': 'Email inválido.'}), 400
        
    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, attributes=['proxyAddresses', 'distinguishedName'])
        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404
            
        proxy_addresses = user['proxyAddresses'].values if 'proxyAddresses' in user else []
            
        new_proxy = f"smtp:{new_alias.lower()}"
        
        if any(p.lower() == new_proxy.lower() for p in proxy_addresses):
            return jsonify({'error': 'Este alias já existe para o usuário.'}), 400
            
        proxy_addresses.append(new_proxy)
        
        conn.modify(user.distinguishedName.value, {'proxyAddresses': [(ldap3.MODIFY_REPLACE, proxy_addresses)]})
        if not conn.result['description'] == 'success':
            return jsonify({'error': conn.result['description']}), 500
            
        logging.info(f"[EXCHANGE] Alias '{new_alias}' adicionado para '{username}' por '{session.get('user_display_name')}'.")
        save_to_history('alteration', username, f"Alias '{new_alias}' adicionado para o usuário por '{session.get('user_display_name')}'")
        return jsonify({'message': 'Alias adicionado com sucesso.'})
    except Exception as e:
        logging.error(f"Erro em api_add_alias: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/remove_alias/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_manage_exchange')
def api_remove_alias(username):
    data = request.get_json()
    alias_to_remove = data.get('alias')
    if not alias_to_remove:
        return jsonify({'error': 'Alias não fornecido.'}), 400
        
    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, attributes=['proxyAddresses', 'distinguishedName'])
        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404
            
        proxy_addresses = user['proxyAddresses'].values if 'proxyAddresses' in user else []
            
        target_proxy = f"smtp:{alias_to_remove.lower()}"
        
        if f"SMTP:{alias_to_remove.lower()}" in [p.upper() if p.startswith('SMTP') else p for p in proxy_addresses]:
            return jsonify({'error': 'Não é possível remover o email principal.'}), 400

        new_proxies = [p for p in proxy_addresses if p.lower() != target_proxy.lower()]
        
        if len(new_proxies) == len(proxy_addresses):
            return jsonify({'error': 'Alias não encontrado.'}), 404
            
        conn.modify(user.distinguishedName.value, {'proxyAddresses': [(ldap3.MODIFY_REPLACE, new_proxies)]})
        if not conn.result['description'] == 'success':
            return jsonify({'error': conn.result['description']}), 500
            
        logging.info(f"[EXCHANGE] Alias '{alias_to_remove}' removido de '{username}' por '{session.get('user_display_name')}'.")
        save_to_history('alteration', username, f"Alias '{alias_to_remove}' removido por '{session.get('user_display_name')}'")
        return jsonify({'message': 'Alias removido com sucesso.'})
    except Exception as e:
        logging.error(f"Erro em api_remove_alias: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/set_primary_alias/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_manage_exchange')
def api_set_primary_alias(username):
    data = request.get_json()
    new_primary = data.get('alias')
    if not new_primary:
        return jsonify({'error': 'Alias não fornecido.'}), 400
        
    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, attributes=['proxyAddresses', 'distinguishedName', 'userPrincipalName'])
        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404
            
        proxy_addresses = user['proxyAddresses'].values if 'proxyAddresses' in user else []
            
        new_proxies = []
        found = False
        
        for p in proxy_addresses:
            if p.startswith('SMTP:'):
                new_proxies.append(f"smtp:{p[5:]}")
            elif p.lower() == f"smtp:{new_primary.lower()}":
                new_proxies.append(f"SMTP:{new_primary}")
                found = True
            else:
                new_proxies.append(p)
                
        if not found:
            new_proxies.append(f"SMTP:{new_primary}")
            
        changes = {
            'proxyAddresses': [(ldap3.MODIFY_REPLACE, new_proxies)],
            'mail': [(ldap3.MODIFY_REPLACE, [new_primary])],
            'targetAddress': [(ldap3.MODIFY_REPLACE, [new_primary])]
        }
        
        conn.modify(user.distinguishedName.value, changes)
        if not conn.result['description'] == 'success':
            return jsonify({'error': conn.result['description']}), 500
            
        logging.info(f"[EXCHANGE] Email principal de '{username}' alterado para '{new_primary}' por '{session.get('user_display_name')}'.")
        save_to_history('alteration', username, f"Email principal alterado para '{new_primary}' por '{session.get('user_display_name')}'")
        return jsonify({'message': 'Email principal alterado com sucesso.'})
    except Exception as e:
        logging.error(f"Erro em api_set_primary_alias: {e}")
        return jsonify({'error': str(e)}), 500


@users_bp.route('/api/convert_user_normal/<username>', methods=['POST'])
@require_auth
@require_api_permission(action='can_manage_exchange')
def api_convert_user_normal(username):
    try:
        conn = get_service_account_connection()
        user = get_user_by_samaccountname(conn, username, attributes=[
            'distinguishedName', 'userAccountControl', 'msExchRecipientTypeDetails', 'msExchRemoteRecipientType', 'targetAddress'
        ])
        if not user:
            return jsonify({'error': 'Usuário não encontrado.'}), 404
            
        uac = user.userAccountControl.value if 'userAccountControl' in user else 512
        new_uac = uac & ~2 # Habilita/Reativa a conta localmente (remove ACCOUNTDISABLE)
        
        modifications = {
            'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(new_uac)])],
            'msExchRecipientTypeDetails': [(ldap3.MODIFY_REPLACE, [])],   # Limpa o atributo
            'msExchRemoteRecipientType': [(ldap3.MODIFY_REPLACE, [])],   # Limpa o atributo
            'targetAddress': [(ldap3.MODIFY_REPLACE, [])]                # Limpa o targetAddress
        }
        
        conn.modify(user.distinguishedName.value, modifications)
        if conn.result['description'] == 'success':
            logging.info(f"[EXCHANGE] Usuário '{username}' convertido de volta para Caixa de Usuário / Normal por '{session.get('user_display_name')}'.")
            save_to_history('exchange_change', username, f"Convertido para Caixa de Usuário / Normal por '{session.get('user_display_name')}'")
            return jsonify({'success': True})
        else:
            return jsonify({'error': f"Falha no LDAP: {conn.result['message']}"}), 400
    except Exception as e:
        logging.error(f"Erro ao converter {username} para caixa normal: {e}")
        return jsonify({'error': str(e)}), 500
