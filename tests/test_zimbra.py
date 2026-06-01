import pytest
from unittest.mock import MagicMock
from common import load_config, save_config
from routes.zimbra import load_zimbra_mappings, save_zimbra_mappings

def test_zimbra_config_page(authenticated_client, mocker):
    # Mock load_config to return some basic config
    mocker.patch('routes.zimbra.load_config', return_value={
        'ZIMBRA_API_URL': 'http://localhost:5000/mock/zimbra/soap',
        'ZIMBRA_ADMIN_USER': 'admin@comolatti.com.br',
        'ZIMBRA_ADMIN_PASSWORD': 'adminpassword',
        'ZIMBRA_ENABLED': True
    })
    
    # Mock ZimbraSOAPClient to return domains
    mock_client = mocker.patch('routes.zimbra.ZimbraSOAPClient')
    mock_client.return_value.get_domains.return_value = [{'name': 'comolatti.com.br', 'id': 'd1'}]
    
    response = authenticated_client.get('/admin/zimbra_config')
    assert response.status_code == 200
    assert b'comolatti.com.br' in response.data

def test_api_save_config(authenticated_client, mocker):
    mock_save = mocker.patch('routes.zimbra.save_config')
    response = authenticated_client.post('/api/zimbra/save_config', json={
        'zimbra_url': 'http://localhost:5000/mock/zimbra/soap',
        'zimbra_user': 'admin@comolatti.com.br',
        'zimbra_password': 'newpassword',
        'zimbra_enabled': True
    })
    assert response.status_code == 200
    assert response.json['success'] is True
    mock_save.assert_called_once()

def test_api_test_connection(authenticated_client, mocker):
    mock_client = mocker.patch('routes.zimbra.ZimbraSOAPClient')
    mock_client.return_value.get_domains.return_value = [{'name': 'comolatti.com.br', 'id': 'd1'}]
    
    response = authenticated_client.post('/api/zimbra/test_connection', json={
        'zimbra_url': 'http://localhost:5000/mock/zimbra/soap',
        'zimbra_user': 'admin@comolatti.com.br',
        'zimbra_password': 'password'
    })
    assert response.status_code == 200
    assert response.json['success'] is True
    assert len(response.json['domains']) == 1

def test_api_save_mapping(authenticated_client, mocker):
    # Mock AD calls
    mocker.patch('routes.zimbra.get_service_account_connection')
    mocker.patch('routes.zimbra.get_group_by_name', return_value=MagicMock())
    mocker.patch('routes.zimbra.save_zimbra_mappings')
    
    response = authenticated_client.post('/api/zimbra/save_mapping', json={
        'ad_group_name': 'Diretoria',
        'zimbra_dl_email': 'diretoria@comolatti.com.br'
    })
    assert response.status_code == 200
    assert response.json['success'] is True

def test_api_sync_group(authenticated_client, mocker):
    # Mock config and mapping
    mocker.patch('routes.zimbra.load_config', return_value={
        'ZIMBRA_API_URL': 'http://localhost:5000/mock/zimbra/soap',
        'ZIMBRA_ADMIN_USER': 'admin@comolatti.com.br',
        'ZIMBRA_ADMIN_PASSWORD': 'adminpassword',
        'ZIMBRA_ENABLED': True
    })
    mocker.patch('routes.zimbra.load_zimbra_mappings', return_value=[
        {'ad_group_name': 'Diretoria', 'zimbra_dl_email': 'diretoria@comolatti.com.br'}
    ])
    
    # Mock AD calls
    mocker.patch('routes.zimbra.get_service_account_connection')
    
    mock_group = MagicMock()
    mock_group.__contains__.side_effect = lambda x: x == 'member'
    mock_group.member.values = ['cn=admin,ou=users,dc=comolatti,dc=lan']
    mocker.patch('routes.zimbra.get_group_by_name', return_value=mock_group)

    
    mock_user = MagicMock()
    # Mocking get_attr_value
    mocker.patch('routes.zimbra.get_attr_value', side_effect=lambda entry, attr: 'admin@comolatti.lan' if attr == 'mail' else None)
    mocker.patch('routes.utils.get_user_by_dn', return_value=mock_user)
    
    # Mock SOAP Client
    mock_client = mocker.patch('routes.zimbra.ZimbraSOAPClient')
    mock_client.return_value.get_dl_members.return_value = {
        'id': 'dl-123',
        'email': 'diretoria@comolatti.com.br',
        'members': ['old_member@comolatti.lan'] # will be removed
    }
    
    response = authenticated_client.post('/api/zimbra/sync_group', json={
        'ad_group_name': 'Diretoria'
    })
    
    assert response.status_code == 200
    assert response.json['success'] is True
    assert response.json['stats']['added'] == 1
    assert response.json['stats']['removed'] == 1

def test_api_sync_group_auto_create(authenticated_client, mocker):
    # Mock config e mapping
    mocker.patch('routes.zimbra.load_config', return_value={
        'ZIMBRA_API_URL': 'http://localhost:5000/mock/zimbra/soap',
        'ZIMBRA_ADMIN_USER': 'admin@comolatti.com.br',
        'ZIMBRA_ADMIN_PASSWORD': 'adminpassword',
        'ZIMBRA_ENABLED': True
    })
    mocker.patch('routes.zimbra.load_zimbra_mappings', return_value=[
        {'ad_group_name': 'Diretoria', 'zimbra_dl_email': 'diretoria@comolatti.com.br'}
    ])
    
    # Mock AD calls
    mocker.patch('routes.zimbra.get_service_account_connection')
    
    mock_group = MagicMock()
    mock_group.__contains__.side_effect = lambda x: x == 'member'
    mock_group.member.values = ['cn=admin,ou=users,dc=comolatti,dc=lan']
    mocker.patch('routes.zimbra.get_group_by_name', return_value=mock_group)
    
    mock_user = MagicMock()
    mocker.patch('routes.zimbra.get_attr_value', side_effect=lambda entry, attr: 'admin@comolatti.lan' if attr == 'mail' else None)
    mocker.patch('routes.utils.get_user_by_dn', return_value=mock_user)
    
    # Mock SOAP Client para levantar NO_SUCH_DISTRIBUTION_LIST na primeira chamada e funcionar na segunda
    mock_client = mocker.patch('routes.zimbra.ZimbraSOAPClient')
    mock_client.return_value.get_dl_members.side_effect = [
        Exception("[account.NO_SUCH_DISTRIBUTION_LIST] no such distribution list"),
        {
            'id': 'dl-123',
            'email': 'diretoria@comolatti.com.br',
            'members': []
        }
    ]
    
    response = authenticated_client.post('/api/zimbra/sync_group', json={
        'ad_group_name': 'Diretoria'
    })
    
    assert response.status_code == 200
    assert response.json['success'] is True
    mock_client.return_value.create_dl.assert_called_once_with('diretoria@comolatti.com.br')
    assert response.json['stats']['added'] == 1
