import os
import logging
from flask import Flask, render_template, session
from datetime import datetime
from routes.utils import limiter
from routes.auth import auth_bp
from routes.main import main_bp
from routes.users import users_bp
from routes.groups import groups_bp
from routes.admin import admin_bp
from common import load_config, get_flask_secret_key

# ==============================================================================
# Configuração de Logs
# ==============================================================================
basedir = os.path.abspath(os.path.dirname(__file__))
logs_dir = os.path.join(basedir, 'logs')
os.makedirs(logs_dir, exist_ok=True)

log_path = os.path.join(logs_dir, 'ad_creator.log')
logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

# ==============================================================================
# Inicialização do Aplicativo Flask
# ==============================================================================
app = Flask(__name__)
app.secret_key = get_flask_secret_key()

from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)

# Configuração do Limiter
limiter.init_app(app)

# ==============================================================================
# Registro de Blueprints
# ==============================================================================
app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(users_bp)
app.register_blueprint(groups_bp)
app.register_blueprint(admin_bp)

# ==============================================================================
# Processador de Contexto Global (Branding e Ano)
# ==============================================================================
@app.context_processor
def inject_global_vars():
    from routes.utils import check_permission, is_authenticated, get_attr_value, get_user_status
    config = load_config()
    return {
        'appearance': {
            'bg_color': config.get('ORGANOGRAM_BG_COLOR', '#f8f9fa'),
            'bg_image': config.get('ORGANOGRAM_BG_IMAGE'),
            'logo': config.get('ORGANOGRAM_LOGO'),
            'favicon': config.get('ORGANOGRAM_FAVICON'),
            'subtitle': config.get('ORGANOGRAM_SUBTITLE', 'Portal de Administração')
        },
        'year': datetime.now().year,
        'check_permission': check_permission,
        'is_authenticated': is_authenticated,
        'get_attr_value': get_attr_value,
        'get_user_status': get_user_status
    }

# ==============================================================================
# Filtros Jinja customizados (se necessário)
# ==============================================================================
@app.template_filter('datetime')
def format_datetime(value, format="%d/%m/%Y %H:%M"):
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            from datetime import datetime
            # Tenta converter de ISO format (comum em JSON)
            # Remove o 'Z' se presente e substitui por offset UTC para fromisoformat
            dt_str = value.replace('Z', '+00:00')
            value = datetime.fromisoformat(dt_str)
        except (ValueError, TypeError):
            return value # Retorna a string original se não conseguir converter
    return value.strftime(format)

# ==============================================================================
# Limpeza de Conexões LDAP
# ==============================================================================
@app.teardown_appcontext
def close_connections(exception):
    from flask import g
    read_conn = g.pop('read_conn', None)
    if read_conn:
        try:
            read_conn.unbind()
        except:
            pass
            
    service_conn = g.pop('service_conn', None)
    if service_conn:
        try:
            service_conn.unbind()
        except:
            pass

# ==============================================================================
# Execução
# ==============================================================================
if __name__ == '__main__':
    # Em produção, deve-se usar um servidor WSGI como Gunicorn ou Waitress
    app.run(debug=True, host='0.0.0.0', port=5000)