# Instruções para Execução com Docker

Este guia explica como executar a aplicação de gerenciamento de AD usando Docker e Docker Compose.

## Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/) (geralmente incluído com o Docker Desktop)

## Como Executar

1. **Construir e Iniciar o Contêiner:**
   Navegue até o diretório raiz do projeto (onde o arquivo `docker-compose.yml` está localizado) e execute o seguinte comando:

   ```bash
   docker-compose up --build
   ```

   - O comando `--build` força a reconstrução da imagem a partir do `Dockerfile`, garantindo que quaisquer alterações no código sejam incluídas.
   - Na primeira vez, o Docker fará o download da imagem base e instalará todas as dependências, o que pode levar alguns minutos. As execuções subsequentes serão muito mais rápidas.
   - A aplicação estará acessível em `http://localhost:5000` no seu navegador.

2. **Parar a Aplicação:**
   Para parar o contêiner, pressione `Ctrl + C` no terminal onde o `docker-compose` está rodando. Para garantir que o contêiner seja parado e removido, você pode executar:

   ```bash
   docker-compose down
   ```

## Persistência de Dados

**Seus dados estão seguros!** Graças à configuração no `docker-compose.yml`, os diretórios `data/` e `logs/` da sua máquina local são espelhados para dentro do contêiner.

Isso significa que todo o histórico da aplicação (configurações, agendamentos, usuários admin, etc.) **não será perdido** quando você parar ou reconstruir o contêiner.
