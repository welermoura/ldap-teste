from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired

class GroupSearchForm(FlaskForm):
    search_query = StringField('Buscar Grupo por Nome', validators=[DataRequired()])
    submit = SubmitField('Buscar')

class CreateScheduleForm(FlaskForm):
    # sAMAccountName of the user
    sam_account = StringField('Login do Usuário', validators=[DataRequired()])
    # Group DN or sAMAccountName
    group_name = StringField('Nome do Grupo', validators=[DataRequired()])
    # Duration or end date (depends on app logic, but let's use what's in app.py)
    submit = SubmitField('Agendar')

class ManageMemberForm(FlaskForm):
    sam_account = StringField('Login do Usuário', validators=[DataRequired()])
    submit = SubmitField('Adicionar/Remover')
