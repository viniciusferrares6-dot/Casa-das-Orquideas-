from __future__ import annotations

from datetime import datetime
from functools import wraps
from pathlib import Path
import json
import os
import re
import sqlite3

from flask import Flask, flash, g, redirect, render_template, request, send_from_directory, session, url_for
from openpyxl import load_workbook
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("WEB_APP_DATA_DIR", BASE_DIR))
DB_PATH = Path(os.getenv("WEB_APP_DB_PATH", DATA_DIR / "web_app.db"))
EXCEL_PATH = BASE_DIR / "clientes.xlsx"
CONFIG_PATH = BASE_DIR / "config.json"
EXTENSOES_IMAGEM = [".png", ".jpg", ".jpeg", ".webp"]


def carregar_configuracoes():
    configuracoes = {
        "admin_email": "admin@orquideas.local",
        "admin_password": "1234",
        "pix_key": "pix@orquideas.local",
        "secret_key": "orquideas-web-dev",
    }
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as arquivo:
                conteudo = json.load(arquivo)
            if isinstance(conteudo, dict):
                configuracoes.update({chave: str(valor) for chave, valor in conteudo.items() if valor})
        except (OSError, json.JSONDecodeError):
            pass
    configuracoes["admin_email"] = os.getenv("ORQ_ADMIN_EMAIL", configuracoes["admin_email"]).strip()
    configuracoes["admin_password"] = os.getenv("ORQ_ADMIN_PASSWORD", configuracoes["admin_password"])
    configuracoes["pix_key"] = os.getenv("ORQ_PIX_KEY", configuracoes["pix_key"]).strip()
    configuracoes["secret_key"] = os.getenv("ORQ_WEB_SECRET_KEY", configuracoes["secret_key"])
    return configuracoes


CONFIG = carregar_configuracoes()
app = Flask(__name__)
app.config["SECRET_KEY"] = CONFIG["secret_key"]
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def preparar_armazenamento():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def normalizar_cpf(cpf):
    return re.sub(r"\D", "", str(cpf or ""))


def encontrar_imagem_produto(nome_produto):
    for extensao in EXTENSOES_IMAGEM:
        caminho = BASE_DIR / f"{nome_produto}{extensao}"
        if caminho.exists():
            return caminho.name
    return None


def garantir_imagens_produtos(db):
    produtos_sem_imagem = db.execute("SELECT id, name FROM products WHERE image_path IS NULL OR image_path = ''").fetchall()
    houve_atualizacao = False
    for produto in produtos_sem_imagem:
        imagem = encontrar_imagem_produto(produto["name"])
        if not imagem:
            continue
        db.execute("UPDATE products SET image_path = ? WHERE id = ?", (imagem, produto["id"]))
        houve_atualizacao = True
    if houve_atualizacao:
        db.commit()


def garantir_produto_catalogo(db):
    produto = db.execute("SELECT id FROM products WHERE LOWER(name) = LOWER(?)", ("Cattleya hibrida",)).fetchone()
    if produto:
        db.execute(
            """
            UPDATE products
            SET category = ?, price = ?, stock = ?, status = ?, image_path = ?
            WHERE id = ?
            """,
            ("Orquidea", 80.0, 6, "Disponivel", "cattleya.site.jpeg", produto["id"]),
        )
    else:
        db.execute(
            """
            INSERT INTO products (name, category, price, stock, status, image_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Cattleya hibrida",
                "Orquidea",
                80.0,
                6,
                "Disponivel",
                "cattleya.site.jpeg",
                datetime.now().strftime("%d/%m/%Y %H:%M"),
            ),
        )
    db.commit()


def init_db():
    preparar_armazenamento()
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            cpf TEXT NOT NULL UNIQUE,
            email TEXT,
            phone TEXT,
            city TEXT,
            state TEXT,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            price REAL NOT NULL,
            stock INTEGER NOT NULL,
            status TEXT NOT NULL,
            image_path TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            client_name TEXT NOT NULL,
            total REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            total_price REAL NOT NULL
        );
        """
    )
    db.commit()
    importar_do_excel_se_necessario(db)
    garantir_produto_catalogo(db)
    garantir_imagens_produtos(db)


def importar_do_excel_se_necessario(db):
    if not EXCEL_PATH.exists():
        return
    clientes = db.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    produtos = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if clientes or produtos:
        return

    workbook = load_workbook(EXCEL_PATH, data_only=True)
    try:
        if "clientes" in workbook.sheetnames:
            worksheet = workbook["clientes"]
            for linha in worksheet.iter_rows(min_row=2, values_only=True):
                if not linha or linha[0] is None:
                    continue
                nome = str(linha[1] or "").strip()
                cpf = normalizar_cpf(linha[2])
                if not nome or not cpf:
                    continue
                db.execute(
                    """
                    INSERT OR IGNORE INTO clients (name, cpf, email, phone, city, state, password_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        nome,
                        cpf,
                        str(linha[3] or "").strip(),
                        str(linha[4] or "").strip(),
                        str(linha[6] or "").strip(),
                        str(linha[7] or "").strip().upper(),
                        generate_password_hash(cpf),
                        str(linha[9] or datetime.now().strftime("%d/%m/%Y %H:%M")),
                    ),
                )
        if "produtos" in workbook.sheetnames:
            worksheet = workbook["produtos"]
            for linha in worksheet.iter_rows(min_row=2, values_only=True):
                if not linha or linha[0] is None:
                    continue
                nome = str(linha[1] or "").strip()
                if not nome:
                    continue
                db.execute(
                    """
                    INSERT INTO products (name, category, price, stock, status, image_path, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        nome,
                        str(linha[2] or "").strip(),
                        float(linha[3] or 0),
                        int(float(linha[4] or 0)),
                        str(linha[5] or "Disponivel").strip(),
                        encontrar_imagem_produto(nome),
                        str(linha[6] or datetime.now().strftime("%d/%m/%Y %H:%M")),
                    ),
                )
    finally:
        workbook.close()
    db.commit()


@app.before_request
def before_request():
    init_db()


@app.context_processor
def inject_globals():
    return {
        "admin_logado": session.get("admin_logged_in", False),
        "cliente_logado": session.get("client_name"),
    }


def admin_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if not session.get("admin_logged_in"):
            flash("Entre como administrador para acessar essa area.", "warning")
            return redirect(url_for("admin_login"))
        return view(**kwargs)

    return wrapped_view


def client_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if not session.get("client_id"):
            flash("Entre como cliente para continuar.", "warning")
            return redirect(url_for("cliente_login", next=request.full_path.rstrip("?")))
        return view(**kwargs)

    return wrapped_view


def carrinho_atual():
    cart = session.setdefault("cart", [])
    cart_normalizado = []
    houve_ajuste = False

    for item in cart:
        try:
            product_id = int(item.get("product_id"))
            nome = str(item.get("name", "")).strip()
            unit_price = float(item.get("unit_price", 0))
            quantidade = int(item.get("quantity", 0))
        except (AttributeError, TypeError, ValueError):
            houve_ajuste = True
            continue

        if product_id <= 0 or not nome or unit_price < 0 or quantidade <= 0:
            houve_ajuste = True
            continue

        cart_normalizado.append(
            {
                "product_id": product_id,
                "name": nome,
                "unit_price": unit_price,
                "quantity": quantidade,
            }
        )

        if item != cart_normalizado[-1]:
            houve_ajuste = True

    if houve_ajuste or len(cart_normalizado) != len(cart):
        session["cart"] = cart_normalizado
        session.modified = True

    return session["cart"]


def obter_destino_pos_login():
    destino = request.values.get("next", "").strip()
    if not destino or not destino.startswith("/"):
        return url_for("loja_cliente")
    if destino.startswith("//"):
        return url_for("loja_cliente")
    return destino


def obter_destino_pos_carrinho():
    destino = request.form.get("next", "").strip()
    if destino == "cart":
        return url_for("ver_carrinho")
    return url_for("loja_cliente")


def adicionar_item_ao_carrinho(product_id, quantidade):
    if quantidade <= 0:
        return "Quantidade invalida.", "error"

    produto = get_db().execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not produto:
        return "Produto nao encontrado.", "error"
    if produto["stock"] < quantidade:
        return "Estoque insuficiente para esse produto.", "error"

    cart = carrinho_atual()
    existente = next((item for item in cart if item["product_id"] == product_id), None)
    if existente:
        if existente["quantity"] + quantidade > produto["stock"]:
            return "A quantidade total no carrinho excede o estoque.", "error"
        existente["quantity"] += quantidade
    else:
        cart.append(
            {
                "product_id": product_id,
                "name": produto["name"],
                "unit_price": float(produto["price"]),
                "quantity": quantidade,
            }
        )

    session.modified = True
    return "Produto adicionado ao carrinho.", "success"


@app.route("/health")
def healthcheck():
    db = get_db()
    db.execute("SELECT 1").fetchone()
    return {"status": "ok"}, 200


@app.route("/")
def index():
    db = get_db()
    contagens = {
        "clientes": db.execute("SELECT COUNT(*) FROM clients").fetchone()[0],
        "produtos": db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "vendas": db.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
    }
    destaques = db.execute(
        "SELECT id, name, category, price, stock, status, image_path FROM products ORDER BY id DESC LIMIT 6"
    ).fetchall()
    catalogo_publico = {
        "nome": "Cattleya hibrida",
        "preco": "80,00",
        "imagem": "cattleya.site.jpeg",
        "descricao": (
            "Orquidea de flores grandes, perfumadas e vibrantes, ideal para quem quer destacar "
            "a beleza natural do ambiente com um toque elegante."
        ),
        "ambiente": "Vai muito bem em locais bem iluminados, com luz indireta e boa ventilacao.",
        "cuidados": "Rega moderada e substrato leve, sempre deixando secar entre uma irrigacao e outra.",
    }
    produto_catalogo = db.execute(
        "SELECT id FROM products WHERE LOWER(name) = LOWER(?) LIMIT 1",
        (catalogo_publico["nome"],),
    ).fetchone()
    return render_template(
        "index.html",
        contagens=contagens,
        destaques=destaques,
        catalogo_publico=catalogo_publico,
        catalogo_produto_id=produto_catalogo["id"] if produto_catalogo else None,
    )


@app.route("/assets/<path:filename>")
def asset_file(filename):
    if Path(filename).suffix.lower() not in EXTENSOES_IMAGEM:
        return "", 404
    return send_from_directory(BASE_DIR, filename)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        senha = request.form.get("password", "")
        if email == CONFIG["admin_email"] and senha == CONFIG["admin_password"]:
            session.clear()
            session["admin_logged_in"] = True
            flash("Login de administrador realizado.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Email ou senha invalidos.", "error")
    return render_template("admin_login.html")


@app.route("/cliente/login", methods=["GET", "POST"])
def cliente_login():
    proximo_destino = obter_destino_pos_login()
    if request.method == "POST":
        cpf = normalizar_cpf(request.form.get("cpf"))
        senha = request.form.get("password", "")
        cliente = get_db().execute("SELECT * FROM clients WHERE cpf = ?", (cpf,)).fetchone()
        if cliente and check_password_hash(cliente["password_hash"], senha):
            session.clear()
            session["client_id"] = cliente["id"]
            session["client_name"] = cliente["name"]
            session["cart"] = []
            flash("Login realizado com sucesso.", "success")
            return redirect(proximo_destino)
        flash("CPF ou senha invalidos.", "error")
    return render_template("cliente_login.html", proximo_destino=proximo_destino)


@app.route("/cliente/cadastro", methods=["GET", "POST"])
def cliente_cadastro():
    proximo_destino = obter_destino_pos_login()
    if request.method == "POST":
        nome = request.form.get("name", "").strip()
        cpf = normalizar_cpf(request.form.get("cpf"))
        email = request.form.get("email", "").strip()
        cidade = request.form.get("city", "").strip()
        estado = request.form.get("state", "").strip().upper()
        senha = request.form.get("password", "")
        confirmar = request.form.get("password_confirm", "")
        if not nome or len(cpf) != 11 or not senha:
            flash("Preencha nome, CPF valido e senha.", "error")
            return render_template("cliente_cadastro.html", proximo_destino=proximo_destino)
        if senha != confirmar:
            flash("As senhas nao conferem.", "error")
            return render_template("cliente_cadastro.html", proximo_destino=proximo_destino)
        db = get_db()
        try:
            db.execute(
                """
                INSERT INTO clients (name, cpf, email, phone, city, state, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    nome,
                    cpf,
                    email,
                    request.form.get("phone", "").strip(),
                    cidade,
                    estado,
                    generate_password_hash(senha),
                    datetime.now().strftime("%d/%m/%Y %H:%M"),
                ),
            )
            db.commit()
        except sqlite3.IntegrityError:
            flash("Ja existe um cliente com esse CPF.", "error")
            return render_template("cliente_cadastro.html", proximo_destino=proximo_destino)
        flash("Cadastro concluido. Agora voce ja pode entrar.", "success")
        return redirect(url_for("cliente_login", next=proximo_destino))
    return render_template("cliente_cadastro.html", proximo_destino=proximo_destino)


@app.route("/logout")
def logout():
    session.clear()
    flash("Sessao encerrada.", "success")
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    clientes = db.execute("SELECT * FROM clients ORDER BY id DESC").fetchall()
    produtos = db.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    vendas = db.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 20").fetchall()
    return render_template("admin_dashboard.html", clientes=clientes, produtos=produtos, vendas=vendas)


@app.post("/admin/produtos/novo")
@admin_required
def admin_novo_produto():
    nome = request.form.get("name", "").strip()
    categoria = request.form.get("category", "").strip()
    status = request.form.get("status", "Disponivel").strip()
    try:
        preco = float(request.form.get("price", "0"))
        estoque = int(request.form.get("stock", "0"))
    except ValueError:
        flash("Preco ou estoque invalidos.", "error")
        return redirect(url_for("admin_dashboard"))

    if not nome:
        flash("Informe o nome do produto.", "error")
        return redirect(url_for("admin_dashboard"))

    db = get_db()
    db.execute(
        """
        INSERT INTO products (name, category, price, stock, status, image_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            nome,
            categoria,
            preco,
            estoque,
            status,
            encontrar_imagem_produto(nome),
            datetime.now().strftime("%d/%m/%Y %H:%M"),
        ),
    )
    db.commit()
    flash("Produto criado no site.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/clientes/novo")
@admin_required
def admin_novo_cliente():
    nome = request.form.get("name", "").strip()
    cpf = normalizar_cpf(request.form.get("cpf"))
    senha = request.form.get("password", "").strip()
    if not nome or len(cpf) != 11:
        flash("Informe nome e CPF valido.", "error")
        return redirect(url_for("admin_dashboard"))

    db = get_db()
    try:
        db.execute(
            """
            INSERT INTO clients (name, cpf, email, phone, city, state, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nome,
                cpf,
                request.form.get("email", "").strip(),
                request.form.get("phone", "").strip(),
                request.form.get("city", "").strip(),
                request.form.get("state", "").strip().upper(),
                generate_password_hash(senha or cpf),
                datetime.now().strftime("%d/%m/%Y %H:%M"),
            ),
        )
        db.commit()
    except sqlite3.IntegrityError:
        flash("CPF ja cadastrado no site.", "error")
        return redirect(url_for("admin_dashboard"))

    flash("Cliente criado no site.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/loja")
@client_required
def loja_cliente():
    produtos = get_db().execute(
        "SELECT * FROM products WHERE status != 'Inativo' ORDER BY name"
    ).fetchall()
    itens_carrinho = sum(item["quantity"] for item in carrinho_atual())
    return render_template("cliente_loja.html", produtos=produtos, itens_carrinho=itens_carrinho)


@app.post("/carrinho/adicionar/<int:product_id>")
@client_required
def adicionar_carrinho(product_id):
    try:
        quantidade = int(request.form.get("quantity", "1"))
    except ValueError:
        quantidade = 0
    mensagem, categoria = adicionar_item_ao_carrinho(product_id, quantidade)
    flash(mensagem, categoria)
    return redirect(obter_destino_pos_carrinho())


@app.post("/comprar-agora/<int:product_id>")
@client_required
def comprar_agora(product_id):
    try:
        quantidade = int(request.form.get("quantity", "1"))
    except ValueError:
        quantidade = 0
    mensagem, categoria = adicionar_item_ao_carrinho(product_id, quantidade)
    flash(mensagem, categoria)
    return redirect(url_for("ver_carrinho"))


@app.route("/carrinho")
@client_required
def ver_carrinho():
    cart = carrinho_atual()
    total = sum(item["unit_price"] * item["quantity"] for item in cart)
    return render_template(
        "carrinho.html",
        cart=cart,
        total=total,
        pix_key=CONFIG["pix_key"],
        itens_carrinho=sum(item["quantity"] for item in cart),
    )


@app.get("/pedido/<int:sale_id>")
@client_required
def pedido_confirmado(sale_id):
    db = get_db()
    pedido = db.execute(
        "SELECT id, total, status, created_at FROM sales WHERE id = ? AND client_id = ?",
        (sale_id, session["client_id"]),
    ).fetchone()
    if not pedido:
        flash("Pedido nao encontrado.", "error")
        return redirect(url_for("loja_cliente"))
    itens = db.execute(
        """
        SELECT product_name, quantity, unit_price, total_price
        FROM sale_items
        WHERE sale_id = ?
        ORDER BY id
        """,
        (sale_id,),
    ).fetchall()
    return render_template("pedido_confirmado.html", pedido=pedido, itens=itens, pix_key=CONFIG["pix_key"])


@app.post("/carrinho/remover/<int:product_id>")
@client_required
def remover_carrinho(product_id):
    session["cart"] = [item for item in carrinho_atual() if item["product_id"] != product_id]
    flash("Item removido do carrinho.", "success")
    return redirect(url_for("ver_carrinho"))


@app.post("/checkout")
@client_required
def checkout():
    cart = carrinho_atual()
    if not cart:
        flash("Seu carrinho esta vazio.", "error")
        return redirect(url_for("ver_carrinho"))

    db = get_db()
    produtos = []
    total = 0.0
    for item in cart:
        produto = db.execute("SELECT * FROM products WHERE id = ?", (item["product_id"],)).fetchone()
        if not produto or produto["stock"] < item["quantity"]:
            flash(f"Estoque insuficiente para {item['name']}.", "error")
            return redirect(url_for("ver_carrinho"))
        produtos.append(produto)
        total += float(produto["price"]) * item["quantity"]

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    try:
        db.execute("BEGIN")
        cursor = db.execute(
            "INSERT INTO sales (client_id, client_name, total, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (session["client_id"], session["client_name"], total, "Aguardando PIX", agora),
        )
        sale_id = cursor.lastrowid
        for item, produto in zip(cart, produtos):
            novo_estoque = int(produto["stock"]) - int(item["quantity"])
            novo_status = "Disponivel" if novo_estoque > 0 else "Esgotado"
            db.execute(
                "UPDATE products SET stock = ?, status = ? WHERE id = ?",
                (novo_estoque, novo_status, produto["id"]),
            )
            db.execute(
                """
                INSERT INTO sale_items (sale_id, product_id, product_name, quantity, unit_price, total_price)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    sale_id,
                    produto["id"],
                    produto["name"],
                    item["quantity"],
                    float(produto["price"]),
                    float(produto["price"]) * item["quantity"],
                ),
            )
        db.commit()
    except sqlite3.DatabaseError:
        db.rollback()
        flash("Nao foi possivel concluir a compra.", "error")
        return redirect(url_for("ver_carrinho"))

    session["cart"] = []
    flash("Compra registrada com sucesso.", "success")
    return redirect(url_for("pedido_confirmado", sale_id=sale_id))


if __name__ == "__main__":
    host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(host=host, port=port, debug=debug)
