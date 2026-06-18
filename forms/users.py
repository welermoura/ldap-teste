from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField
from wtforms.validators import DataRequired

class UserSearchForm(FlaskForm):
    search_query = StringField('Buscar Usuário (Nome ou Login)', validators=[DataRequired()])
    submit = SubmitField('Buscar')

class CreateUserForm(FlaskForm):
    first_name = StringField('Nome', validators=[DataRequired()])
    last_name = StringField('Sobrenome', validators=[DataRequired()])
    sam_account = StringField('Login (sAMAccountName)', validators=[DataRequired()])
    upn_suffix = SelectField('Domínio / UPN Suffix', validators=[DataRequired()])
    matricula = StringField('Matrícula')
    telephone = StringField('Telefone Principal')
    model_name = StringField('Nome do Usuário Modelo (para copiar grupos e atributos)', validators=[DataRequired()])
    submit = SubmitField('Buscar Modelo')

class EditUserForm(FlaskForm):
    first_name = StringField('Nome', validators=[DataRequired()])
    initials = StringField('Iniciais')
    last_name = StringField('Sobrenome', validators=[DataRequired()])
    display_name = StringField('Nome de Exibição', validators=[DataRequired()])
    cn = StringField('Nome Completo', validators=[DataRequired()])
    description = StringField('Descrição')
    office = StringField('Escritório')
    telephone = StringField('Telefone Principal')
    email = StringField('E-mail', render_kw={'readonly': True})
    upn = StringField('Login (UPN)', validators=[DataRequired()])
    web_page = StringField('Página da Web')
    street = StringField('Rua')
    post_office_box = StringField('Caixa Postal')
    city = StringField('Cidade')
    state = StringField('Estado/Província')
    zip_code = StringField('CEP')
    home_phone = StringField('Telefone Residencial')
    pager = StringField('Pager')
    mobile = StringField('Celular')
    fax = StringField('Fax')
    title = StringField('Cargo')
    department = StringField('Departamento')
    company = StringField('Empresa')
    manager = StringField('Gerente (Login)')
    matricula = StringField('Matrícula')
    submit = SubmitField('Salvar Alterações')

class DeleteUserForm(FlaskForm):
    confirm_title = StringField('Confirmar Cargo', validators=[DataRequired()])
    confirm_sam = StringField('Confirmar Login', validators=[DataRequired()])
    submit = SubmitField('Eu entendo as consequências, excluir este usuário')
