import pytest
from unittest.mock import MagicMock
from common import load_config, save_config
from routes.zimbra import load_zimbra_mappings, save_zimbra_mappings

@pytest.fixture(autouse=True)
def app_context(app):
    with app.app_context():
        yield

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
    
    # Mock AD connection and group lookup
    mocker.patch('routes.zimbra.get_service_account_connection')
    mock_group = MagicMock()
    mock_group.distinguishedName.value = 'CN=Diretoria,OU=Groups,DC=comolatti,DC=lan'
    mocker.patch('routes.zimbra.get_group_by_name', return_value=mock_group)

    # Mock get_group_members_identities directly
    mocker.patch('routes.zimbra.get_group_members_identities', return_value=[
        {
            'dn': 'CN=admin,OU=Users,DC=comolatti,DC=lan',
            'primary_email': 'admin@comolatti.lan',
            'all_emails': {'admin@comolatti.lan'}
        }
    ])
    
    # Mock SOAP Client
    mock_client = mocker.patch('routes.zimbra.ZimbraSOAPClient')
    mock_client.return_value.get_dl_members.return_value = {
        'id': 'dl-123',
        'email': 'diretoria@comolatti.com.br',
        'members': ['old_member@comolatti.lan'] # will be removed
    }
    mock_client.return_value.get_account_info.return_value = {
        'email': 'old_member@comolatti.lan',
        'aliases': [],
        'status': 'active'
    }
    
    response = authenticated_client.post('/api/zimbra/sync_group', json={
        'ad_group_name': 'Diretoria'
    })
    
    assert response.status_code == 200
    assert response.json['success'] is True
    assert response.json['stats']['added'] == 1
    assert response.json['stats']['removed'] == 1


def test_api_sync_group_delete_when_zimbra_dl_not_found(authenticated_client, mocker):
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
    
    # Mock AD connection and group lookup (AD group exists)
    mocker.patch('routes.zimbra.get_service_account_connection')
    mock_group = MagicMock()
    mock_group.distinguishedName.value = 'CN=Diretoria,OU=Groups,DC=comolatti,DC=lan'
    mocker.patch('routes.zimbra.get_group_by_name', return_value=mock_group)

    # Mock get_group_members_identities
    mocker.patch('routes.zimbra.get_group_members_identities', return_value=[])
    
    # Mock Zimbra SOAP (DL doesn't exist)
    mock_client = mocker.patch('routes.zimbra.ZimbraSOAPClient')
    mock_client.return_value.get_dl_members.side_effect = Exception("[account.NO_SUCH_DISTRIBUTION_LIST] no such distribution list")
    
    # Mock Banco de dados
    mock_db_m = MagicMock()
    mock_query = mocker.patch('models.ZimbraMapping.query')
    mock_query.filter_by.return_value.first.return_value = mock_db_m
    mock_db = mocker.patch('models.db')
    mocker.patch('routes.zimbra.save_to_history')
    
    response = authenticated_client.post('/api/zimbra/sync_group', json={
        'ad_group_name': 'Diretoria'
    })
    
    assert response.status_code == 404
    assert 'não existe mais' in response.json['error']
    assert 'Zimbra' in response.json['error']
    mock_db.session.delete.assert_called_once_with(mock_db_m)
    mock_db.session.commit.assert_called_once()

def test_api_sync_group_delete_when_ad_group_not_found(authenticated_client, mocker):
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
    
    # Mock AD group missing
    mocker.patch('routes.zimbra.get_service_account_connection')
    mocker.patch('routes.zimbra.get_group_by_name', return_value=None)
    
    # Mock Zimbra SOAP (DL exists)
    mock_client = mocker.patch('routes.zimbra.ZimbraSOAPClient')
    mock_client.return_value.get_dl_members.return_value = {'id': 'dl-123', 'email': 'diretoria@comolatti.com.br', 'members': []}
    
    # Mock Banco de dados
    mock_db_m = MagicMock()
    mock_query = mocker.patch('models.ZimbraMapping.query')
    mock_query.filter_by.return_value.first.return_value = mock_db_m
    mock_db = mocker.patch('models.db')
    mocker.patch('routes.zimbra.save_to_history')
    
    response = authenticated_client.post('/api/zimbra/sync_group', json={
        'ad_group_name': 'Diretoria'
    })
    
    assert response.status_code == 404
    assert 'foi removido' in response.json['error']
    assert 'grupo AD' in response.json['error']
    mock_db.session.delete.assert_called_once_with(mock_db_m)
    mock_db.session.commit.assert_called_once()

def test_api_sync_group_delete_when_both_not_found(authenticated_client, mocker):
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
    
    # Mock AD group missing
    mocker.patch('routes.zimbra.get_service_account_connection')
    mocker.patch('routes.zimbra.get_group_by_name', return_value=None)
    
    # Mock Zimbra SOAP (DL missing too)
    mock_client = mocker.patch('routes.zimbra.ZimbraSOAPClient')
    mock_client.return_value.get_dl_members.side_effect = Exception("[account.NO_SUCH_DISTRIBUTION_LIST] no such distribution list")
    
    # Mock Banco de dados
    mock_db_m = MagicMock()
    mock_query = mocker.patch('models.ZimbraMapping.query')
    mock_query.filter_by.return_value.first.return_value = mock_db_m
    mock_db = mocker.patch('models.db')
    mocker.patch('routes.zimbra.save_to_history')
    
    response = authenticated_client.post('/api/zimbra/sync_group', json={
        'ad_group_name': 'Diretoria'
    })
    
    assert response.status_code == 404
    assert 'foi removido' in response.json['error']
    mock_db.session.delete.assert_called_once_with(mock_db_m)
    mock_db.session.commit.assert_called_once()

def test_add_dl_alias(mocker):
    from routes.zimbra_api import ZimbraSOAPClient
    client = ZimbraSOAPClient('http://localhost:5000/mock/zimbra/soap', 'admin@comolatti.com.br', 'adminpassword')
    mocker.patch.object(client, 'authenticate')
    mocker.patch.object(client, 'get_dl_members', return_value={'id': 'dl-id-123'})
    mock_send = mocker.patch.object(client, '_send_soap_request')
    
    res = client.add_dl_alias('ti@comolatti.com.br', 'ti-alias@comolatti.com.br')
    assert res is True
    mock_send.assert_called_once()
    assert 'AddDistributionListAliasRequest' in mock_send.call_args[0][0]
