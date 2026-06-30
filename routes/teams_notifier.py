import logging
import requests

def get_graph_me_identifier(headers):
    """
    Retorna o UPN/ID da própria conta autenticada via /me.
    Requer apenas User.Read (delegado) — sempre disponível em tokens ROPC.
    """
    try:
        res = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers, timeout=10)
        if res.ok:
            data = res.json()
            return data.get('userPrincipalName') or data.get('id')
        logging.warning(f"[TEAMS NOMINAL] /me retornou {res.status_code}: {res.text}")
    except Exception as e:
        logging.warning(f"[TEAMS NOMINAL] Erro ao chamar /me: {e}")
    return None


def get_graph_user_identifier(email, headers):
    """
    Tenta resolver o identificador correto do usuário no Graph API.
    Primeiro tenta obter diretamente pelo e-mail/UPN.
    Se falhar (404), tenta buscar filtrando por mail ou userPrincipalName.
    Retorna o userPrincipalName ou ID se encontrado, ou None se não encontrado.
    Requer a permissão delegada User.ReadBasic.All com admin consent.
    """
    # 1. Tenta obter diretamente
    url = f"https://graph.microsoft.com/v1.0/users/{email}"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.ok:
            user_data = res.json()
            return user_data.get('userPrincipalName') or user_data.get('id')
        else:
            logging.warning(f"[TEAMS NOMINAL] Retorno não-OK ao obter {email} diretamente no Graph: {res.status_code} - {res.text}")
    except Exception as e_direct:
        logging.warning(f"[TEAMS NOMINAL] Erro ao obter {email} diretamente no Graph API: {e_direct}")

    # 2. Se falhar, faz uma busca por filtro
    logging.info(f"[TEAMS NOMINAL] Usuário {email} não encontrado diretamente ou acesso restrito. Buscando via filtro no Entra ID...")
    filter_url = f"https://graph.microsoft.com/v1.0/users?$filter=mail eq '{email}' or userPrincipalName eq '{email}'"
    try:
        filter_res = requests.get(filter_url, headers=headers, timeout=10)
        if filter_res.ok:
            value = filter_res.json().get('value', [])
            if value:
                user_data = value[0]
                resolved = user_data.get('userPrincipalName') or user_data.get('id')
                logging.info(f"[TEAMS NOMINAL] Usuário {email} resolvido no Entra ID como: {resolved}")
                return resolved
        else:
            logging.warning(f"[TEAMS NOMINAL] Retorno não-OK ao filtrar {email} no Graph: {filter_res.status_code} - {filter_res.text}")
    except Exception as e_filter:
        logging.error(f"[TEAMS NOMINAL] Erro ao filtrar usuário {email} no Graph API: {e_filter}")

    # Retorna o próprio email de entrada como um fallback robusto para viabilizar o bind direto no chat
    logging.info(f"[TEAMS NOMINAL] Usando o próprio e-mail '{email}' como fallback para resolução.")
    return email

def send_teams_nominal_security_alert(config, email, anomaly_type, destination, new_password, conn=None):
    """
    Envia alertas de segurança de forma individual (nominal) para os membros de um grupo de segurança do AD
    ou do Microsoft Entra ID cadastrado via chats privados (1-on-1) do MS Teams.
    Utiliza as credenciais corporativas de uma conta de serviço via fluxo ROPC (Resource Owner Password Credentials).
    """
    tenant_id = config.get('TEAMS_TENANT_ID')
    client_id = config.get('TEAMS_CLIENT_ID')
    client_secret = config.get('TEAMS_CLIENT_SECRET')
    user_email = config.get('TEAMS_USER_EMAIL')
    user_password = config.get('TEAMS_USER_PASSWORD')
    target_group = config.get('ZIMBRA_SECURITY_NOTIFY_GROUP', '').strip()
    target_group_id = config.get('ZIMBRA_SECURITY_NOTIFY_GROUP_ID', '').strip()

    missing = []
    if not tenant_id: missing.append('TEAMS_TENANT_ID')
    if not client_id: missing.append('TEAMS_CLIENT_ID')
    if not user_email: missing.append('TEAMS_USER_EMAIL')
    if not user_password: missing.append('TEAMS_USER_PASSWORD')
    if not (target_group or target_group_id): missing.append('ZIMBRA_SECURITY_NOTIFY_GROUP / ZIMBRA_SECURITY_NOTIFY_GROUP_ID')

    if missing:
        logging.warning(f"[TEAMS NOMINAL SIMULATOR] Alerta nominal não enviado devido a credenciais ausentes: {', '.join(missing)}")
        logging.warning(f"[TEAMS NOMINAL SIMULATOR] Alerta simulado: Conta {email} continha {anomaly_type} externo direcionado para {destination}. Nova senha AD gerada: {new_password}")
        return False

    try:
        # 1. Obter Token OAuth2 Delegado usando fluxo ROPC (Resource Owner Password Credentials)
        logging.info(f"[TEAMS NOMINAL] Solicitando token de usuário delegado via ROPC para {user_email}...")
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        token_payload = {
            'grant_type': 'password',
            'client_id': client_id,
            'scope': 'https://graph.microsoft.com/.default',
            'username': user_email,
            'password': user_password
        }
        if client_secret:
            token_payload['client_secret'] = client_secret

        token_res = requests.post(token_url, data=token_payload, timeout=10)
        if not token_res.ok:
            raise Exception(f"Falha na autenticação ROPC: {token_res.status_code} - {token_res.text}")
        
        access_token = token_res.json().get('access_token')
        if not access_token:
            raise Exception("Token de acesso delegado não encontrado na resposta do Entra ID.")

        # 2. Obter membros do grupo (do Entra ID ou do AD local)
        member_emails = set()
        is_entra_group = False

        import re
        is_uuid = bool(re.match(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$', target_group_id))

        if is_uuid:
            logging.info(f"[TEAMS NOMINAL] Buscando membros do grupo do Entra ID {target_group_id}...")
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            members_url = f"https://graph.microsoft.com/v1.0/groups/{target_group_id}/members?$select=id,userPrincipalName,mail,displayName"
            try:
                members_res = requests.get(members_url, headers=headers, timeout=10)
                if members_res.ok:
                    raw_members = members_res.json().get('value', [])
                    for m in raw_members:
                        upn = m.get('userPrincipalName') or m.get('mail')
                        if upn:
                            member_emails.add(upn.strip().lower())
                    is_entra_group = True
                    logging.info(f"[TEAMS NOMINAL] Membros obtidos do Entra ID: {member_emails}")
                else:
                    logging.error(f"[TEAMS NOMINAL] Erro ao acessar membros do grupo no Entra ID: {members_res.status_code} - {members_res.text}")
            except Exception as e_entra:
                logging.error(f"[TEAMS NOMINAL] Exceção ao buscar membros no Entra ID: {str(e_entra)}")

        if not is_entra_group:
            # Fallback clássico para o Active Directory local (LDAP)
            logging.info(f"[TEAMS NOMINAL] Fazendo fallback para o Active Directory local para buscar o grupo '{target_group}'...")
            ldap_conn = conn
            if not ldap_conn:
                try:
                    from common import get_service_account_connection
                    ldap_conn = get_service_account_connection()
                except Exception as e_conn:
                    logging.error(f"[TEAMS NOMINAL] Falha ao obter conexão de serviço AD para alertas nominais: {e_conn}")
                    return False
            
            try:
                from common import get_group_by_name, get_group_members_emails
                group_entry = get_group_by_name(ldap_conn, target_group)
                if not group_entry:
                    logging.error(f"[TEAMS NOMINAL] Grupo de segurança '{target_group}' não foi encontrado no AD local nem no Entra ID. Alerta abortado.")
                    return False
                
                group_dn = group_entry.entry_dn
                member_emails = get_group_members_emails(ldap_conn, group_dn)
            except Exception as e_ad:
                logging.error(f"[TEAMS NOMINAL] Erro ao carregar membros do grupo '{target_group}' no AD local: {e_ad}", exc_info=True)
                return False

        if not member_emails:
            logging.warning(f"[TEAMS NOMINAL] O grupo de segurança '{target_group or target_group_id}' não contém membros ou nenhum membro possui e-mail cadastrado.")
            return False

        # 4. Formatar o HTML Rico para o Alerta Nominal
        mensagem_html = f"""
        <div style="font-family: Arial, sans-serif; border-left: 5px solid #E81123; padding-left: 15px; max-width: 600px;">
            <h3 style="color: #E81123; margin-top: 0; margin-bottom: 5px;">🚨 Alerta de Autoremediação de Segurança - Anomalia Removida</h3>
            <p style="color: #323130; margin-top: 0; margin-bottom: 15px;">Uma configuração insegura ou vazamento potencial de dados foi identificado e remediado automaticamente nas configurações de e-mail do Zimbra.</p>
            
            <table style="width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 15px;">
                <tr>
                    <td style="padding: 6px 0; font-weight: bold; width: 180px; color: #605E5C;">👤 Conta Remediada:</td>
                    <td style="padding: 6px 0; color: #323130; font-weight: bold;">{email}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; font-weight: bold; color: #605E5C;">⚠️ Tipo de Anomalia:</td>
                    <td style="padding: 6px 0;"><span style="background-color: #FDE7E9; color: #A80000; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; text-transform: uppercase;">{anomaly_type}</span></td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; font-weight: bold; color: #605E5C;">📬 Destinatário Externo:</td>
                    <td style="padding: 6px 0; color: #E81123; font-weight: bold; word-break: break-all;">{destination}</td>
                </tr>
                <tr style="background-color: #F3F2F1;">
                    <td style="padding: 12px; font-weight: bold; color: #323130; border-radius: 4px 0 0 4px;">🔑 Nova Senha Temporária AD:</td>
                    <td style="padding: 12px; font-family: 'Consolas', 'Courier New', monospace; font-size: 15px; font-weight: bold; color: #0078D4; border-radius: 0 4px 4px 0; letter-spacing: 0.5px;">
                        <strong>{new_password}</strong>
                    </td>
                </tr>
            </table>
            
            <p style="margin-top: 10px; font-size: 11px; color: #605E5C; line-height: 1.4;">
                <i>* O recurso foi desativado no Zimbra e a senha do usuário foi resetada com sucesso no Active Directory. O usuário precisará definir uma nova senha no seu próximo logon no domínio corporativo.</i>
            </p>
        </div>
        """

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        # Resolve o identificador da conta de serviço via /me (requer apenas User.Read)
        resolved_service_user = get_graph_me_identifier(headers)
        if not resolved_service_user:
            # Fallback: tenta resolver pelo e-mail (requer User.ReadBasic.All)
            resolved_service_user = get_graph_user_identifier(user_email, headers)
        if not resolved_service_user:
            logging.error(f"[TEAMS NOMINAL] Não foi possível resolver a conta de serviço {user_email} no Microsoft Entra ID. Alerta abortado.")
            return False

        # 5. Iterar sobre todos os membros do grupo e disparar no chat privado (oneOnOne)
        success_count = 0
        for member_email in member_emails:
            # Evita o envio para a própria conta de serviço que está enviando
            if member_email.lower() == user_email.lower():
                continue
                
            try:
                # Resolve o identificador/UPN correto do destinatário no Entra ID (evita 404 caso seja diferente do mail AD)
                resolved_member_user = get_graph_user_identifier(member_email, headers)
                if not resolved_member_user:
                    logging.warning(f"[TEAMS NOMINAL] Não foi possível resolver o usuário {member_email} no Microsoft Entra ID. Pulando envio nominal.")
                    continue

                if resolved_member_user.lower() == resolved_service_user.lower():
                    continue

                # 5.1 Criar ou buscar o canal de chat privado
                logging.info(f"[TEAMS NOMINAL] Abrindo canal de chat privado 1-on-1 com {resolved_member_user} (mail original: {member_email})...")
                chat_url = "https://graph.microsoft.com/v1.0/chats"
                chat_payload = {
                    "chatType": "oneOnOne",
                    "members": [
                        {
                            "@odata.type": "#microsoft.graph.aadUserConversationMember",
                            "roles": ["owner"],
                            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{resolved_service_user}')"
                        },
                        {
                            "@odata.type": "#microsoft.graph.aadUserConversationMember",
                            "roles": ["owner"],
                            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{resolved_member_user}')"
                        }
                    ]
                }
                chat_res = requests.post(chat_url, json=chat_payload, headers=headers, timeout=10)
                if not chat_res.ok:
                    logging.error(f"[TEAMS NOMINAL] Erro ao criar canal de chat com {member_email}: {chat_res.status_code} - {chat_res.text}")
                    continue
                    
                chat_id = chat_res.json().get('id')
                if not chat_id:
                    logging.error(f"[TEAMS NOMINAL] Campo ID ausente no chat privado de {member_email}")
                    continue
                
                # 5.2 Postar a mensagem no chat privado
                logging.info(f"[TEAMS NOMINAL] Enviando mensagem de segurança no chat {chat_id} para {member_email}...")
                message_url = f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages"
                message_payload = {
                    "body": {
                        "contentType": "html",
                        "content": mensagem_html
                    }
                }
                msg_res = requests.post(message_url, json=message_payload, headers=headers, timeout=10)
                if not msg_res.ok:
                    logging.error(f"[TEAMS NOMINAL] Falha ao enviar mensagem de alerta para {member_email}: {msg_res.status_code} - {msg_res.text}")
                    continue
                    
                success_count += 1
                logging.info(f"[TEAMS NOMINAL] Alerta de segurança enviado com sucesso para {member_email}.")
                
            except Exception as ex:
                logging.error(f"[TEAMS NOMINAL] Exceção durante envio de mensagem nominal para {member_email}: {ex}", exc_info=True)

        logging.info(f"[TEAMS NOMINAL] Processo finalizado com sucesso para {success_count}/{len(member_emails)} membros.")
        return success_count > 0

    except Exception as e:
        logging.error(f"[TEAMS NOMINAL] Erro crítico ao enviar alertas nominais para o Teams via Graph API: {e}", exc_info=True)
        return False


def send_teams_security_alert(config, email, anomaly_type, destination, new_password, conn=None):
    """
    Envia uma notificação rica em formato HTML para o Teams (no canal do grupo ou nominalmente via chats privados).
    Utiliza as configurações cadastradas no sistema.
    """
    # Intercepta e delega caso a notificação nominal esteja ativada
    is_nominal = config.get('ZIMBRA_SECURITY_NOTIFY_NOMINAL', 'False') == 'True'
    if is_nominal:
        return send_teams_nominal_security_alert(config, email, anomaly_type, destination, new_password, conn=conn)

    # Fluxo clássico por canal público usando Application Token (Client Credentials)
    tenant_id = config.get('TEAMS_TENANT_ID')
    client_id = config.get('TEAMS_CLIENT_ID')
    client_secret = config.get('TEAMS_CLIENT_SECRET')
    team_id = config.get('TEAMS_GROUP_ID')
    channel_id = config.get('TEAMS_CHANNEL_ID')

    missing = []
    if not tenant_id: missing.append('TEAMS_TENANT_ID')
    if not client_id: missing.append('TEAMS_CLIENT_ID')
    if not client_secret: missing.append('TEAMS_CLIENT_SECRET')
    if not team_id: missing.append('TEAMS_GROUP_ID')
    if not channel_id: missing.append('TEAMS_CHANNEL_ID')

    if missing:
        logging.warning(f"[TEAMS SIMULATOR] Alerta não enviado devido a credenciais ausentes: {', '.join(missing)}")
        logging.warning(f"[TEAMS SIMULATOR] Alerta simulado: Conta {email} continha {anomaly_type} externo direcionado para {destination}. Nova senha AD gerada: {new_password}")
        return False

    try:
        # 1. Obter Token OAuth2 do Entra ID (Application Token)
        logging.info("Obtendo token do Microsoft Entra ID para envio de alerta...")
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        token_payload = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
            'scope': 'https://graph.microsoft.com/.default'
        }
        token_res = requests.post(token_url, data=token_payload, timeout=10)
        if not token_res.ok:
            raise Exception(f"Falha na autenticação do Entra: {token_res.status_code} - {token_res.text}")
        
        access_token = token_res.json().get('access_token')
        if not access_token:
            raise Exception("Token de acesso não encontrado na resposta do Entra ID.")

        # 2. Formatar o HTML Rico para o Alerta
        mensagem_html = f"""
        <div style="font-family: Arial, sans-serif; border-left: 5px solid #E81123; padding-left: 15px; max-width: 600px;">
            <h3 style="color: #E81123; margin-top: 0; margin-bottom: 5px;">🚨 Alerta de Autoremediação de Segurança - Anomalia Removida</h3>
            <p style="color: #323130; margin-top: 0; margin-bottom: 15px;">Uma configuração insegura ou vazamento potencial de dados foi identificado e remediado automaticamente nas configurações de e-mail do Zimbra.</p>
            
            <table style="width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 15px;">
                <tr>
                    <td style="padding: 6px 0; font-weight: bold; width: 180px; color: #605E5C;">👤 Conta Remediada:</td>
                    <td style="padding: 6px 0; color: #323130; font-weight: bold;">{email}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; font-weight: bold; color: #605E5C;">⚠️ Tipo de Anomalia:</td>
                    <td style="padding: 6px 0;"><span style="background-color: #FDE7E9; color: #A80000; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; text-transform: uppercase;">{anomaly_type}</span></td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; font-weight: bold; color: #605E5C;">📬 Destinatário Externo:</td>
                    <td style="padding: 6px 0; color: #E81123; font-weight: bold; word-break: break-all;">{destination}</td>
                </tr>
                <tr style="background-color: #F3F2F1;">
                    <td style="padding: 12px; font-weight: bold; color: #323130; border-radius: 4px 0 0 4px;">🔑 Nova Senha Temporária AD:</td>
                    <td style="padding: 12px; font-family: 'Consolas', 'Courier New', monospace; font-size: 15px; font-weight: bold; color: #0078D4; border-radius: 0 4px 4px 0; letter-spacing: 0.5px;">
                        <strong>{new_password}</strong>
                    </td>
                </tr>
            </table>
            
            <p style="margin-top: 10px; font-size: 11px; color: #605E5C; line-height: 1.4;">
                <i>* O recurso foi desativado no Zimbra e a senha do usuário foi resetada com sucesso no Active Directory. O usuário precisará definir uma nova senha no seu próximo logon no domínio corporativo.</i>
            </p>
        </div>
        """

        # 3. Enviar no Canal via Graph API
        logging.info(f"Enviando alerta no canal do Teams: {channel_id}...")
        graph_url = f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{channel_id}/messages"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        payload = {
            "body": {
                "contentType": "html",
                "content": mensagem_html
            }
        }
        
        graph_res = requests.post(graph_url, json=payload, headers=headers, timeout=10)
        if not graph_res.ok:
            raise Exception(f"Erro na requisição Graph API: {graph_res.status_code} - {graph_res.text}")
            
        logging.info(f"Alerta de segurança enviado com sucesso para o MS Teams para a conta {email}.")
        return True

    except Exception as e:
        logging.error(f"Erro ao enviar alerta para o Teams via Graph API: {e}", exc_info=True)
        return False
