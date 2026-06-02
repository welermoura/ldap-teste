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

    basedir = os.path.abspath(os.path.dirname(__file__))
    zimbra_mappings_file = os.path.join(basedir, 'data', 'zimbra_mappings.json')
    
    if not os.path.exists(zimbra_mappings_file):
        logging.info("Nenhum arquivo de mapeamentos do Zimbra encontrado. Pulando sincronização.")
        return

    try:
        with open(zimbra_mappings_file, 'r', encoding='utf-8') as f:
            mappings = json.load(f)
    except Exception as e:
        logging.error(f"Erro ao ler o arquivo de mapeamentos do Zimbra: {e}")
        return

    if not mappings:
        logging.info("Nenhum mapeamento de grupo do Zimbra ativo.")
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
        ad_group = mapping.get('ad_group_name', '').strip()
        zimbra_email = mapping.get('zimbra_dl_email', '').strip()
        
        if not ad_group or not zimbra_email:
            continue
            
        logging.info(f"Sincronizando grupo AD '{ad_group}' com lista Zimbra '{zimbra_email}'...")
        try:
            ad_group_obj = get_group_by_name(conn, ad_group, ['member'])
            if not ad_group_obj:
                logging.error(f"Grupo do AD '{ad_group}' não foi encontrado para sincronização.")
                continue

            # Extrai e-mails dos membros do AD
            ad_member_dns = ad_group_obj.member.values if 'member' in ad_group_obj and ad_group_obj.member.values else []
            ad_emails = set()
            
            for dn in ad_member_dns:
                user_entry = get_user_by_dn(conn, dn, ['mail', 'userPrincipalName'])
                if user_entry:
                    email = get_attr_value(user_entry, 'mail') or get_attr_value(user_entry, 'userPrincipalName')
                    if email:
                        ad_emails.add(email.strip().lower())

            # Conecta no Zimbra
            try:
                dl_info = client.get_dl_members(zimbra_email)
            except Exception as e:
                if "NO_SUCH_DISTRIBUTION_LIST" in str(e):
                    logging.info(f"Lista '{zimbra_email}' não existe no Zimbra. Tentando criar automaticamente...")
                    try:
                        client.create_dl(zimbra_email)
                        dl_info = client.get_dl_members(zimbra_email)
                    except Exception as e_create:
                        logging.error(f"Erro ao criar lista '{zimbra_email}' no Zimbra: {e_create}")
                        continue
                else:
                    logging.error(f"Erro ao buscar membros da lista Zimbra '{zimbra_email}': {e}")
                    continue

            zimbra_emails = set(dl_info['members'])
            zimbra_real_email = dl_info['email']

            # Diferenças
            to_add = ad_emails - zimbra_emails
            to_remove = zimbra_emails - ad_emails

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
                else:
                    logging.error("AD_SEARCH_BASE não definido. As operações de AD foram puladas.")
                conn.unbind()
            else:
                logging.error("Não foi possível conectar ao AD.")
    except Exception as e:
        logging.critical(f"Erro inesperado durante o processamento: {e}", exc_info=True)
    
    logging.info("Gerenciador de Agendamentos do AD finalizado.")
    logging.info("=============================================\n")

