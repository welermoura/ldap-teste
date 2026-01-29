# Análise do Erro de Migração (Alembic)

## Problema Identificado

Os logs fornecidos indicam um erro no serviço `inventory_backend` relacionado ao banco de dados `inventory_db` e à ferramenta de migração **Alembic**.

**Erro:**
```
ERROR [alembic.util.messaging] Multiple head revisions are present for given argument 'head'; please specify a specific target revision, '<branchname>@head' to narrow to a specific head, or 'heads' for all heads
```

## Diagnóstico

1.  **Mismatch de Repositório:** O código presente neste ambiente pertence ao projeto **AD Manager** (Gerenciador de Active Directory via LDAP). Não há arquivos relacionados a `inventory_backend`, PostgreSQL ou Alembic neste diretório.
2.  **Causa do Erro:** O erro "Multiple head revisions" ocorre quando dois ou mais arquivos de migração (scripts Python no diretório `versions` do Alembic) apontam para a mesma revisão pai (down_revision), criando uma bifurcação na história das migrações. Isso geralmente acontece quando dois desenvolvedores criam migrações simultaneamente ou durante merges de branches no Git.

## Solução

Como o código do `inventory_backend` não está aqui, você deve executar os seguintes passos no diretório ou container onde o `inventory_backend` está rodando:

### Opção 1: Mesclar as Revisões (Recomendado)

O Alembic pode criar automaticamente um novo arquivo de migração que mescla os dois "heads" (cabeças).

1.  Acesse o shell do container ou o ambiente onde o Alembic está instalado:
    ```bash
    docker-compose exec inventory_backend bash
    # ou, se estiver rodando localmente com venv
    source venv/bin/activate
    ```

2.  Execute o comando de merge:
    ```bash
    alembic merge heads -m "merge revisions"
    ```

3.  Aplique a migração:
    ```bash
    alembic upgrade head
    ```

### Opção 2: Correção Manual

1.  Identifique os dois arquivos de migração conflitantes na pasta `versions`.
2.  Edite um deles e altere o campo `down_revision` para apontar para o ID de revisão do outro arquivo, criando uma sequência linear.
