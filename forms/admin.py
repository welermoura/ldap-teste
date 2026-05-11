from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired

class LogSearchForm(FlaskForm):
    search_query = StringField('Filtrar Log por Texto')
    submit = SubmitField('Filtrar')
