# CRUD com Excel em Python

Aplicacao desktop em Python com Tkinter e Excel para cadastro de clientes, produtos e vendas.

## Requisitos

- Python 3
- Dependencias do `requirements.txt`

## Instalar dependencias

```powershell
python -m pip install -r requirements.txt
```

## Executar desktop

```powershell
python .\excel_crud.py
```

## Executar web

```powershell
python .\web_app.py
```

Depois abra `http://127.0.0.1:5000`.

## Pronto para deploy

O projeto agora inclui:

- `wsgi.py` para servidor WSGI
- `Procfile` para plataformas que usam comando de processo
- `render.yaml` com configuracao inicial para Render
- suporte a `PORT`, `FLASK_ENV`, `WEB_APP_DATA_DIR` e `WEB_APP_DB_PATH`
- endpoint de health check em `/health`

## Configuracao opcional

Voce pode criar um `config.json` na pasta do projeto usando o modelo `config.example.json`.

Tambem e possivel sobrescrever os valores por variaveis de ambiente:

- `ORQ_ADMIN_EMAIL`
- `ORQ_ADMIN_PASSWORD`
- `ORQ_PIX_KEY`
- `ORQ_WEB_SECRET_KEY`
- `WEB_APP_DATA_DIR`
- `WEB_APP_DB_PATH`

## Funcionalidades

- CRUD de clientes
- CRUD de produtos
- Carrinho e finalizacao de compras
- Registro de vendas em planilha
- Login de administrador
- Login e cadastro rapido de clientes
- Versao web inicial com Flask e SQLite

## Arquivos de dados

- `clientes.xlsx`: base local com clientes, produtos e vendas
- `config.json`: configuracao local de credenciais e chave PIX
- `web_app.db`: banco SQLite usado pela versao web

## Observacoes da versao web

- Na primeira execucao, a versao web tenta importar clientes e produtos do `clientes.xlsx`
- Clientes importados do Excel entram com senha inicial igual ao CPF numerico
- O login web do cliente usa `CPF + senha`
- Em hospedagem, use disco persistente para o SQLite se quiser manter os dados

## Exemplo de deploy no Render

1. Suba esse projeto para o GitHub.
2. No Render, crie um novo `Web Service` apontando para o repositorio.
3. Se quiser, use o `render.yaml` do projeto.
4. Configure as variaveis `ORQ_ADMIN_EMAIL`, `ORQ_ADMIN_PASSWORD`, `ORQ_PIX_KEY` e `ORQ_WEB_SECRET_KEY`.
5. Adicione um disco persistente e monte em `/var/data`.
6. Publique o servico.
