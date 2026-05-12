from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo

class LoginForm(FlaskForm):
    username = StringField('Nome de Usuário', validators=[DataRequired()])
    password = PasswordField('Senha', validators=[DataRequired()])
    submit = SubmitField('Entrar')

class AdminRegistrationForm(FlaskForm):
    username = StringField('Nome de Usuário do Admin', validators=[DataRequired(), Length(min=3, max=50)])
    password = PasswordField('Senha do Admin', validators=[])
    confirm_password = PasswordField('Confirmar Senha', validators=[EqualTo('password')])
    submit = SubmitField('Registrar Admin')

class AdminLoginForm(FlaskForm):
    username = StringField('Nome de Usuário do Admin', validators=[DataRequired()])
    password = PasswordField('Senha do Admin', validators=[DataRequired()])
    submit = SubmitField('Entrar')

class AdminChangePasswordForm(FlaskForm):
    current_password = PasswordField('Senha Atual', validators=[DataRequired()])
    new_password = PasswordField('Nova Senha', validators=[DataRequired(), Length(min=8, message='A senha deve ter pelo menos 8 caracteres.')])
    confirm_new_password = PasswordField('Confirmar Nova Senha', validators=[DataRequired(), EqualTo('new_password', message='As senhas não coincidem.')])
    submit = SubmitField('Alterar Senha')

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Senha Atual', validators=[DataRequired()])
    new_password = PasswordField('Nova Senha', validators=[DataRequired(), Length(min=8, message='A senha deve ter pelo menos 8 caracteres.')])
    confirm_new_password = PasswordField('Confirmar Nova Senha', validators=[DataRequired(), EqualTo('new_password', message='As senhas não coincidem.')])
    submit = SubmitField('Alterar Senha')
