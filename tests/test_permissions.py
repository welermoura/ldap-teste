import pytest
import json
from unittest.mock import MagicMock
from common import load_permissions

@pytest.fixture(autouse=True)
def app_context(app):
    with app.app_context():
        yield

def test_load_permissions_normalization(mocker):
    # Mock SQL Server URI check
    mocker.patch('common.get_sql_server_uri', return_value="mssql+pymssql://test")
    
    # Mock Permission model and ensure_db_registered
    mocker.patch('models.ensure_db_registered')
    
    # Mock db.Model.query.all()
    mock_permission_query = mocker.patch('models.Permission.query')
    
    # Create fake Permission database objects
    # Case 1: normal permission with dictionary actions/views
    perm_normal = MagicMock()
    perm_normal.group_name = "GroupNormal"
    perm_normal.type = "custom"
    perm_normal.allowed_ous = json.dumps(["OU=Users,DC=company,DC=com"])
    perm_normal.actions = json.dumps({"can_create": True})
    perm_normal.views = json.dumps({"can_view_user_stats": True})
    
    # Case 2: actions/views stored as empty list string "[]" (as seen in type 'none' saves previously)
    perm_empty_list = MagicMock()
    perm_empty_list.group_name = "GroupEmptyList"
    perm_empty_list.type = "none"
    perm_empty_list.allowed_ous = json.dumps([])
    perm_empty_list.actions = "[]"
    perm_empty_list.views = "[]"
    
    # Case 3: actions/views as None/empty string
    perm_none = MagicMock()
    perm_none.group_name = "GroupNone"
    perm_none.type = "none"
    perm_none.allowed_ous = None
    perm_none.actions = None
    perm_none.views = None
    
    mock_permission_query.all.return_value = [perm_normal, perm_empty_list, perm_none]
    
    result = load_permissions()
    
    # Verify normalization worked
    assert isinstance(result["GroupNormal"]["actions"], dict)
    assert result["GroupNormal"]["actions"].get("can_create") is True
    assert isinstance(result["GroupNormal"]["views"], dict)
    assert result["GroupNormal"]["views"].get("can_view_user_stats") is True
    
    assert isinstance(result["GroupEmptyList"]["actions"], dict)
    assert result["GroupEmptyList"]["actions"] == {}
    assert isinstance(result["GroupEmptyList"]["views"], dict)
    assert result["GroupEmptyList"]["views"] == {}
    
    assert isinstance(result["GroupNone"]["actions"], dict)
    assert result["GroupNone"]["actions"] == {}
    assert isinstance(result["GroupNone"]["views"], dict)
    assert result["GroupNone"]["views"] == {}

def test_api_dashboard_stats_permissions(client, mocker):
    # Mock AD/DB helpers so we don't hit external services
    mocker.patch('routes.admin.get_read_connection')
    mocker.patch('routes.admin.load_config', return_value={})
    
    # Mock paged search generator to return dummy data for active/disabled users
    mock_conn = mocker.patch('routes.admin.get_read_connection').return_value
    mock_conn.extend.standard.paged_search.return_value = [
        {'attributes': {'userAccountControl': 512}}, # active
        {'attributes': {'userAccountControl': 514}}  # disabled
    ]
    
    # We set session variables for authentication
    with client.session_transaction() as sess:
        sess['ad_user'] = 'test_user'
        sess['access_level'] = 'custom'
        sess['user_groups'] = ['TestGroup']

    # Scenario 1: User has 'can_view_user_stats' but NOT 'can_view_deactivated_last_week'
    def mock_check_permission(action=None, field=None, view=None):
        if view == 'can_view_user_stats':
            return True
        return False
        
    mocker.patch('routes.admin.check_permission', side_effect=mock_check_permission)
    
    response = client.get('/api/dashboard/stats')
    assert response.status_code == 200
    data = json.loads(response.data)
    
    # Verify user stats are present
    assert data['active_users'] == 1
    assert data['disabled_users'] == 1
    
    # Verify deactivated last week and trends are empty/0 because we lack permission
    assert data['deactivated_last_week'] == 0
    assert data['trends'] == []
