from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify, current_app
from routes.utils import get_password_reset_error_message
from common import (
    load_config, get_user_by_samaccountname, get_service_account_connection,
    get_ldap_connection, get_user_access_level
)
from forms.auth import LoginForm, ChangePasswordForm
from werkzeug.security import check_password_hash
import ldap3
from ldap3 import MODIFY_REPLACE
import os
import json
import logging

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'ad_user' in session:
        return redirect(url_for('main.dashboard'))
    
    config = load_config()
    form = LoginForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        # Lógica de Autenticação (LDAP ou Local)
        # Primeiro tenta local (admin do sistema)
        data_dir = os.path.join(current_app.root_path, 'data')
        users_file = os.path.join(data_dir, 'users.json')
        if os.path.exists(users_file):
            with open(users_file, 'r') as f:
                local_users = json.load(f)
            if username in local_users and check_password_hash(local_users[username], password):
                session['ad_user'] = username
                session['user_display_name'] = f"{username} (Admin Local)"
                session['is_admin'] = True
                session['access_level'] = 'full'
                return redirect(url_for('main.dashboard'))

        # Se não for local, tenta AD
        try:
            user_dn = f"{username}@{config['AD_DOMAIN']}"
            conn = get_ldap_connection(user=user_dn, password=password)
            
            # Busca grupos e nome de exibição
            user_entry = get_user_by_samaccountname(conn, username, ['displayName', 'memberOf'])
            if not user_entry:
                flash('Usuário não encontrado no AD.', 'error')
                return redirect(url_for('auth.login'))

            user_groups = []
            if 'memberOf' in user_entry:
                for group_dn in user_entry.memberOf:
                    try:
                        # Extrai o nome do grupo do DN (ex: CN=Group Name,OU=...)
                        group_name = group_dn.split(',')[0].split('=')[1]
                        user_groups.append(group_name)
                    except (IndexError, AttributeError):
                        continue
            access_level = get_user_access_level(user_groups)

            if access_level == 'none':
                flash('Você não tem permissão para acessar o sistema.', 'error')
                return redirect(url_for('auth.login'))

            display_name = user_entry.displayName.value if user_entry and 'displayName' in user_entry else username
            
            session['ad_user'] = username
            session['user_display_name'] = display_name
            session['user_groups'] = user_groups
            session['access_level'] = access_level
            session['ad_password'] = password
            
            logging.info(f"Usuário '{username}' logado com sucesso (Nível: {access_level}).")
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            flash('Credenciais inválidas ou erro de conexão com o AD.', 'error')
            logging.error(f"Erro de login para '{username}': {e}")

    return render_template('login.html', form=form)

@auth_bp.route('/logout')
def logout():
    user = session.get('ad_user')
    session.clear()
    flash('Você saiu do sistema.', 'info')
    if user:
        logging.info(f"Usuário '{user}' saiu do sistema.")
    return redirect(url_for('auth.login'))

@auth_bp.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'ad_user' not in session:
        return redirect(url_for('auth.login'))
        
    form = ChangePasswordForm()
    if form.validate_on_submit():
        username = session['ad_user']
        current_password = form.current_password.data
        new_password = form.new_password.data
        
        try:
            config = load_config()
            user_dn = f"{username}@{config['AD_DOMAIN']}"
            
            # Autentica com a senha atual para validar
            conn = get_ldap_connection(user=user_dn, password=current_password)
            
            # Muda a senha
            user_entry = get_user_by_samaccountname(conn, username, ['distinguishedName'])
            password_value = f'"{new_password}"'.encode('utf-16-le')
            conn.modify(user_entry.distinguishedName.value, {'unicodePwd': [(MODIFY_REPLACE, [password_value])]})
            
            if conn.result['description'] == 'success':
                # Atualiza a senha na sessão se necessário
                if 'ad_password' in session:
                    session['ad_password'] = new_password
                flash('Senha alterada com sucesso!', 'success')
                logging.info(f"Usuário '{username}' alterou sua própria senha.")
                return redirect(url_for('main.dashboard'))
            else:
                error_msg = get_password_reset_error_message(conn.result['message'])
                flash(f"Erro ao alterar senha: {error_msg}", 'error')
        except Exception as e:
            flash(f"Erro de autenticação ou conexão: {e}", 'error')
            
    return render_template('change_password.html', form=form)

# SSO placeholder
@auth_bp.route('/sso/login')
def sso_login():
    config = load_config()
    if not config.get('SSO_ENABLED'):
        return redirect(url_for('auth.login'))
    # Implementação futura do SSO (ex: Kerberos/Remote-User)
    return "SSO não configurado totalmente.", 501


