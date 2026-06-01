import pytest

def test_login_page_renders(client):
    response = client.get('/login')
    assert response.status_code == 200
    assert b'Login' in response.data

def test_login_success(client, mocker_ldap, mocker):
    # Mocka a verificação de acesso
    mocker.patch('routes.auth.get_user_access_level', return_value='full')
    mocker.patch('routes.auth.load_config', return_value={'AD_DOMAIN': 'comolatti.lan'})
    
    # Mocka get_user_by_samaccountname para simular dados retornados do AD
    mock_get_user = mocker.patch('routes.auth.get_user_by_samaccountname')
    mock_user = mocker.MagicMock()
    mock_user.displayName.value = "Usuário Teste"
    mock_get_user.return_value = mock_user


    response = client.post('/login', data={
        'username': 'usuario.teste',
        'password': 'password123'
    }, follow_redirects=True)
    
    # Se o login der certo, deve ir pro dashboard ou manage_users
    assert response.status_code == 200

def test_protected_route_requires_login(client):
    response = client.get('/manage_users', follow_redirects=True)
    # Se não estiver logado, deve redirecionar para o login
    assert b'Fa\xc3\xa7a login para acessar esta p\xc3\xa1gina.' in response.data or b'Login' in response.data

def test_authenticated_user_can_access_dashboard(authenticated_client):
    response = authenticated_client.get('/dashboard')
    assert response.status_code == 200
    assert b'Usu\xc3\xa1rio Teste' in response.data or b'Gest\xc3\xa3o AD' in response.data
