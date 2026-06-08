import pytest
import json
from unittest.mock import MagicMock, call
from flask import session
from common import get_attr_value

class MockLDAPUser:
    def __init__(self, attributes):
        self._attributes = attributes
        for k, v in attributes.items():
            setattr(self, k, MagicMock(value=v))
            
    def __contains__(self, item):
        return item in self._attributes
        
    def __getitem__(self, item):
        return getattr(self, item)

def get_form_data(user, overrides=None):
    data = {
        'first_name': get_attr_value(user, 'givenName'),
        'last_name': get_attr_value(user, 'sn'),
        'initials': get_attr_value(user, 'initials'),
        'display_name': get_attr_value(user, 'displayName'),
        'cn': get_attr_value(user, 'cn'),
        'description': get_attr_value(user, 'description'),
        'office': get_attr_value(user, 'physicalDeliveryOfficeName'),
        'email': get_attr_value(user, 'mail'),
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
