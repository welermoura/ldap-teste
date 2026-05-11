from flask import Blueprint, render_template, session, redirect, url_for, current_app
from routes.utils import (
    require_auth, get_read_connection,
    get_attr_value
)
from common import load_config, get_user_by_samaccountname, get_service_account_connection
import os
import json
import logging
from flask import jsonify, send_from_directory
from ldap3 import SUBTREE

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@require_auth
def index():
    return redirect(url_for('main.dashboard'))

@main_bp.route('/dashboard')
@require_auth
def dashboard():
    from flask_wtf import FlaskForm
    from datetime import date
    form = FlaskForm()
    today_date = date.today().isoformat()
    return render_template('dashboard.html', form=form, today_date=today_date)

@main_bp.route('/profile')
@require_auth
def profile():
    username = session.get('ad_user')
    try:
        conn = get_read_connection()
        user = get_user_by_samaccountname(conn, username, attributes=['*', 'thumbnailPhoto'])
        return render_template('profile.html', user=user)
    except Exception as e:
        return redirect(url_for('main.dashboard'))

@main_bp.app_context_processor
def inject_appearance():
    config = load_config()
    appearance = {
        'bg_color': config.get('ORGANOGRAM_BG_COLOR', '#f8f9fa'),
        'bg_image': config.get('ORGANOGRAM_BG_IMAGE'),
        'logo': config.get('ORGANOGRAM_LOGO'),
        'favicon': config.get('ORGANOGRAM_FAVICON'),
        'subtitle': config.get('ORGANOGRAM_SUBTITLE', 'Portal de Administração')
    }
    return dict(appearance=appearance)

@main_bp.route('/organograma')
def organograma():
    """Rota pública para visualizar o organograma via React."""
    try:
        basedir = current_app.root_path
        manifest_path = os.path.join(basedir, 'frontend', 'dist', '.vite', 'manifest.json')
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        entry_point_key = 'organograma.html'
        if entry_point_key not in manifest:
            entry_point_key = 'src/organograma.jsx'
            if entry_point_key not in manifest:
                 return f"Erro de configuração. Chave '{entry_point_key}' não encontrada.", 500

        entry_point = manifest[entry_point_key]
        js_file = entry_point.get('file')
        css_files = entry_point.get('css', [])
        css_file = css_files[0] if css_files else None

        return render_template('organograma_react.html', js_file=js_file, css_file=css_file)
    except Exception as e:
        logging.error(f"Erro ao carregar o manifesto do Vite para Organograma: {e}", exc_info=True)
        return "Erro ao carregar a aplicação Organograma. Verifique os logs.", 500

@main_bp.route('/api/public/organogram_data')
def api_public_organogram_data():
    """API pública que retorna a estrutura hierárquica completa do AD."""
    try:
        conn = get_read_connection()
        config = load_config()
        search_base = config.get('AD_SEARCH_BASE')
        if not search_base:
            return jsonify({'error': 'AD_SEARCH_BASE não configurado.'}), 500

        # Busca todos os usuários que têm um Principal Name (indicativo de conta real)
        # Removido o filtro de !(userAccountControl:1.2.840.113556.1.4.803:=2) para mostrar usuários "em férias" (bloqueados)
        attributes = ['cn', 'displayName', 'sAMAccountName', 'title', 'department', 'manager', 'distinguishedName', 'l', 'thumbnailPhoto', 'userAccountControl', 'mail', 'telephoneNumber']
        search_filter = '(&(objectClass=user)(objectCategory=person)(userPrincipalName=*))'
        
        # Usa paged_search para lidar com mais de 1000 usuários
        entries = conn.extend.standard.paged_search(
            search_base=search_base,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=attributes,
            paged_size=1000,
            generator=True
        )

        all_entries = []
        parent_dns = set()
        for entry in entries:
            if entry['type'] != 'searchResEntry': continue
            attrs = entry['attributes']
            dn = entry['dn']
            manager_dn = attrs.get('manager')
            if manager_dn:
                parent_dns.add(manager_dn)
            
            all_entries.append({
                'dn': dn,
                'attrs': attrs,
                'manager_dn': manager_dn
            })

        nodes = []
        for entry in all_entries:
            dn = entry['dn']
            attrs = entry['attrs']
            manager_dn = entry['manager_dn']
            
            # Filtro: Mostrar apenas quem tem superior OU quem é superior de alguém (evita órfãos isolados)
            # A pedido do usuário: "mostrando apenas quem tem superior configurado"
            # Mas incluímos quem é superior para manter a raiz da árvore.
            if not manager_dn and dn not in parent_dns:
                continue

            uac = attrs.get('userAccountControl', 0)
            is_disabled = bool(uac & 2)

            nodes.append({
                'distinguishedName': dn,
                'name': attrs.get('displayName') or attrs.get('cn') or attrs.get('sAMAccountName'),
                'username': attrs.get('sAMAccountName'),
                'title': attrs.get('title') or 'Colaborador',
                'department': attrs.get('department') or '',
                'location': attrs.get('l') or '',
                'managerId': manager_dn,
                'mail': attrs.get('mail') or '',
                'telephoneNumber': attrs.get('telephoneNumber') or '',
                'hasPhoto': bool(attrs.get('thumbnailPhoto')),
                'isDisabled': is_disabled
            })
        
        # Constrói a hierarquia
        node_map = {n['distinguishedName']: n for n in nodes}
        tree = []
        
        for n in nodes:
            manager_dn = n.get('managerId')
            if manager_dn and manager_dn in node_map:
                parent = node_map[manager_dn]
                if 'children' not in parent:
                    parent['children'] = []
                parent['children'].append(n)
            else:
                # Se não tem gerente no mapa, é uma raiz da árvore exibida
                tree.append(n)
            
        return jsonify(tree)
    except Exception as e:
        logging.error(f"Erro ao gerar dados do organograma: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
