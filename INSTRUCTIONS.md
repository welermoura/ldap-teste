# Instruções para Execução com Docker

Este guia explica como executar a aplicação de gerenciamento de AD usando Docker e Docker Compose.

## Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/) (geralmente incluído com o Docker Desktop)

## Como Executar

1. **Construir e Iniciar os Contêineres:**
   Navegue até o diretório raiz do projeto (onde o arquivo `docker-compose.yml` está localizado) e execute o seguinte comando:

   ```bash
   docker-compose up --build
   ```

   - O comando `--build` força a reconstrução da imagem a partir do `Dockerfile`, garantindo que quaisquer alterações no código sejam incluídas.
   - Este comando iniciará **dois serviços**: `web` (a aplicação Flask) e `scheduler` (o agendador de tarefas cron). Você verá os logs de ambos os serviços no seu terminal.
   - Na primeira vez, o processo pode levar alguns minutos. As execuções subsequentes serão muito mais rápidas.
   - A aplicação web estará acessível em `http://localhost:5000` no seu navegador.

2. **Parar a Aplicação:**
   Para parar ambos os contêineres, pressione `Ctrl + C` no terminal onde o `docker-compose` está rodando. Para garantir que os contêineres sejam parados e removidos, você pode executar:

   ```bash
   docker-compose down
   ```

## Persistência de Dados e Logs

**Seus dados estão seguros!** Graças à configuração no `docker-compose.yml`, os diretórios `data/` e `logs/` da sua máquina local são espelhados para dentro de ambos os contêineres.

- **Histórico da Aplicação:** Todo o histórico (configurações, agendamentos, usuários admin, etc.) no diretório `data/` não será perdido quando você parar ou reconstruir os contêineres.
- **Logs do Agendador:** A saída do script agendado (`schedule_manager.py`) será salva no arquivo `logs/cron.log` na sua máquina local, facilitando a verificação e depuração.
