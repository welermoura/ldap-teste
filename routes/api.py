from flask import Blueprint, jsonify, request, session, Response
from routes.utils import require_auth, require_api_permission, check_permission, require_api_key
from common import (
    get_ldap_connection, get_service_account_connection,
    get_user_by_samaccountname, get_attr_value,
    load_config
)
import logging

# Cria o blueprint para a API v1
api_bp = Blueprint('api', __name__, url_prefix='/api/v1')

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Endpoint simples para verificar se a API está no ar."""
    return jsonify({"status": "ok", "version": "1.0"})

# Exemplo de rota movida:
@api_bp.route('/action_permissions', methods=['GET'])
@require_auth
def api_action_permissions():
    """Retorna as permissões de ações para o usuário logado."""
    actions = ['can_create', 'can_disable', 'can_reset_password', 'can_edit', 'can_manage_groups', 'can_delete_user', 'can_move_user', 'can_edit_users']
    user_permissions = {action: check_permission(action=action) for action in actions}
    user_permissions['can_manage_hierarchy'] = user_permissions['can_edit_users']
    return jsonify(user_permissions)

# Mais endpoints RESTful viriam aqui (ex: GET /users/<username>, POST /users, PUT /users/<username>)

@api_bp.route('/integration/ping', methods=['GET'])
@require_api_key
def api_integration_ping():
    """
    Endpoint dedicado para testar a conectividade da chave de API.
    Retorna 200 OK se o token for válido, e ecoa as permissões da chave.
    """
    # A chave validada pode ser recuperada se adicionada ao request ou lendo novamente
    return jsonify({
        "status": "success", 
        "message": "Autenticado com sucesso via API Key",
        "system": "GEstão AD REST API"
    })

@api_bp.route('/mock_hr', methods=['GET'])
def api_mock_hr():
    """
    Simulador da API da ADP (Recursos Humanos).
    Retorna uma lista fictícia de colaboradores e seus períodos de férias.
    """
    auth_header = request.headers.get('Authorization')
    if not auth_header or auth_header != "Bearer hr_mock_token_123":
        return jsonify({"error": "Unauthorized"}), 401

    import datetime
    hoje = datetime.date.today()
    daqui_uma_semana = (hoje + datetime.timedelta(days=7)).isoformat()
    daqui_um_mes = (hoje + datetime.timedelta(days=37)).isoformat()

    ferias_adp = [
        {
            "matricula": "99001",
            "first_name": "Carlos",
            "last_name": "Mendes",
            "vacation_start": daqui_uma_semana,
            "vacation_end": daqui_um_mes
        },
        {
            "matricula": "99002",
            "first_name": "Ana",
            "last_name": "Souza",
            "vacation_start": hoje.isoformat(),
            "vacation_end": daqui_uma_semana
        }
    ]
    return jsonify(ferias_adp)
