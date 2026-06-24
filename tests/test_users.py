import pytest
import json
from unittest.mock import MagicMock, call
from flask import session
from common import get_attr_value

class MockLDAPUser:
    def __init__(self, attributes):
        self._attributes = attributes
        for k, v in attributes.items():
            mock_attr = MagicMock(value=v)
            if isinstance(v, list):
                mock_attr.values = v
            else:
                mock_attr.values = [v]
            setattr(self, k, mock_attr)
            
    def __contains__(self, item):
        return item in self._attributes
        
    def __getitem__(self, item):
        return getattr(self, item)

def get_form_data(user, overrides=None):
    upn_val = get_attr_value(user, 'userPrincipalName') or 'john.doe@domain.com'
    parts = upn_val.split('@', 1)
    upn_prefix = parts[0] if parts else 'john.doe'
    upn_suffix = '@' + parts[1] if len(parts) == 2 else '@domain.com'

    data = {
        'first_name': get_attr_value(user, 'givenName'),
        'last_name': get_attr_value(user, 'sn'),
        'initials': get_attr_value(user, 'initials'),
        'display_name': get_attr_value(user, 'displayName'),
        'cn': get_attr_value(user, 'cn'),
        'description': get_attr_value(user, 'description'),
        'office': get_attr_value(user, 'physicalDeliveryOfficeName'),
        'email': get_attr_value(user, 'mail'),
        'upn_prefix': upn_prefix,
        'upn_suffix': upn_suffix,
        'web_page': get_attr_value(user, 'wWWHomePage'),
        'street': get_attr_value(user, 'streetAddress'),
        'post_office_box': get_attr_value(user, 'postOfficeBox'),
        'city': get_attr_value(user, 'l'),
        'state': get_attr_value(user, 'st'),
        'zip_code': get_attr_value(user, 'postalCode'),
        'home_phone': get_attr_value(user, 'homePhone'),
        'pager': get_attr_value(user, 'pager'),
        'mobile': get_attr_value(user, 'mobile'),
        'fax': get_attr_value(user, 'facsimileTelephoneNumber'),
        'title': get_attr_value(user, 'title'),
        'department': get_attr_value(user, 'department'),
        'company': get_attr_value(user, 'company'),
        'manager': '',
        'matricula': get_attr_value(user, 'extensionAttribute4'),
    }
    if overrides:
        data.update(overrides)
    return data

@pytest.fixture(autouse=True)
def app_context(app):
    with app.app_context():
        yield

def test_edit_user_render(authenticated_client, mocker):
    # Mock AD functions
    mock_conn = MagicMock()
    mocker.patch('routes.users.get_read_connection', return_value=mock_conn)
    
    mock_user = MockLDAPUser({
        'sAMAccountName': 'john.doe',
        'displayName': 'John Doe',
        'cn': 'John Doe Original',
        'givenName': 'John',
        'sn': 'Doe',
        'initials': 'JD',
        'distinguishedName': 'CN=John Doe Original,OU=Users,DC=domain,DC=com',
        'description': 'Test description',
        'mail': 'john.doe@domain.com',
        'userPrincipalName': 'john.doe@domain.com',
        'manager': 'CN=Boss,OU=Users,DC=domain,DC=com'
    })
    mocker.patch('routes.users.get_user_by_samaccountname', return_value=mock_user)
    mocker.patch('routes.users.get_user_by_dn', return_value=None)
    mocker.patch('routes.users.check_permission', return_value=True)
    mocker.patch('routes.users.load_config', return_value={})

    response = authenticated_client.get('/edit_user/john.doe')
    assert response.status_code == 200
    # Verify both display_name and cn fields are rendered in the HTML
    assert b'Nome de Exibi\xc3\xa7\xc3\xa3o' in response.data
    assert b'Nome Completo' in response.data

def test_edit_user_cn_changed(authenticated_client, mocker):
    # Mock connections
    read_conn = MagicMock()
    service_conn = MagicMock()
    service_conn.result = {'description': 'success'}
    mocker.patch('routes.users.get_read_connection', return_value=read_conn)
    mocker.patch('routes.users.get_service_account_connection', return_value=service_conn)
    
    mock_user = MockLDAPUser({
        'sAMAccountName': 'john.doe',
        'displayName': 'John Doe',
        'cn': 'John Doe Original',
        'givenName': 'John',
        'sn': 'Doe',
        'initials': 'JD',
        'distinguishedName': 'CN=John Doe Original,OU=Users,DC=domain,DC=com',
        'description': 'Test description',
        'mail': 'john.doe@domain.com',
        'userPrincipalName': 'john.doe@domain.com',
        'manager': ''
    })
    mocker.patch('routes.users.get_user_by_samaccountname', return_value=mock_user)
    mocker.patch('routes.users.check_permission', return_value=True)
    mocker.patch('routes.users.load_config', return_value={})
    mocker.patch('routes.users.save_to_history')

    # Send POST with new CN but same Display Name
    post_data = get_form_data(mock_user, {'cn': 'John Doe New CN'})
    response = authenticated_client.post('/edit_user/john.doe', data=post_data, follow_redirects=True)
    
    assert response.status_code == 200
    
    # modify should NOT be called since no other attributes changed
    assert not service_conn.modify.called
    
    # modify_dn should be called to rename the user object in AD
    service_conn.modify_dn.assert_called_once_with(
        'CN=John Doe Original,OU=Users,DC=domain,DC=com',
        'CN=John Doe New CN'
    )

def test_edit_user_display_name_changed_only(authenticated_client, mocker):
    read_conn = MagicMock()
    service_conn = MagicMock()
    service_conn.result = {'description': 'success'}
    mocker.patch('routes.users.get_read_connection', return_value=read_conn)
    mocker.patch('routes.users.get_service_account_connection', return_value=service_conn)
    
    mock_user = MockLDAPUser({
        'sAMAccountName': 'john.doe',
        'displayName': 'John Doe Original',
        'cn': 'John Doe',
        'givenName': 'John',
        'sn': 'Doe',
        'initials': 'JD',
        'distinguishedName': 'CN=John Doe,OU=Users,DC=domain,DC=com',
        'description': 'Test description',
        'mail': 'john.doe@domain.com',
        'userPrincipalName': 'john.doe@domain.com',
        'manager': ''
    })
    mocker.patch('routes.users.get_user_by_samaccountname', return_value=mock_user)
    mocker.patch('routes.users.check_permission', return_value=True)
    mocker.patch('routes.users.load_config', return_value={})
    mocker.patch('routes.users.save_to_history')

    # Send POST with new Display Name but same CN
    post_data = get_form_data(mock_user, {'display_name': 'John Doe New Display Name'})
    response = authenticated_client.post('/edit_user/john.doe', data=post_data, follow_redirects=True)
    
    assert response.status_code == 200
    
    # modify should be called to replace displayName
    service_conn.modify.assert_called_once()
    args, kwargs = service_conn.modify.call_args
    assert args[0] == 'CN=John Doe,OU=Users,DC=domain,DC=com'
    # Check that displayName is modified
    changes = args[1]
    assert 'displayName' in changes
    
    # modify_dn should NOT be called since CN is the same
    assert not service_conn.modify_dn.called

def test_edit_user_both_changed(authenticated_client, mocker):
    read_conn = MagicMock()
    service_conn = MagicMock()
    service_conn.result = {'description': 'success'}
    mocker.patch('routes.users.get_read_connection', return_value=read_conn)
    mocker.patch('routes.users.get_service_account_connection', return_value=service_conn)
    
    mock_user = MockLDAPUser({
        'sAMAccountName': 'john.doe',
        'displayName': 'John Doe Original',
        'cn': 'John Doe Original CN',
        'givenName': 'John',
        'sn': 'Doe',
        'initials': 'JD',
        'distinguishedName': 'CN=John Doe Original CN,OU=Users,DC=domain,DC=com',
        'description': 'Test description',
        'mail': 'john.doe@domain.com',
        'userPrincipalName': 'john.doe@domain.com',
        'manager': ''
    })
    mocker.patch('routes.users.get_user_by_samaccountname', return_value=mock_user)
    mocker.patch('routes.users.check_permission', return_value=True)
    mocker.patch('routes.users.load_config', return_value={})
    mocker.patch('routes.users.save_to_history')

    # Send POST with new Display Name AND new CN
    post_data = get_form_data(mock_user, {
        'display_name': 'John Doe New Display Name',
        'cn': 'John Doe New CN'
    })
    response = authenticated_client.post('/edit_user/john.doe', data=post_data, follow_redirects=True)
    
    assert response.status_code == 200
    
    # modify should be called to replace displayName
    service_conn.modify.assert_called_once()
    
    # modify_dn should also be called to rename CN
    service_conn.modify_dn.assert_called_once_with(
        'CN=John Doe Original CN,OU=Users,DC=domain,DC=com',
        'CN=John Doe New CN'
    )

def test_api_convert_user_shared_success(authenticated_client, mocker):
    service_conn = MagicMock()
    service_conn.result = {'description': 'success'}
    mocker.patch('routes.users.get_service_account_connection', return_value=service_conn)
    
    mock_user = MockLDAPUser({
        'sAMAccountName': 'john.doe',
        'distinguishedName': 'CN=John Doe,OU=Users,DC=domain,DC=com',
        'userAccountControl': 512,
        'userPrincipalName': 'john.doe@domain.com',
        'mail': '',
        'targetAddress': '',
        'mailNickname': '',
        'proxyAddresses': []
    })
    mocker.patch('routes.users.get_user_by_samaccountname', return_value=mock_user)
    mocker.patch('routes.users.check_permission', return_value=True)
    mocker.patch('routes.users.save_to_history')
    
    response = authenticated_client.post('/api/convert_user_shared/john.doe')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    
    # Verifica as modificações enviadas ao AD
    service_conn.modify.assert_called_once()
    args, kwargs = service_conn.modify.call_args
    assert args[0] == 'CN=John Doe,OU=Users,DC=domain,DC=com'
    changes = args[1]
    
    # 512 | 2 = 514 (desabilitado)
    assert changes['userAccountControl'] == [('MODIFY_REPLACE', ['514'])]
    assert changes['msExchRecipientTypeDetails'] == [('MODIFY_REPLACE', [34359738368])]
    assert changes['msExchRemoteRecipientType'] == [('MODIFY_REPLACE', [97])]
    
    # Novas validações baseadas no UPN
    assert changes['mail'] == [('MODIFY_REPLACE', ['john.doe@domain.com'])]
    assert changes['targetAddress'] == [('MODIFY_REPLACE', ['john.doe@domain.com'])]
    assert changes['mailNickname'] == [('MODIFY_REPLACE', ['john.doe'])]
    assert changes['proxyAddresses'] == [('MODIFY_REPLACE', ['SMTP:john.doe@domain.com'])]

def test_api_convert_user_shared_missing_upn(authenticated_client, mocker):
    service_conn = MagicMock()
    mocker.patch('routes.users.get_service_account_connection', return_value=service_conn)
    
    mock_user = MockLDAPUser({
        'sAMAccountName': 'john.doe',
        'distinguishedName': 'CN=John Doe,OU=Users,DC=domain,DC=com',
        'userAccountControl': 512,
        'userPrincipalName': ''
    })
    mocker.patch('routes.users.get_user_by_samaccountname', return_value=mock_user)
    mocker.patch('routes.users.check_permission', return_value=True)
    
    response = authenticated_client.post('/api/convert_user_shared/john.doe')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'UPN' in data['error']

def test_api_set_primary_alias_valid_upn_suffix(authenticated_client, mocker):
    service_conn = MagicMock()
    service_conn.result = {'description': 'success'}
    mocker.patch('routes.users.get_service_account_connection', return_value=service_conn)
    
    mock_user = MockLDAPUser({
        'sAMAccountName': 'john.doe',
        'distinguishedName': 'CN=John Doe,OU=Users,DC=domain,DC=com',
        'userPrincipalName': 'john.doe@domain.com',
        'proxyAddresses': ['SMTP:john.doe@domain.com', 'smtp:john.new@comolatti.com.br']
    })
    mocker.patch('routes.users.get_user_by_samaccountname', return_value=mock_user)
    mocker.patch('routes.users.check_permission', return_value=True)
    mocker.patch('routes.users.get_ad_upn_suffixes', return_value=['@domain.com', '@comolatti.com.br'])
    mocker.patch('routes.users.save_to_history')
    
    # Define john.new@comolatti.com.br (UPN suffix válido) como principal
    response = authenticated_client.post('/api/set_primary_alias/john.doe', json={'alias': 'john.new@comolatti.com.br'})
    assert response.status_code == 200
    
    service_conn.modify.assert_called_once()
    args, kwargs = service_conn.modify.call_args
    changes = args[1]
    
    # O UPN não deve ser alterado (não deve estar nas mudanças)
    assert 'userPrincipalName' not in changes
    # O targetAddress deve ser o novo e-mail principal
    assert changes['targetAddress'] == [('MODIFY_REPLACE', ['john.new@comolatti.com.br'])]
    assert changes['mail'] == [('MODIFY_REPLACE', ['john.new@comolatti.com.br'])]

def test_api_set_primary_alias_invalid_upn_suffix(authenticated_client, mocker):
    service_conn = MagicMock()
    service_conn.result = {'description': 'success'}
    mocker.patch('routes.users.get_service_account_connection', return_value=service_conn)
    
    mock_user = MockLDAPUser({
        'sAMAccountName': 'john.doe',
        'distinguishedName': 'CN=John Doe,OU=Users,DC=domain,DC=com',
        'userPrincipalName': 'john.doe@domain.com',
        'proxyAddresses': ['SMTP:john.doe@domain.com', 'smtp:john.new@externo.com']
    })
    mocker.patch('routes.users.get_user_by_samaccountname', return_value=mock_user)
    mocker.patch('routes.users.check_permission', return_value=True)
    # comolatti.com.br é UPN válido, mas externo.com NÃO é
    mocker.patch('routes.users.get_ad_upn_suffixes', return_value=['@domain.com', '@comolatti.com.br'])
    mocker.patch('routes.users.save_to_history')
    
    # Define john.new@externo.com (UPN suffix inválido) como principal
    response = authenticated_client.post('/api/set_primary_alias/john.doe', json={'alias': 'john.new@externo.com'})
    assert response.status_code == 200
    
    service_conn.modify.assert_called_once()
    args, kwargs = service_conn.modify.call_args
    changes = args[1]
    
    # O UPN não deve ser alterado (não deve estar nas mudanças)
    assert 'userPrincipalName' not in changes
    # O targetAddress deve ser atualizado para o novo e-mail principal
    assert changes['targetAddress'] == [('MODIFY_REPLACE', ['john.new@externo.com'])]
    assert changes['mail'] == [('MODIFY_REPLACE', ['john.new@externo.com'])]

def test_api_convert_user_shared_existing_mail_out_of_sync_target(authenticated_client, mocker):
    service_conn = MagicMock()
    service_conn.result = {'description': 'success'}
    mocker.patch('routes.users.get_service_account_connection', return_value=service_conn)
    
    mock_user = MockLDAPUser({
        'sAMAccountName': 'john.doe',
        'distinguishedName': 'CN=John Doe,OU=Users,DC=domain,DC=com',
        'userAccountControl': 512,
        'userPrincipalName': 'john.doe@domain.com',
        'mail': 'john.primary@comolatti.com.br',
        'targetAddress': 'john.old@domain.com',  # targetAddress antigo/desatualizado
        'mailNickname': 'john.doe',
        'proxyAddresses': ['SMTP:john.primary@comolatti.com.br']
    })
    mocker.patch('routes.users.get_user_by_samaccountname', return_value=mock_user)
    mocker.patch('routes.users.check_permission', return_value=True)
    mocker.patch('routes.users.save_to_history')
    
    response = authenticated_client.post('/api/convert_user_shared/john.doe')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    
    service_conn.modify.assert_called_once()
    args, kwargs = service_conn.modify.call_args
    changes = args[1]
    
    # O targetAddress deve ser atualizado para o e-mail principal atual do usuário
    assert changes['targetAddress'] == [('MODIFY_REPLACE', ['john.primary@comolatti.com.br'])]
    # Como mail, mailNickname e proxyAddresses principal já estão corretos e consistentes, eles não devem mudar
    assert 'mail' not in changes
    assert 'mailNickname' not in changes
    assert 'proxyAddresses' not in changes

def test_api_convert_user_normal_success(authenticated_client, mocker):
    service_conn = MagicMock()
    service_conn.result = {'description': 'success'}
    mocker.patch('routes.users.get_service_account_connection', return_value=service_conn)
    
    mock_user = MockLDAPUser({
        'sAMAccountName': 'john.doe',
        'distinguishedName': 'CN=John Doe,OU=Users,DC=domain,DC=com',
        'userAccountControl': 514,  # desabilitado
        'msExchRecipientTypeDetails': 34359738368,
        'msExchRemoteRecipientType': 97,
        'targetAddress': 'john.doe@comolatti.com.br'
    })
    mocker.patch('routes.users.get_user_by_samaccountname', return_value=mock_user)
    mocker.patch('routes.users.check_permission', return_value=True)
    mocker.patch('routes.users.save_to_history')
    
    response = authenticated_client.post('/api/convert_user_normal/john.doe')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    
    service_conn.modify.assert_called_once()
    args, kwargs = service_conn.modify.call_args
    changes = args[1]
    
    # 514 & ~2 = 512 (habilitado)
    assert changes['userAccountControl'] == [('MODIFY_REPLACE', ['512'])]
    assert changes['msExchRecipientTypeDetails'] == [('MODIFY_REPLACE', [])]
    assert changes['msExchRemoteRecipientType'] == [('MODIFY_REPLACE', [])]
    assert changes['targetAddress'] == [('MODIFY_REPLACE', [])]


