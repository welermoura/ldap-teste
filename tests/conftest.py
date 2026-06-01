import pytest
from app import app as flask_app
from flask import session

@pytest.fixture
def app():
    # Cria uma instância da aplicação para os testes com configuração de teste
    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test_secret_key"
    })
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def mocker_ldap(mocker):
    # Um mock simples para a função get_ldap_connection
    # Isso impede que o teste tente bater num AD de verdade
    mock_conn = mocker.patch('common.get_ldap_connection')
    mock_conn.return_value = mocker.MagicMock(result={'description': 'success'})

    return mock_conn

@pytest.fixture
def authenticated_client(client, mocker):
    with client.session_transaction() as sess:
        sess['ad_user'] = 'usuario.teste'
        sess['user_display_name'] = 'Usuário Teste'
        sess['is_admin'] = True
        sess['permissions'] = {
            'can_create': True,
            'can_disable': True,
            'can_edit': True,
            'can_manage_groups': True
        }
    return client

