# Flask + Pix Automatico com PagBank

Projeto Flask com fluxo de pedido estilo e-commerce, geracao automatica de cobranca Pix no PagBank, webhook de confirmacao e atualizacao da tela em tempo real.

## O que o sistema faz

- Cria pedidos no SQLite com valor e status
- Gera cobranca Pix pelo endpoint `POST /criar_pix`
- Retorna codigo Pix copia e cola, QR Code em base64 e identificador da cobranca
- Recebe notificacoes no endpoint `POST /webhook`
- Consulta o pedido no PagBank e atualiza o pedido para `pago`
- Mostra o QR Code na pagina do pedido e acompanha o status com JavaScript
- Envia email automatico quando o pagamento for aprovado se SMTP estiver configurado

## Instalar dependencias

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configuracao do PagBank

1. Copie `config.example.json` para `config.json`.
2. Abra `config.json`.
3. Cole seu token em `pagbank_token`.
4. Se for validar a autenticidade do webhook, preencha `pagbank_webhook_token`.
5. Defina uma URL publica em `pagbank_notification_url` ou configure `loja_base_url`.
6. Ajuste `pagbank_api_base`:
   - Sandbox: `https://sandbox.api.pagseguro.com`
   - Producao: `https://api.pagseguro.com`

Exemplo:

```json
{
  "pagbank_token": "SEU_TOKEN_PAGBANK",
  "pagbank_webhook_token": "seu-token-do-webhook",
  "pagbank_notification_url": "https://SEU-ENDERECO/webhook",
  "pagbank_api_base": "https://sandbox.api.pagseguro.com",
  "loja_base_url": "https://SEU-ENDERECO"
}
```

Voce tambem pode usar variaveis de ambiente:

- `PAGBANK_TOKEN`
- `PAGBANK_WEBHOOK_TOKEN`
- `PAGBANK_NOTIFICATION_URL`
- `PAGBANK_API_BASE`
- `APP_BASE_URL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `SMTP_SENDER`
- `SMTP_USE_TLS`

## Como rodar

```powershell
python .\web_app.py
```

Abra `http://127.0.0.1:5000`.

## Fluxo de uso

1. Entre como cliente ou crie um cadastro.
2. Adicione produtos ao carrinho.
3. Clique em `Finalizar compra`.
4. Na pagina do pedido, clique em `Pagar com Pix`.
5. O sistema chama `POST /criar_pix`, cria um `order` no PagBank e mostra o QR Code.
6. A tela entra em modo `Aguardando pagamento...`.
7. Quando o PagBank enviar o webhook e a cobranca ficar com status `PAID`, o pedido muda para `pago`.

## Endpoints principais

### `POST /criar_pix`

Body JSON de exemplo:

```json
{
  "pedido_id": 1,
  "valor": 150.0
}
```

Resposta de exemplo:

```json
{
  "pedido_id": 1,
  "payment_id": "CHAR_123",
  "status": "WAITING",
  "qr_code": "00020126...",
  "qr_code_base64": "iVBORw0KGgoAAA...",
  "ticket_url": "https://sandbox.api.pagseguro.com/qrcode/QRCO_123/png"
}
```

### `POST /webhook`

Recebe a notificacao do PagBank, consulta o pedido por `id` e atualiza o pedido:

- `pendente` enquanto a cobranca estiver aguardando pagamento
- `pago` quando o status da cobranca no PagBank virar `PAID`

## Como testar

1. Gere um token no painel do PagBank Developers.
2. Configure `pagbank_api_base` com sandbox ou producao.
3. Rode a aplicacao localmente.
4. Exponha sua URL local com uma ferramenta como `ngrok`.
5. Configure no `config.json`:
   - `pagbank_notification_url`: `https://abc123.ngrok-free.app/webhook`
   - `loja_base_url`: `https://abc123.ngrok-free.app`
6. Gere um pedido e clique em `Pagar com Pix`.
7. Faça o pagamento e verifique se o webhook chegou e se o pedido mudou para `pago`.

Observacoes importantes:

- O cliente precisa ter CPF cadastrado para gerar Pix no PagBank.
- O webhook precisa de uma URL publica real.
- Se voce configurar `pagbank_webhook_token`, o app valida o header `x-authenticity-token`.

## Email automatico

O envio de email e opcional. Para ativar, preencha no `config.json`:

```json
{
  "smtp_host": "smtp.seuprovedor.com",
  "smtp_port": "587",
  "smtp_user": "usuario",
  "smtp_password": "senha",
  "smtp_sender": "loja@seudominio.com",
  "smtp_use_tls": "true"
}
```

## Estrutura usada no banco

- `sales`: pedido simples com valor e status
- `sale_items`: itens do pedido
- `pix_payments`: dados do pagamento Pix e ids do PagBank

## Arquivos principais

- `web_app.py`: backend Flask, integracao HTTP com PagBank, webhook e email
- `templates/pedido_confirmado.html`: botao Pix, QR Code e polling de status
- `templates/carrinho.html`: resumo do checkout
- `config.example.json`: modelo de configuracao
