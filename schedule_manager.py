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


if __name__ == "__main__":
    logging.info("=============================================")
    logging.info("Iniciando Gerenciador de Agendamentos do AD.")
    try:
        config = load_config()
        conn = get_ldap_connection()

        if conn:
            search_base = config.get('AD_SEARCH_BASE')
            if search_base:
                process_user_deactivations(conn, search_base)
                process_user_reactivations(conn, search_base)
                process_group_membership_changes(conn, search_base)
            else:
                logging.error("AD_SEARCH_BASE não definido. As operações de AD foram puladas.")
            conn.unbind()
        else:
            logging.error("Não foi possível conectar ao AD.")
    except Exception as e:
        logging.critical(f"Erro inesperado durante o processamento: {e}", exc_info=True)
    
    logging.info("Gerenciador de Agendamentos do AD finalizado.")
    logging.info("=============================================\n")
