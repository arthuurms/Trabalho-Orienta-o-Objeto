from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import openai
from abc import ABC, abstractmethod

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SECRET_KEY'] = '123456'
db = SQLAlchemy(app)

class OpenAIConfig:
    _instance = None

    @staticmethod
    def criar_instancia():
        if OpenAIConfig._instance is None:
            OpenAIConfig()
        return OpenAIConfig._instance

    def __init__(self):
        if OpenAIConfig._instance is None:
            openai.api_key = ''
            OpenAIConfig._instance = self

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)

    def __init__(self, name, password):
        self.name = name
        self.password = generate_password_hash(password)

    def verify_password(self, pwd):
        return check_password_hash(self.password, pwd)
    
class Descricao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_produto = db.Column(db.String(128), nullable=False)
    comentario = db.Column(db.Text, nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

with app.app_context():
    db.create_all()

class Tipo_Descricao(ABC):
    @abstractmethod
    def gerar(nome_produto, comentario):
        pass

class PequenaDescricao(Tipo_Descricao):
    @staticmethod
    def gerar(nome_produto, comentario):
        return SimplificadorDescricao.gerar_descricao(nome_produto, comentario, "pequena")
    
class SimplesDescricao(Tipo_Descricao):
    @staticmethod
    def gerar(nome_produto, comentario):
        return SimplificadorDescricao.gerar_descricao(nome_produto, comentario, "simples")
    
class CompletaDescricao(Tipo_Descricao):
    @staticmethod
    def gerar(nome_produto, comentario):
        return SimplificadorDescricao.gerar_descricao(nome_produto, comentario, "completa")

class SimplificadorDescricao:
    @staticmethod
    def gerar_descricao(nome_produto, comentario, tipo):
        OpenAIConfig.criar_instancia()
        
        if tipo == "pequena":
            max_tokens = 300
        elif tipo == "simples":
            max_tokens = 600
        elif tipo == "completa":
            max_tokens = 900
        else:
            raise ValueError("Tipo de descrição inválido")

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Atue como um profissional em copywritter e crie uma descrição persuasiva para um produto"},
                {"role": "user", "content": f"Digite uma {tipo} descrição sobre um(a) {nome_produto} com os seguintes detalhes: {comentario}. Não use simbolos, tags html e nem formate o texto."}
            ],
            max_tokens=max_tokens
        )
        return response.choices[0].message['content'].strip()

class CriarDescricao:
    @staticmethod
    def criar(tipo):
        if tipo == 'pequeno':
            return PequenaDescricao()
        if tipo == 'simples':
            return SimplesDescricao()
        if tipo == 'completa':
            return CompletaDescricao()
        raise ValueError("Não foi possivel criar o tipo solicitado")

class Criar_Texto_Strategy:
    @staticmethod
    def criar_instancia(nome_produto, comentario, tipo, userid):
        texto_copy = tipo.gerar(nome_produto, comentario)
        return Descricao(nome_produto=nome_produto, comentario=comentario, descricao=texto_copy, user_id=userid)

@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if request.method == 'POST':
        name = request.form['name']
        pwd = request.form['password']
        if name and pwd:
            if not User.query.filter_by(name=name).first():
                user = User(name, pwd)
                db.session.add(user)
                db.session.commit()
                session['user_id'] = user.id
                return redirect(url_for('home'))
            else:
                return '''Usuario já existente <a href="registrar">clique para voltar</a>'''

    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form['name']
        pwd = request.form['password']
        user = User.query.filter_by(name=name).first()
        if user and user.verify_password(pwd):
            session['user_id'] = user.id
            return redirect(url_for('home'))
        else:
            return '''Usuario ou senha incorreta <a href="login">clique para voltar</a>'''

    return render_template('login.html')

@app.route('/', methods=['GET', 'POST'])
def index():
    return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/home', methods=['GET', 'POST'])
def home():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if request.method == 'POST':
            nome_produto = request.form['nome_produto']
            comentario = request.form['comentario']
            tipo = request.form['tipo']
            userid = session['user_id']

            tipo_instancia = CriarDescricao.criar(tipo)
            fabricar = Criar_Texto_Strategy()
            nova_descricao = fabricar.criar_instancia(nome_produto, comentario, tipo_instancia, userid)
            db.session.add(nova_descricao)
            db.session.commit()
    else:
        return redirect(url_for('login'))

    descricoes = Descricao.query.filter_by(user_id=user.id).all()
    return render_template('home.html', user=user, descricoes=descricoes)

@app.route('/editar/<int:descricao_id>', methods=['GET', 'POST'])
def editar_descricao(descricao_id):
    if 'user_id' in session:
        descricao = Descricao.query.get(descricao_id)
        if descricao:
            if request.method == 'POST':
                descricao.nome_produto = request.form['nome_produto']
                descricao.descricao = request.form['descricao']
                db.session.commit()
                return redirect(url_for('home'))
        else:
            return '''Essa descrição não existe! <a href="../home">clique para voltar</a>'''
    else:
        return redirect(url_for('login'))
    return render_template('editar_descricao.html', descricao=descricao)

@app.route('/excluir_descricao/<int:descricao_id>', methods=['GET', 'POST'])
def excluir_descricao(descricao_id):
    if request.method == 'POST':
        if 'user_id' in session:
            descricao = Descricao.query.get(descricao_id)
            db.session.delete(descricao)
            db.session.commit()
            return redirect(url_for('home'))
        else:
            return redirect(url_for('login'))
    else:
        return '''Não é possivel excluir desta maneira! <a href="home">clique para voltar</a>'''
    
@app.errorhandler(404)
def page_not_found(e):
    return '''Essa página não existe, <a href="home">clique para voltar</a>'''

if __name__ == '__main__':
    app.run()
