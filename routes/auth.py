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
        
        # 1. Carrega a lista de administradores (Locais e AD)
        from common import load_admin_users
        admins = load_admin_users()
        
        # 2. Busca o usuário na lista de admins (case-insensitive)
        admin_key = next((k for k in admins if k.lower() == username.lower()), None)
        
        # 3. Tenta autenticação como Administrador Local
        if admin_key and admins[admin_key] != "AD_AUTH":
            if check_password_hash(admins[admin_key], password):
                session['ad_user'] = admin_key
                session['user_display_name'] = f"{admin_key} (Admin Local)"
                session['is_admin'] = True
                session['access_level'] = 'full'
                return redirect(url_for('main.dashboard'))

        # 4. Tenta autenticação via Active Directory (Operadores ou Admins do AD)
        try:
            # Se for um Admin do AD, ele deve estar na lista 'admins' com "AD_AUTH"
            is_ad_admin = admin_key and admins[admin_key] == "AD_AUTH"
            
            # Conexão LDAP
            config = load_config()
            user_dn = f"{username}@{config.get('AD_DOMAIN')}"
            conn = get_ldap_connection(user=user_dn, password=password)
            
            # Login bem-sucedido no AD!
            session['ad_user'] = username
            session['is_admin'] = is_ad_admin # Define se terá acesso ao menu admin
            
            # Busca detalhes do usuário no AD
            user_entry = get_user_by_samaccountname(conn, username, ['displayName', 'memberOf'])
            if user_entry:
                session['user_display_name'] = user_entry.displayName.value if 'displayName' in user_entry else username
                
                # Se for admin, acesso total. Se não, verifica grupos.
                if is_ad_admin:
                    session['access_level'] = 'full'
                else:
                    user_groups = []
                    if 'memberOf' in user_entry:
                        for group_dn in user_entry.memberOf:
                            try:
                                group_name = group_dn.split(',')[0].split('=')[1]
                                user_groups.append(group_name)
                            except: continue
                    session['user_groups'] = user_groups
                    session['access_level'] = get_user_access_level(user_groups)
            
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            logging.warning(f"Falha de login para {username}: {e}")
            flash('Usuário ou senha incorretos.', 'error')
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


