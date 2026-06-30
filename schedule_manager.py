import os
import json
import logging
import ldap3
from datetime import date
from common import (
    load_config, get_ldap_connection, get_user_by_samaccountname, 
    get_group_by_name, load_disable_schedules, save_disable_schedules,
    load_group_schedules, save_group_schedules, save_to_history,
    load_schedules, save_schedules
)

# ==============================================================================
# Configuração de Logs
# ==============================================================================
basedir = os.path.abspath(os.path.dirname(__file__))
logs_dir = os.path.join(basedir, 'logs')
os.makedirs(logs_dir, exist_ok=True)

log_path = os.path.join(logs_dir, 'schedule_manager.log')
logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%d-%m-%Y %H:%M:%S',
    encoding='utf-8'
)

# ==============================================================================
# Lógica de Processamento
# ==============================================================================

def process_user_deactivations(conn, search_base):
    """Processa a desativação agendada de contas de usuário."""
    logging.info("Iniciando verificação de desativações de usuários.")
    schedules = load_disable_schedules()
    if not schedules:
        logging.info("Nenhum agendamento de desativação pendente.")
        return

    today = date.today().isoformat()
    schedules_to_keep = {}
    for username, deactivation_date in schedules.items():
        if deactivation_date <= today:
            logging.info(f"Tentando desativar o usuário '{username}' agendado para {deactivation_date}.")
            user = get_user_by_samaccountname(conn, username)
            if user:
                uac = user.userAccountControl.value
                if not (uac & 2): # Se a conta NÃO estiver desativada
                    new_uac = uac | 2 # Adiciona a flag de desativação
                    conn.modify(user.distinguishedName.value, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(new_uac)])]})
                    if conn.result['description'] == 'success':
                        logging.info(f"Usuário '{username}' desativado com sucesso.")
                        save_to_history('deactivation', username, f"Desativação agendada para {deactivation_date} executada.")
                    else:
                        logging.error(f"Falha ao desativar '{username}': {conn.result['message']}. Mantendo agendamento.")
                        schedules_to_keep[username] = deactivation_date
                else:
                    logging.warning(f"Usuário '{username}' já estava desativado. Removendo agendamento de desativação.")
            else:
                logging.warning(f"Usuário '{username}' agendado para desativação não encontrado. Removendo agendamento.")
        else:
            schedules_to_keep[username] = deactivation_date

    save_disable_schedules(schedules_to_keep)
    logging.info("Verificação de desativações de usuários concluída.")


def process_user_reactivations(conn, search_base):
    """Processa a reativação de contas de usuário."""
    logging.info("Iniciando verificação de reativações de usuários.")
    schedules = load_schedules()
    if not schedules:
        logging.info("Nenhum agendamento de reativação pendente.")
        return

    today = date.today().isoformat()
    schedules_to_keep = {}
    for username, reactivation_date in schedules.items():
        if reactivation_date <= today:
            logging.info(f"Tentando reativar o usuário '{username}' agendado para {reactivation_date}.")
            user = get_user_by_samaccountname(conn, username)
            if user:
                uac = user.userAccountControl.value
                if uac & 2:  # Se a conta estiver desativada
                    new_uac = uac - 2
                    conn.modify(user.distinguishedName.value, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(new_uac)])]})
                    if conn.result['description'] == 'success':
                        logging.info(f"Usuário '{username}' reativado com sucesso.")
                        save_to_history('reactivation', username, f"Reativação agendada para {reactivation_date} executada.")
                    else:
                        logging.error(f"Falha ao reativar '{username}': {conn.result['message']}. Mantendo agendamento.")
                        schedules_to_keep[username] = reactivation_date
                else:
                    logging.warning(f"Usuário '{username}' já estava ativo. Removendo agendamento de reativação.")
            else:
                logging.warning(f"Usuário '{username}' agendado para reativação não encontrado. Removendo agendamento.")
        else:
            schedules_to_keep[username] = reactivation_date

    save_schedules(schedules_to_keep)
    logging.info("Verificação de reativações de usuários concluída.")

def process_group_membership_changes(conn, search_base):
    """Processa as alterações agendadas de associação a grupos."""
    logging.info("Iniciando verificação de alterações de associação a grupos.")
    schedules = load_group_schedules()
    if not schedules:
        logging.info("Nenhum agendamento de grupos pendente.")
        return

    today = date.today().isoformat()
    remaining_schedules = []
    for schedule in schedules:
        execution_date = schedule.get('execution_date') or schedule.get('revert_date')
        action = schedule.get('action') or schedule.get('revert_action')

        if not execution_date or not action:
            logging.warning(f"Agendamento malformado ignorado: {schedule}")
            continue

        if execution_date <= today:
            user_sam, group_name = schedule['user_sam'], schedule['group_name']
            logging.info(f"Processando: {action} '{user_sam}' em '{group_name}' agendado para {execution_date}.")

            user = get_user_by_samaccountname(conn, user_sam)
            group = get_group_by_name(conn, group_name)

            if not user or not group:
                logging.warning(f"Usuário '{user_sam}' ou grupo '{group_name}' não encontrado. Removendo agendamento.")
                continue

            try:
                if action == 'add':
                    conn.extend.microsoft.add_members_to_groups([user.distinguishedName.value], group.distinguishedName.value)
                elif action == 'remove':
                    conn.extend.microsoft.remove_members_from_groups([user.distinguishedName.value], group.distinguishedName.value)

                if conn.result['description'] == 'success':
                    logging.info(f"Sucesso ao executar a ação '{action}' para '{user_sam}' no grupo '{group_name}'.")
                    save_to_history('group_change', user_sam, f"Ação '{action}' no grupo '{group_name}' executada (agendado).")
                else:
                    logging.error(f"Falha na ação '{action}' para '{user_sam}': {conn.result['message']}. Mantendo agendamento.")
                    remaining_schedules.append(schedule)

            except Exception as e:
                logging.error(f"Exceção ao processar agendamento para '{user_sam}': {e}. Mantendo agendamento.")
                remaining_schedules.append(schedule)
        else:
            remaining_schedules.append(schedule)

    save_group_schedules(remaining_schedules)
    logging.info("Verificação de alterações de associação a grupos concluída.")


def process_zimbra_group_syncs(conn, config):
    """Sincroniza todos os grupos do AD mapeados com o Zimbra de forma agendada."""
    logging.info("Iniciando sincronização automática de grupos com o Zimbra.")
    
    if not config.get('ZIMBRA_ENABLED', False):
        logging.info("A integração com o Zimbra está desativada nas configurações.")
        return

    zimbra_url = config.get('ZIMBRA_API_URL')
    zimbra_user = config.get('ZIMBRA_ADMIN_USER')
    zimbra_password = config.get('ZIMBRA_ADMIN_PASSWORD')
    
    if not zimbra_url or not zimbra_user or not zimbra_password:
        logging.error("Configurações do Zimbra incompletas ou ausentes. Pulando sincronização.")
        return

    try:
        from routes.zimbra import load_zimbra_mappings
        mappings = load_zimbra_mappings()
    except Exception as e:
        logging.error(f"Erro ao carregar os mapeamentos do Zimbra: {e}")
        return

    if not mappings:
        logging.info("Nenhum mapeamento de grupo do Zimbra encontrado.")
        return

    from routes.zimbra_api import ZimbraSOAPClient
    from routes.utils import get_user_by_dn
    from common import get_attr_value, get_group_by_name

    try:
        client = ZimbraSOAPClient(zimbra_url, zimbra_user, zimbra_password)
    except Exception as e:
        logging.error(f"Erro ao inicializar o cliente SOAP do Zimbra: {e}")
        return

    for mapping in mappings:
        if not mapping.get('active', True):
            logging.info(f"Mapeamento para grupo AD '{mapping.get('ad_group_name')}' está inativo. Pulando.")
            continue

        ad_group = mapping.get('ad_group_name', '').strip()
        zimbra_email = mapping.get('zimbra_dl_email', '').strip()
        
        if not ad_group or not zimbra_email:
            continue
            
        logging.info(f"Sincronizando grupo AD '{ad_group}' com lista Zimbra '{zimbra_email}'...")
        try:
            ad_group_obj = get_group_by_name(conn, ad_group, ['distinguishedName'])
            if not ad_group_obj:
                logging.error(f"Grupo do AD '{ad_group}' não foi encontrado para sincronização.")
                # Se o grupo não existir no AD, verifica se a lista de distribuição também não existe no Zimbra
                zimbra_exists = True
                try:
                    client.get_dl_members(zimbra_email)
                except Exception as e:
                    if "NO_SUCH_DISTRIBUTION_LIST" in str(e):
                        zimbra_exists = False
                
                # Exclui a DL do Zimbra se o grupo do AD foi removido
                if zimbra_exists:
                    try:
                        client.delete_dl(zimbra_email)
                        logging.warning(f"Lista do Zimbra '{zimbra_email}' excluída automaticamente porque o grupo AD '{ad_group}' correspondente foi removido.")
                        zimbra_exists = False
                    except Exception as e_dl_del:
                        logging.error(f"Erro ao excluir DL no Zimbra '{zimbra_email}' para o grupo AD removido '{ad_group}': {e_dl_del}")

                try:
                    from models import db, ZimbraMapping
                    db_m = ZimbraMapping.query.filter_by(ad_group_name=ad_group).first()
                    if db_m:
                        db.session.delete(db_m)
                        db.session.commit()
                        if not zimbra_exists:
                            save_to_history('zimbra_mapping_delete', ad_group, f"Mapeamento e lista do Zimbra removidos automaticamente pelo agendador porque o grupo AD '{ad_group}' foi removido.")
                            logging.warning(f"Mapeamento '{ad_group}' -> '{zimbra_email}' deletado automaticamente (ambos ausentes).")
                        else:
                            save_to_history('zimbra_mapping_delete', ad_group, f"Mapeamento removido automaticamente pelo agendador porque o grupo AD '{ad_group}' não existe mais.")
                            logging.warning(f"Mapeamento '{ad_group}' -> '{zimbra_email}' deletado automaticamente (grupo AD ausente).")
                except Exception as e_del:
                    logging.error(f"Erro ao deletar mapeamento do banco de dados para '{ad_group}': {e_del}")
                continue

            # Extrai as identidades dos membros do AD (e-mail principal e aliases)
            from common import get_group_members_identities
            ad_members = get_group_members_identities(conn, ad_group_obj.distinguishedName.value)

            # Conecta no Zimbra
            try:
                dl_info = client.get_dl_members(zimbra_email)
            except Exception as e:
                if "NO_SUCH_DISTRIBUTION_LIST" in str(e):
                    logging.warning(f"Lista '{zimbra_email}' não existe no Zimbra. Removendo mapeamento.")
                    try:
                        from models import db, ZimbraMapping
                        db_m = ZimbraMapping.query.filter_by(ad_group_name=ad_group).first()
                        if db_m:
                            db.session.delete(db_m)
                            db.session.commit()
                            save_to_history('zimbra_mapping_delete', ad_group, f"Mapeamento removido automaticamente pelo agendador porque a lista Zimbra '{zimbra_email}' não existe mais.")
                            logging.warning(f"Mapeamento '{ad_group}' -> '{zimbra_email}' deletado automaticamente (lista Zimbra ausente).")
                    except Exception as e_del:
                        logging.error(f"Erro ao deletar mapeamento do banco de dados para '{ad_group}': {e_del}")
                    continue
                else:
                    logging.error(f"Erro ao buscar membros da lista Zimbra '{zimbra_email}': {e}")
                    continue

            # Normalizar e-mails do Zimbra
            zimbra_emails = {m.strip().lower() for m in dl_info['members']}
            zimbra_real_email = dl_info['email']

            # Carrega as identidades completas (e-mail principal + apelidos/aliases) para cada membro do Zimbra em paralelo
            zimbra_member_identities = {}
            from concurrent.futures import ThreadPoolExecutor
            
            def fetch_zimbra_identity(z_email):
                acc_info = client.get_account_info(z_email)
                if acc_info:
                    identities = {acc_info['email']} | set(acc_info['aliases'])
                else:
                    identities = {z_email}
                return z_email, identities
                
            with ThreadPoolExecutor(max_workers=20) as executor:
                results = executor.map(fetch_zimbra_identity, zimbra_emails)
                for z_email, identities in results:
                    zimbra_member_identities[z_email] = identities

            # Mapeia cada e-mail do Zimbra ao membro correspondente do AD (se houver) para evitar duplicatas/aliases
            ad_member_to_zimbra_emails = {i: [] for i in range(len(ad_members))}
            unmatched_zimbra_emails = set()
            
            for z_email, z_identities in zimbra_member_identities.items():
                matched_indices = []
                for i, member in enumerate(ad_members):
                    if z_identities & member['all_emails']:
                        matched_indices.append(i)
                
                if matched_indices:
                    for idx in matched_indices:
                        ad_member_to_zimbra_emails[idx].append(z_email)
                else:
                    unmatched_zimbra_emails.add(z_email)
                    
            to_add = set()
            to_remove = set(unmatched_zimbra_emails)
            
            for i, member in enumerate(ad_members):
                matching_emails = ad_member_to_zimbra_emails[i]
                if not matching_emails:
                    if member['primary_email']:
                        to_add.add(member['primary_email'])
                else:
                    # Se o usuário está representado por múltiplos e-mails/aliases na DL, mantém apenas um
                    primary = member['primary_email']
                    if primary and primary in matching_emails:
                        keep_email = primary
                    else:
                        keep_email = matching_emails[0]
                        
                    for email in matching_emails:
                        if email != keep_email:
                            to_remove.add(email)

            added_count = 0
            for email in to_add:
                try:
                    client.add_dl_member(zimbra_real_email, email)
                    added_count += 1
                except Exception as e_add:
                    logging.error(f"Falha ao adicionar membro '{email}' à lista '{zimbra_real_email}': {e_add}")

            removed_count = 0
            for email in to_remove:
                try:
                    client.remove_dl_member(zimbra_real_email, email)
                    removed_count += 1
                except Exception as e_rem:
                    logging.error(f"Falha ao remover membro '{email}' da lista '{zimbra_real_email}': {e_rem}")

            if added_count > 0 or removed_count > 0:
                logging.info(f"Sucesso na sincronização do grupo '{ad_group}' -> '{zimbra_real_email}': {added_count} adicionados, {removed_count} removidos.")
                save_to_history('zimbra_sync', 'scheduler', f"Sincronização automática para '{zimbra_real_email}': {added_count} adicionados, {removed_count} removidos.")
            else:
                logging.info(f"Grupo '{zimbra_real_email}' já está 100% sincronizado (sem alterações).")

        except Exception as e:
            logging.error(f"Erro ao processar sincronização automática para o grupo '{ad_group}': {e}")

    logging.info("Sincronização automática de grupos com o Zimbra concluída.")


def generate_secure_password(length=12):
    """Gera uma senha forte e randômica que atenda aos requisitos de complexidade do AD."""
    import secrets
    import string
    
    uppercase = string.ascii_uppercase
    lowercase = string.ascii_lowercase
    digits = string.digits
    special = "!@#$%-+=_?"
    
    password = [
        secrets.choice(uppercase),
        secrets.choice(lowercase),
        secrets.choice(digits),
        secrets.choice(special)
    ]
    
    all_chars = uppercase + lowercase + digits + special
    for _ in range(length - 4):
        password.append(secrets.choice(all_chars))
        
    secrets.SystemRandom().shuffle(password)
    return "".join(password)


def process_zimbra_security_auto_remediation(conn, config, force=False):
    """
    Varre as contas do Zimbra em busca de encaminhamentos, reply-to ou notificações
    direcionados para e-mails externos não autorizados em contas que não estão na whitelist.
    Caso encontre, altera a senha no AD, desativa no Zimbra e envia alerta no Teams.
    """
    from datetime import datetime, timedelta
    from common import save_config

    logging.info("Iniciando verificação de segurança (Autoremediação Zimbra).")
    
    # 1. Verifica se a autoremediação está ativada nas configurações
    remediation_enabled = config.get('ZIMBRA_AUTO_REMEDIATION_ENABLED')
    if not remediation_enabled or str(remediation_enabled).lower() != 'true':
        logging.info("Autoremediação automática do Zimbra está desativada.")
        return

    # 1.1. Verifica intervalo de execução agendado se não for forçado
    if not force:
        try:
            interval_minutes = int(config.get('ZIMBRA_AUDIT_INTERVAL_MINUTES', '240'))
        except (ValueError, TypeError):
            interval_minutes = 240
            
        last_run_str = config.get('ZIMBRA_LAST_AUDIT_TIMESTAMP', '')
        if last_run_str:
            try:
                last_run = datetime.strptime(last_run_str, '%Y-%m-%d %H:%M:%S')
                if datetime.now() - last_run < timedelta(minutes=interval_minutes):
                    logging.info(f"[AUTOREMEDIATION] Menos de {interval_minutes} minutos se passaram desde o último run ({last_run_str}). Pulando execução agendada.")
                    return
            except Exception as ex:
                logging.error(f"[AUTOREMEDIATION] Erro ao analisar última data de auditoria '{last_run_str}': {ex}")

    try:
        # 2. Carrega a whitelist de segurança (lista de e-mails autorizados separados por vírgula)
        whitelist_str = config.get('ZIMBRA_SECURITY_WHITELIST', '')
        whitelist = {email.strip().lower() for email in whitelist_str.split(',') if email.strip()}

        # 3. Conecta à API do Zimbra
        zimbra_url = config.get('ZIMBRA_API_URL')
        zimbra_user = config.get('ZIMBRA_ADMIN_USER')
        zimbra_password = config.get('ZIMBRA_ADMIN_PASSWORD')
        
        if not zimbra_url or not zimbra_user or not zimbra_password:
            logging.error("Configurações do Zimbra incompletas para auditoria de segurança.")
            config['ZIMBRA_LAST_AUDIT_TIMESTAMP'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            config['ZIMBRA_LAST_AUDIT_STATUS'] = 'Failed: Configurações do Zimbra incompletas'
            save_config(config)
            return

        from routes.zimbra_api import ZimbraSOAPClient
        try:
            client = ZimbraSOAPClient(zimbra_url, zimbra_user, zimbra_password)
        except Exception as e:
            logging.error(f"Erro ao inicializar cliente Zimbra para autoremediação: {e}")
            config['ZIMBRA_LAST_AUDIT_TIMESTAMP'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            config['ZIMBRA_LAST_AUDIT_STATUS'] = f'Failed: Erro ao inicializar cliente Zimbra: {str(e)}'
            save_config(config)
            return

        # 4. Obtém os domínios corporativos internos autorizados
        try:
            domains = client.get_domains()
            internal_domains = {d.get('name', '').strip().lower() for d in domains if d.get('name')}
            logging.info(f"Domínios internos autorizados: {', '.join(internal_domains)}")
        except Exception as e:
            logging.error(f"Erro ao obter domínios corporativos internos no Zimbra: {e}")
            config['ZIMBRA_LAST_AUDIT_TIMESTAMP'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            config['ZIMBRA_LAST_AUDIT_STATUS'] = f'Failed: Erro ao obter domínios corporativos internos: {str(e)}'
            save_config(config)
            return

        # Helper para verificar se um e-mail é externo
        def is_external_email(email_addr):
            if not email_addr or '@' not in email_addr:
                return False
            parts = email_addr.split('@')
            domain = parts[-1].strip().lower()
            return domain not in internal_domains

        # 5. Varre contas do Zimbra que possuam regras suspeitas
        try:
            accounts = client.search_accounts_with_forwarding()
        except Exception as e:
            logging.error(f"Erro ao buscar contas no Zimbra para verificação de segurança: {e}")
            config['ZIMBRA_LAST_AUDIT_TIMESTAMP'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            config['ZIMBRA_LAST_AUDIT_STATUS'] = f'Failed: Erro ao buscar contas no Zimbra: {str(e)}'
            save_config(config)
            return

        if not accounts:
            logging.info("Nenhuma conta com encaminhamento, reply-to ou notificação configurada encontrada.")
            config['ZIMBRA_LAST_AUDIT_TIMESTAMP'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            config['ZIMBRA_LAST_AUDIT_STATUS'] = 'Success'
            save_config(config)
            return

        search_base = config.get('AD_SEARCH_BASE')
        if not search_base:
            logging.error("AD_SEARCH_BASE não definido. Não é possível rodar a autoremediação sem buscar usuários no AD.")
            config['ZIMBRA_LAST_AUDIT_TIMESTAMP'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            config['ZIMBRA_LAST_AUDIT_STATUS'] = 'Failed: AD_SEARCH_BASE não definido'
            save_config(config)
            return

        from ldap3.utils.conv import escape_filter_chars
        from routes.teams_notifier import send_teams_security_alert

        for account in accounts:
            account_email = account.get('email', '').strip().lower()
            account_id = account.get('id')
            
            if not account_email or not account_id:
                continue

            # Identifica as anomalias externas
            unauthorized_forwardings = [addr for addr in account.get('forwarding_addresses', []) if is_external_email(addr)]
            unauthorized_reply_to = account.get('reply_to', '') if is_external_email(account.get('reply_to', '')) else ''
            unauthorized_notification = account.get('notification_address', '') if is_external_email(account.get('notification_address', '')) else ''

            # Se não houver anomalias, pula esta conta
            if not unauthorized_forwardings and not unauthorized_reply_to and not unauthorized_notification:
                continue

            # Se a conta estiver na whitelist, apenas loga e pula a remediação
            if account_email in whitelist:
                logging.info(f"[AUTOREMEDIATION] Conta '{account_email}' possui redirecionamento externo permitido por whitelist. Pulando remediação.")
                continue

            logging.warning(f"[AUTOREMEDIATION] Anomalia detectada na conta não autorizada '{account_email}'!")

            # Passo A: Buscar usuário no AD por mail, userPrincipalName ou sAMAccountName para redefinição de senha
            user_search_filter = f"(|(mail={escape_filter_chars(account_email)})(userPrincipalName={escape_filter_chars(account_email)})(sAMAccountName={escape_filter_chars(account_email.split('@')[0])}))"
            
            try:
                conn.search(search_base, user_search_filter, attributes=['distinguishedName', 'sAMAccountName', 'displayName'])
                if not conn.entries:
                    logging.error(f"[AUTOREMEDIATION] Usuário '{account_email}' não foi encontrado no AD. Abortando remediação de segurança para este e-mail.")
                    continue

                ad_user = conn.entries[0]
                user_dn = ad_user.distinguishedName.value
                sam_username = ad_user.sAMAccountName.value
                ad_display_name = ad_user.displayName.value if ('displayName' in ad_user and ad_user.displayName.value) else None
            except Exception as e_ad_search:
                logging.error(f"[AUTOREMEDIATION] Erro ao buscar usuário '{account_email}' no AD: {e_ad_search}")
                continue

            # Passo B: Gerar nova senha segura e alterar no Active Directory
            try:
                security_pwd = config.get('ZIMBRA_SECURITY_DEFAULT_PASSWORD', '').strip()
                new_pwd = security_pwd if security_pwd else generate_secure_password()
            except Exception:
                new_pwd = generate_secure_password()

            logging.info(f"[AUTOREMEDIATION] Resetando senha para o usuário AD '{sam_username}' ({user_dn})...")
            try:
                import ldap3
                password_value = f'"{new_pwd}"'.encode('utf-16-le')
                conn.modify(user_dn, {'unicodePwd': [(ldap3.MODIFY_REPLACE, [password_value])]})
                if conn.result['description'] == 'success':
                    # Força a alteração de senha no próximo logon por segurança
                    conn.modify(user_dn, {'pwdLastSet': [(ldap3.MODIFY_REPLACE, [0])]})
                    logging.info(f"[AUTOREMEDIATION] Senha de '{sam_username}' alterada com sucesso no AD. Forçando alteração de senha no próximo logon.")
                else:
                    logging.error(f"[AUTOREMEDIATION] Falha ao resetar senha no AD para '{sam_username}': {conn.result['message']}")
                    continue
            except Exception as e_pwd:
                logging.error(f"[AUTOREMEDIATION] Exceção ao resetar senha de '{sam_username}' no AD: {e_pwd}")
                continue

            # Passo C: Desativar os recursos irregulares no Zimbra
            removed_attributes = []
            if unauthorized_forwardings:
                try:
                    # Remove os encaminhamentos externos mantendo os corporativos (se houver)
                    corporate_forwardings = [addr for addr in account.get('forwarding_addresses', []) if not is_external_email(addr)]
                    client.modify_account(account_id, {
                        'zimbraPrefMailForwardingAddress': corporate_forwardings
                    })
                    logging.info(f"[AUTOREMEDIATION] Encaminhamento externo de '{account_email}' foi removido com sucesso do Zimbra.")
                    removed_attributes.append(('Encaminhamento Externo', ', '.join(unauthorized_forwardings)))
                except Exception as e_rem:
                    logging.error(f"[AUTOREMEDIATION] Falha ao remover encaminhamento do Zimbra para '{account_email}': {e_rem}")

            if unauthorized_reply_to:
                try:
                    # Limpa o endereco, o texto de exibicao e desativa o "Responder para"
                    client.modify_account(account_id, {
                        'zimbraPrefReplyToAddress': '',
                        'zimbraPrefReplyToDisplay': '',
                        'zimbraPrefReplyToEnabled': 'FALSE'
                    })
                    logging.info(f"[AUTOREMEDIATION] Reply-To externo de '{account_email}' foi removido com sucesso do Zimbra.")
                    removed_attributes.append(('Reply-To Externo', unauthorized_reply_to))
                except Exception as e_rem:
                    logging.error(f"[AUTOREMEDIATION] Falha ao remover Reply-To do Zimbra para '{account_email}': {e_rem}")

            if unauthorized_notification:
                try:
                    # Limpa o endereco de notificacao e desativa a notificacao externa
                    client.modify_account(account_id, {
                        'zimbraPrefNewMailNotificationAddress': '',
                        'zimbraPrefNewMailNotificationEnabled': 'FALSE'
                    })
                    logging.info(f"[AUTOREMEDIATION] Notificação externa de '{account_email}' foi removido com sucesso do Zimbra.")
                    removed_attributes.append(('Notificação Externa', unauthorized_notification))
                except Exception as e_rem:
                    logging.error(f"[AUTOREMEDIATION] Falha ao remover Notificação do Zimbra para '{account_email}': {e_rem}")

            # Passo D: Corrigir o nome de exibição "De" (From) puxando o displayName do AD
            if ad_display_name:
                try:
                    client.modify_account(account_id, {'zimbraPrefFromDisplay': ad_display_name})
                    logging.info(f"[AUTOREMEDIATION] Nome 'De' (From) de '{account_email}' redefinido para o displayName do AD: '{ad_display_name}'.")
                    try:
                        save_to_history(
                            'SECURITY_REMEDIATION',
                            'scheduler',
                            f"Autoremediação: nome 'De' de {account_email} corrigido para o displayName do AD ('{ad_display_name}')."
                        )
                    except Exception as e_hist_from:
                        logging.error(f"[AUTOREMEDIATION] Erro ao gravar histórico da correção do nome 'De': {e_hist_from}")
                except Exception as e_from:
                    logging.error(f"[AUTOREMEDIATION] Falha ao corrigir o nome 'De' (From) de '{account_email}': {e_from}")
            else:
                logging.warning(f"[AUTOREMEDIATION] displayName do AD não disponível para '{account_email}'; nome 'De' não foi corrigido.")

            # Passo E: Registrar no histórico e enviar mensagens para o Teams
            for attr_label, dest_val in removed_attributes:
                try:
                    save_to_history(
                        'SECURITY_REMEDIATION',
                        'scheduler',
                        f"Autoremediação executada para {account_email}: removido {attr_label} apontando para {dest_val}. Senha AD alterada."
                    )
                except Exception as e_hist:
                    logging.error(f"[AUTOREMEDIATION] Erro ao gravar histórico: {e_hist}")

                try:
                    send_teams_security_alert(
                        config=config,
                        email=account_email,
                        anomaly_type=attr_label,
                        destination=dest_val,
                        new_password=new_pwd,
                        conn=conn
                    )
                except Exception as e_teams:
                    logging.error(f"[AUTOREMEDIATION] Erro ao disparar alerta Teams para {account_email}: {e_teams}")

        logging.info("Verificação de segurança (Autoremediação Zimbra) concluída.")
        config['ZIMBRA_LAST_AUDIT_TIMESTAMP'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        config['ZIMBRA_LAST_AUDIT_STATUS'] = 'Success'
        save_config(config)

    except Exception as e:
        logging.error(f"Erro inesperado durante a auditoria de segurança do Zimbra: {e}", exc_info=True)
        config['ZIMBRA_LAST_AUDIT_TIMESTAMP'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        config['ZIMBRA_LAST_AUDIT_STATUS'] = f'Failed: {str(e)}'
        save_config(config)
        raise e


def process_zimbra_from_display_correction(conn, config, dry_run=False):
    """
    Corrige o nome de exibicao "De" (zimbraPrefFromDisplay) das contas do Zimbra,
    alinhando ao displayName do usuario no AD. Roda de forma INDEPENDENTE das demais
    anomalias (encaminhamento/reply/notificacao).

    O displayName do AD e a AUTORIDADE (mandatario): sempre prevalece sobre o "De".

    Regras:
      - So corrige contas cujo "De" esta PREENCHIDO e difere do displayName do AD.
        (Se estiver vazio, o Zimbra ja usa o padrao da conta — nao mexe.)
      - Pula contas sem usuario correspondente no AD.
    """
    from routes.zimbra_api import ZimbraSOAPClient

    if not config.get('ZIMBRA_ENABLED', False):
        logging.info("[FROM-DISPLAY] Integracao Zimbra desativada. Pulando correcao de nome 'De'.")
        return 0

    search_base = config.get('AD_SEARCH_BASE')
    if not search_base:
        logging.error("[FROM-DISPLAY] AD_SEARCH_BASE nao definido. Abortando correcao de nome 'De'.")
        return 0

    # 1. Carrega displayName do AD (mail/UPN/sAMAccountName -> displayName)
    ad_by_mail, ad_by_sam = {}, {}
    try:
        for e in conn.extend.standard.paged_search(
                search_base=search_base, search_filter='(&(objectClass=user)(displayName=*))',
                attributes=['mail', 'userPrincipalName', 'sAMAccountName', 'displayName'],
                paged_size=500, generator=True):
            if e.get('type') != 'searchResEntry':
                continue
            a = e['attributes']
            disp = a.get('displayName')
            disp = (disp[0] if isinstance(disp, list) and disp else disp) if disp else None
            if not disp:
                continue
            for k in ('mail', 'userPrincipalName'):
                v = a.get(k)
                v = (v[0] if isinstance(v, list) and v else v) if v else None
                if v:
                    ad_by_mail[v.strip().lower()] = disp
            sam = a.get('sAMAccountName')
            sam = (sam[0] if isinstance(sam, list) and sam else sam) if sam else None
            if sam:
                ad_by_sam[sam.strip().lower()] = disp
    except Exception as e_ad:
        logging.error(f"[FROM-DISPLAY] Erro ao carregar usuarios do AD: {e_ad}")
        return 0

    # 2. Conecta no Zimbra
    zimbra_url = config.get('ZIMBRA_API_URL', '')
    zimbra_user = config.get('ZIMBRA_ADMIN_USER', '')
    zimbra_password = config.get('ZIMBRA_ADMIN_PASSWORD', '')
    if not zimbra_url or not zimbra_user:
        logging.error("[FROM-DISPLAY] API do Zimbra nao configurada. Abortando.")
        return 0
    client = ZimbraSOAPClient(zimbra_url, zimbra_user, zimbra_password)
    client.authenticate()

    ns = '{urn:zimbraAdmin}'
    SOAP_NS = '{http://www.w3.org/2003/05/soap-envelope}'

    # 3. Varre por dominio (evita o teto de 1000 resultados do SearchDirectory)
    try:
        domains = [d.get('name') for d in (client.get_domains() or []) if d.get('name')]
    except Exception as e_dom:
        logging.error(f"[FROM-DISPLAY] Erro ao listar dominios do Zimbra: {e_dom}")
        return 0

    analisadas = corrigidas = 0
    for dom in domains:
        try:
            body = (f'<SearchDirectoryRequest xmlns="urn:zimbraAdmin" types="accounts" '
                    f'limit="2000" domain="{dom}" attrs="zimbraPrefFromDisplay"></SearchDirectoryRequest>')
            root = client._send_soap_request(body, timeout=120)
            resp = root.find(f'{SOAP_NS}Body').find(f'{ns}SearchDirectoryResponse')
        except Exception as e_sd:
            logging.error(f"[FROM-DISPLAY] Erro ao buscar contas do dominio '{dom}': {e_sd}")
            continue
        for acc_el in resp.findall(f'{ns}account'):
            analisadas += 1
            email = (acc_el.attrib.get('name', '') or '').strip().lower()
            acc_id = acc_el.attrib.get('id')
            fd = None
            for a_el in acc_el.findall(f'{ns}a'):
                if a_el.attrib.get('n') == 'zimbraPrefFromDisplay':
                    fd = a_el.text
            cur = (fd or '').strip()
            if not cur or not acc_id:
                continue  # sem override -> Zimbra usa o padrao
            ad_disp = ad_by_mail.get(email) or ad_by_sam.get(email.split('@')[0])
            if not ad_disp:
                continue
            ad_disp = ad_disp.strip()
            if cur == ad_disp:
                continue
            if dry_run:
                logging.info(f"[FROM-DISPLAY][DRY-RUN] {email}: '{cur}' -> '{ad_disp}'")
                corrigidas += 1
                continue
            try:
                client.modify_account(acc_id, {'zimbraPrefFromDisplay': ad_disp})
                corrigidas += 1
                logging.info(f"[FROM-DISPLAY] {email}: nome 'De' corrigido de '{cur}' para '{ad_disp}'.")
                try:
                    save_to_history('SECURITY_REMEDIATION', 'scheduler',
                                    f"Correcao de nome 'De': {email} de '{cur}' para o displayName do AD ('{ad_disp}').")
                except Exception as e_h:
                    logging.error(f"[FROM-DISPLAY] Erro ao gravar historico para {email}: {e_h}")
            except Exception as e_mod:
                logging.error(f"[FROM-DISPLAY] Falha ao corrigir nome 'De' de {email}: {e_mod}")

    logging.info(f"[FROM-DISPLAY] Concluido. Analisadas={analisadas}, corrigidas={corrigidas}, dry_run={dry_run}.")
    return corrigidas


if __name__ == "__main__":
    logging.info("=============================================")
    logging.info("Iniciando Gerenciador de Agendamentos do AD.")
    try:
        from app import app
        with app.app_context():
            config = load_config()
            conn = get_ldap_connection()

            if conn:
                search_base = config.get('AD_SEARCH_BASE')
                if search_base:
                    process_user_deactivations(conn, search_base)
                    process_user_reactivations(conn, search_base)
                    process_group_membership_changes(conn, search_base)
                    # Sincronização de grupos do Zimbra
                    process_zimbra_group_syncs(conn, config)
                    # Autoremediação de segurança do Zimbra
                    process_zimbra_security_auto_remediation(conn, config)
                    # Correção do nome "De" (zimbraPrefFromDisplay) alinhado ao displayName do AD
                    process_zimbra_from_display_correction(conn, config)
                else:
                    logging.error("AD_SEARCH_BASE não definido. As operações de AD foram puladas.")
                conn.unbind()
            else:
                logging.error("Não foi possível conectar ao AD.")
    except Exception as e:
        logging.critical(f"Erro inesperado durante o processamento: {e}", exc_info=True)
    
    logging.info("Gerenciador de Agendamentos do AD finalizado.")
    logging.info("=============================================\n")

