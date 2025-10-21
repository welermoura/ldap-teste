#!/usr/bin/env python3
import os
import json
from datetime import date
import logging
from ldap3 import MODIFY_REPLACE
from common import load_config, get_ldap_connection, get_user_by_samaccountname, get_group_by_name, SCHEDULE_FILE, GROUP_SCHEDULE_FILE
import json
import os
# ==============================================================================
# Configuração Base
# ==============================================================================
basedir = os.path.abspath(os.path.dirname(__file__))
logs_dir = os.path.join(basedir, 'logs')
os.makedirs(logs_dir, exist_ok=True)

# Configuração do Logging
log_path = os.path.join(logs_dir, 'reactivator.log')
logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

# ==============================================================================
# Lógica Principal do Script
# ==============================================================================
def process_user_reactivations(conn, search_base):
    """Processa a reativação de contas de usuário de forma robusta."""
    logging.info("Iniciando verificação de reativações de usuários.")
    try:
        with open(SCHEDULE_FILE, 'r') as f:
            schedules = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logging.info("Nenhum arquivo de agendamento de usuários ('schedules.json') encontrado ou está vazio. Pulando.")
        return

    today = date.today().isoformat()
    schedules_to_keep = {}

    for username, reactivation_date in schedules.items():
        if reactivation_date <= today:
            logging.info(f"Tentando reativar o usuário '{username}' agendado para {reactivation_date}.")
            user = get_user_by_samaccountname(conn, username, search_base)
            if user:
                uac = user.userAccountControl.value
                if uac & 2:  # Se a conta estiver desativada (flag 2)
                    new_uac = uac - 2
                    conn.modify(user.distinguishedName.value, {'userAccountControl': [(ldap3.MODIFY_REPLACE, [str(new_uac)])]})
                    if conn.result['description'] == 'success':
                        logging.info(f"Usuário '{username}' reativado com sucesso. Agendamento removido.")
                    else:
                        logging.error(f"Falha ao reativar '{username}': {conn.result['message']}. Mantendo agendamento para próxima execução.")
                        schedules_to_keep[username] = reactivation_date  # Mantém o agendamento se a reativação falhar
                else:
                    logging.warning(f"Usuário '{username}' já estava ativo. Removendo agendamento.")
            else:
                logging.warning(f"Usuário '{username}' agendado para reativação não foi encontrado no AD. Removendo agendamento.")
        else:
            # A data de reativação é no futuro, então mantém o agendamento.
            schedules_to_keep[username] = reactivation_date

    with open(SCHEDULE_FILE, 'w') as f:
        json.dump(schedules_to_keep, f, indent=4)
    logging.info("Verificação de reativações de usuários concluída.")

def process_group_membership_changes(conn, search_base):
    """Processa as alterações agendadas de associação a grupos de forma robusta."""
    logging.info("Iniciando verificação de alterações de associação a grupos.")
    try:
        with open(GROUP_SCHEDULE_FILE, 'r') as f:
            schedules = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logging.info("Nenhum arquivo de agendamento de grupos ('group_schedules.json') encontrado ou está vazio. Pulando.")
        return

    today = date.today().isoformat()
    remaining_schedules = []

    for schedule in schedules:
        if schedule['revert_date'] <= today:
            user_sam = schedule['user_sam']
            group_name = schedule['group_name']
            action = schedule['revert_action']

            logging.info(f"Processando agendamento para '{user_sam}' no grupo '{group_name}'. Ação: {action}.")

            user = get_user_by_samaccountname(conn, user_sam, search_base)
            group = get_group_by_name(conn, group_name, search_base)

            if not user or not group:
                logging.warning(f"Usuário '{user_sam}' ou grupo '{group_name}' não encontrado. Removendo agendamento inválido.")
                continue

            try:
                if action == 'add':
                    conn.extend.microsoft.add_members_to_groups([user.distinguishedName.value], group.distinguishedName.value)
                elif action == 'remove':
                    conn.extend.microsoft.remove_members_from_groups([user.distinguishedName.value], group.distinguishedName.value)
                else:
                    logging.warning(f"Ação desconhecida '{action}' para o agendamento. Ignorando.")
                    continue

                if conn.result['description'] == 'success':
                    logging.info(f"Sucesso: Usuário '{user_sam}' foi '{'adicionado a' if action == 'add' else 'removido de'}' '{group_name}'. Agendamento concluído.")
                else:
                    logging.error(f"Falha ao executar ação '{action}' para '{user_sam}' em '{group_name}': {conn.result['message']}. Mantendo agendamento.")
                    remaining_schedules.append(schedule)
            except Exception as e:
                logging.error(f"Erro de exceção ao processar agendamento para '{user_sam}' em '{group_name}': {e}. Mantendo agendamento.")
                remaining_schedules.append(schedule)
        else:
            remaining_schedules.append(schedule)

    with open(GROUP_SCHEDULE_FILE, 'w') as f:
        json.dump(remaining_schedules, f, indent=4)
    logging.info("Verificação de alterações de associação a grupos concluída.")


if __name__ == "__main__":
    logging.info("=============================================")
    logging.info("Iniciando script de tarefas agendadas do AD.")

    config = load_config()
    if not config:
        logging.critical("Configuração não carregada. Abortando.")
        exit(1)

    conn = get_ldap_connection()
    if not conn:
        logging.critical("Não foi possível estabelecer conexão com o AD. Abortando.")
        exit(1)

    search_base = config.get('AD_SEARCH_BASE')
    if not search_base:
        logging.critical("AD_SEARCH_BASE não definido na configuração. Abortando.")
        exit(1)

    try:
        process_user_reactivations(conn, search_base)
        process_group_membership_changes(conn, search_base)
    except Exception as e:
        logging.critical(f"Ocorreu um erro inesperado durante a execução do script: {e}", exc_info=True)
    finally:
        conn.unbind()
        logging.info("Conexão com o AD encerrada.")
        logging.info("Script de tarefas agendadas do AD finalizado.")
        logging.info("=============================================\n")