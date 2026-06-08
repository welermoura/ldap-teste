from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, FileField, SubmitField
from wtforms.validators import DataRequired, Regexp
from flask_wtf.file import FileAllowed

class ConfigForm(FlaskForm):
    ad_server = StringField('Servidor AD', validators=[DataRequired()])
    use_ldaps = BooleanField('Usar LDAPS (SSL)', default=False)
    ca_cert = FileField('Certificado de CA para LDAPS (.cer, .crt, .pem)', validators=[
        FileAllowed(['cer', 'crt', 'pem'], 'Apenas certificados (.cer, .crt, .pem) são permitidos.')
    ])
    ad_domain = StringField('Domínio (NetBIOS name, ex: MEUDOMINIO)', validators=[DataRequired()])
    ad_search_base = StringField('Base de Busca AD (ex: OU=Usuarios,DC=dominio,DC=com)', validators=[DataRequired()])
    sso_enabled = BooleanField('Habilitar Single Sign-On (SSO)', default=False)
    default_password = PasswordField('Senha Padrão (deixe em branco para não alterar)')
    service_account_user = StringField('Usuário de Serviço (para tarefas automáticas)')
    service_account_password = PasswordField('Senha do Usuário de Serviço (deixe em branco para não alterar)')
    submit = SubmitField('Salvar Configuração')

class AppearanceForm(FlaskForm):
    bg_color = StringField('Cor de Fundo (Hex)', validators=[Regexp(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$', message="Formato inválido. Use #RRGGBB.")])
    bg_image = FileField('Imagem de Fundo', validators=[FileAllowed(['jpg', 'png', 'jpeg', 'gif', 'webp'], 'Apenas imagens são permitidas.')])
    logo = FileField('Logo', validators=[FileAllowed(['jpg', 'png', 'jpeg', 'svg'], 'Apenas imagens são permitidas.')])
    favicon = FileField('Favicon', validators=[FileAllowed(['ico', 'png'], 'Apenas .ico ou .png permitidos.')])
    subtitle = StringField('Subtítulo do Cabeçalho')
    submit = SubmitField('Salvar Aparência')
