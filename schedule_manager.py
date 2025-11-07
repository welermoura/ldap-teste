#!/usr/bin/env python3
import os
import json
from datetime import date
import logging
from ldap3 import MODIFY_REPLACE
from common import load_config, get_ldap_connection, get_user_by_samaccountname, get_group_by_name, SCHEDULE_FILE, DISABLE_SCHEDULE_FILE, GROUP_SCHEDULE_FILE
import json
import os
# ==============================================================================
# Configuração Base
# ==============================================================================
basedir = os.path.abspath(os.path.dirname(__file__))
logs_dir = os.path.join(basedir, 'logs')
os.makedirs(logs_dir, exist_ok=True)

log_path = os.path.join(logs_dir, 'schedule_manager.log') # Nome do log atualizado
logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

# ==============================================================================
# Lógica Principal do Script
# ==============================================================================
def process_user_deactivations(conn, search_base):
    """Processa a desativação agendada de contas de usuário."""
    logging.info("Iniciando verificação de desativações de usuários.")
    try:
        with open(DISABLE_SCHEDULE_FILE, 'r') as f:
            schedules = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logging.info("Nenhum arquivo de agendamento de desativação ('disable_schedules.json') encontrado.")
        return

    today = date.today().isoformat()
    schedules_to_keep = {}
    for username, deactivation_date in schedules.items():
        if deactivation_date <= today:
            logging.info(f"Tentando desativar o usuário '{username}' agendado para {deactivation_date}.")
            user = get_user_by_samaccountname(conn, username, search_base)
            if user:
                uac = user.userAccountControl.value
                if not (uac & 2): # Se a conta NÃO estiver desativada
                    new_uac = uac | 2 # Adiciona a flag de desativação
                    conn.modify(user.distinguishedName.value, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(new_uac)])]})
                    if conn.result['description'] == 'success':
                        logging.info(f"Usuário '{username}' desativado com sucesso.")
                    else:
                        logging.error(f"Falha ao desativar '{username}': {conn.result['message']}. Mantendo agendamento.")
                        schedules_to_keep[username] = deactivation_date
                else:
                    logging.warning(f"Usuário '{username}' já estava desativado. Removendo agendamento de desativação.")
            else:
                logging.warning(f"Usuário '{username}' agendado para desativação não encontrado. Removendo agendamento.")
        else:
            schedules_to_keep[username] = deactivation_date

    with open(DISABLE_SCHEDULE_FILE, 'w') as f:
        json.dump(schedules_to_keep, f, indent=4)
    logging.info("Verificação de desativações de usuários concluída.")


def process_user_reactivations(conn, search_base):
    """Processa a reativação de contas de usuário."""
    logging.info("Iniciando verificação de reativações de usuários.")
    try:
        with open(SCHEDULE_FILE, 'r') as f:
            schedules = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logging.info("Nenhum arquivo de agendamento de reativação ('schedules.json') encontrado.")
        return

    today = date.today().isoformat()
    schedules_to_keep = {}
    for username, reactivation_date in schedules.items():
        if reactivation_date <= today:
            logging.info(f"Tentando reativar o usuário '{username}' agendado para {reactivation_date}.")
            user = get_user_by_samaccountname(conn, username, search_base)
            if user:
                uac = user.userAccountControl.value
                if uac & 2:  # Se a conta estiver desativada
                    new_uac = uac - 2
                    conn.modify(user.distinguishedName.value, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(new_uac)])]})
                    if conn.result['description'] == 'success':
                        logging.info(f"Usuário '{username}' reativado com sucesso.")
                    else:
                        logging.error(f"Falha ao reativar '{username}': {conn.result['message']}. Mantendo agendamento.")
                        schedules_to_keep[username] = reactivation_date
                else:
                    logging.warning(f"Usuário '{username}' já estava ativo. Removendo agendamento de reativação.")
            else:
                logging.warning(f"Usuário '{username}' agendado para reativação não encontrado. Removendo agendamento.")
        else:
            schedules_to_keep[username] = reactivation_date

    with open(SCHEDULE_FILE, 'w') as f:
        json.dump(schedules_to_keep, f, indent=4)
    logging.info("Verificação de reativações de usuários concluída.")

def process_group_membership_changes(conn, search_base):
    """Processa as alterações agendadas de associação a grupos."""
    logging.info("Iniciando verificação de alterações de associação a grupos.")
    try:
        with open(GROUP_SCHEDULE_FILE, 'r') as f:
            schedules = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logging.info("Nenhum arquivo de agendamento de grupos ('group_schedules.json') encontrado.")
        return

    today = date.today().isoformat()
    remaining_schedules = []
    for schedule in schedules:
        # Suporta tanto o formato antigo ('revert_date') quanto o novo ('execution_date') para retrocompatibilidade.
        execution_date = schedule.get('execution_date') or schedule.get('revert_date')

        if execution_date and execution_date <= today:
            # Suporta o nome de ação antigo ('revert_action') e o novo ('action').
            action = schedule.get('action') or schedule.get('revert_action')
            user_sam = schedule.get('user_sam')
            group_name = schedule.get('group_name')

            if not all([user_sam, group_name, action]):
                 logging.warning(f"Agendamento malformado encontrado e ignorado: {schedule}")
                 continue

            logging.info(f"Processando agendamento: {action} '{user_sam}' no grupo '{group_name}' para data '{execution_date}'.")

            user = get_user_by_samaccountname(conn, user_sam, search_base)
            group = get_group_by_name(conn, group_name, search_base)

            if not user or not group:
                logging.warning(f"Usuário '{user_sam}' ou grupo '{group_name}' não encontrado. Removendo agendamento.")
                continue

            try:
                if action == 'add':
                    conn.extend.microsoft.add_members_to_groups([user.distinguishedName.value], group.distinguishedName.value)
                elif action == 'remove':
                    conn.extend.microsoft.remove_members_from_groups([user.distinguishedName.value], group.distinguishedName.value)

                if conn.result['description'] == 'success':
                    logging.info(f"Sucesso ao executar a ação '{action}' para o usuário '{user_sam}' no grupo '{group_name}'.")
                else:
                    logging.error(f"Falha ao executar a ação '{action}' para '{user_sam}': {conn.result['message']}. O agendamento será mantido para nova tentativa.")
                    remaining_schedules.append(schedule)
            except Exception as e:
                logging.error(f"Exceção ao processar agendamento para '{user_sam}' no grupo '{group_name}': {e}. O agendamento será mantido.")
                remaining_schedules.append(schedule)
        else:
            remaining_schedules.append(schedule)

    with open(GROUP_SCHEDULE_FILE, 'w') as f:
        json.dump(remaining_schedules, f, indent=4)
    logging.info("Verificação de alterações de associação a grupos concluída.")


if __name__ == "__main__":
    logging.info("=============================================")
    logging.info("Iniciando Gerenciador de Agendamentos do AD.")
    config = load_config()
    conn = get_ldap_connection()

    if conn:
        search_base = config.get('AD_SEARCH_BASE')
        if search_base:
            try:
                process_user_deactivations(conn, search_base)
                process_user_reactivations(conn, search_base)
                process_group_membership_changes(conn, search_base)
            except Exception as e:
                logging.critical(f"Erro inesperado durante o processamento de agendamentos: {e}", exc_info=True)
            finally:
                conn.unbind()
                logging.info("Conexão com o AD encerrada.")
        else:
            logging.error("AD_SEARCH_BASE não definido. As operações de AD foram puladas.")
    else:
        logging.error("Não foi possível conectar ao AD. As operações de AD foram puladas.")
        logging.info("Conexão com o AD encerrada.")
        logging.info("Gerenciador de Agendamentos do AD finalizado.")
        logging.info("=============================================\n")