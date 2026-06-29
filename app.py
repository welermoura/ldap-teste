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
from routes.zimbra import zimbra_bp
from common import load_config, get_flask_secret_key
from models import db, seed_database_from_json

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
    datefmt='%d-%m-%Y %H:%M:%S',
    encoding='utf-8'
)

# Filtro para ocultar o aviso de servidor de desenvolvimento (development server warning) do Werkzeug
class NoDevServerWarningFilter(logging.Filter):
    def filter(self, record):
        return "development server" not in record.getMessage()

logging.getLogger('werkzeug').addFilter(NoDevServerWarningFilter())

# ==============================================================================
# Inicialização do Aplicativo Flask
# ==============================================================================
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.secret_key = get_flask_secret_key()

# Permite que o Flask reconheça requisições HTTPS encaminhadas por um Proxy Reverso
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Configuração de cookies compatível com HTTP e HTTPS (seguro se configurado em SESSION_COOKIE_SECURE)
config = load_config()
use_secure_cookies = str(config.get('SESSION_COOKIE_SECURE', os.environ.get('SESSION_COOKIE_SECURE', 'False'))).lower() == 'true'
app.config['SESSION_COOKIE_SECURE'] = use_secure_cookies
app.config['REMEMBER_COOKIE_SECURE'] = use_secure_cookies
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# ==============================================================================
# Inicialização do Banco de Dados (SQL Server / Fallback JSON)
# ==============================================================================
from common import get_sql_server_uri
active_db_uri = get_sql_server_uri() or 'sqlite:///:memory:'

app.config['SQLALCHEMY_DATABASE_URI'] = active_db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 1800,
    'pool_pre_ping': True
}
db.init_app(app)

with app.app_context():
    try:
        if active_db_uri != 'sqlite:///:memory:':
            db.create_all()
            seed_database_from_json(db)
            logging.info("[DB] Banco de dados SQL Server conectado e tabelas sincronizadas na inicialização.")
        else:
            logging.info("[DB] Banco de dados em modo Fallback JSON (SQLite em memória registrado).")
    except Exception as e:
        logging.error(f"[DB] Erro ao sincronizar tabelas com o SQL Server na inicialização: {e}")

from flask_wtf.csrf import CSRFProtect, CSRFError
app.config['WTF_CSRF_ENABLED'] = True
csrf = CSRFProtect(app)

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    logging.warning(f"CSRF Token Expirado ou Inválido: {e.description}")
    return render_template('csrf_error.html', reason=e.description), 400

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
app.register_blueprint(zimbra_bp)
csrf.exempt(zimbra_bp)

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
        'get_user_status': get_user_status,
        'zimbra_enabled': config.get('ZIMBRA_ENABLED', False)
    }

# ==============================================================================
# Filtros Jinja customizados (se necessário)
# ==============================================================================
@app.template_filter('datetime')
def format_datetime(value, format="%d-%m-%Y %H:%M"):
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
    app.run(debug=False, host='0.0.0.0', port=5000)