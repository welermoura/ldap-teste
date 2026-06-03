import os
import json
import logging
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Central SQLAlchemy instance
db = SQLAlchemy()

class ConfigSetting(db.Model):
    __tablename__ = 'config_settings'
    key = db.Column(db.String(150), primary_key=True)
    value = db.Column(db.Text, nullable=True)

class Schedule(db.Model):
    __tablename__ = 'schedules'
    username = db.Column(db.String(150), primary_key=True)
    reactivation_date = db.Column(db.String(50), nullable=False)

class DisableSchedule(db.Model):
    __tablename__ = 'disable_schedules'
    username = db.Column(db.String(150), primary_key=True)
    deactivation_date = db.Column(db.String(50), nullable=False)

class GroupSchedule(db.Model):
    __tablename__ = 'group_schedules'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_dn = db.Column(db.String(500), unique=True, nullable=False)
    target_mail = db.Column(db.String(250), nullable=False)
    sync_type = db.Column(db.String(50), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

class Permission(db.Model):
    __tablename__ = 'permissions'
    group_name = db.Column(db.String(250), primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    allowed_ous = db.Column(db.Text, nullable=True) # JSON array encoded as string
    actions = db.Column(db.Text, nullable=True) # JSON object/array encoded as string
    views = db.Column(db.Text, nullable=True) # JSON object encoded as string

class AdminUser(db.Model):
    __tablename__ = 'admin_users'
    username = db.Column(db.String(150), primary_key=True)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(250), nullable=True)
    email = db.Column(db.String(250), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)

class HistoryLog(db.Model):
    __tablename__ = 'history_logs'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    action = db.Column(db.String(100), nullable=False)
    user_sam = db.Column(db.String(150), nullable=False)
    details = db.Column(db.Text, nullable=True)

class ZimbraMapping(db.Model):
    __tablename__ = 'zimbra_mappings'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ad_group_name = db.Column(db.String(250), unique=True, nullable=False)
    zimbra_dl_email = db.Column(db.String(250), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

def seed_database_from_json(database_instance):
    """Automatically seeds the SQL Server database from existing local JSON files if tables are empty."""
    basedir = os.path.abspath(os.path.dirname(__file__))
    data_dir = os.path.join(basedir, 'data')
    
    # Executa verificação e migração simples para a coluna 'views' na tabela 'permissions'
    try:
        from sqlalchemy import inspect
        inspector = inspect(database_instance.engine)
        if 'permissions' in inspector.get_table_names():
            columns = [c['name'] for c in inspector.get_columns('permissions')]
            if 'views' not in columns:
                logging.info("[DB Migration] Column 'views' is missing from 'permissions' table. Adding it now...")
                # Usando execute direto no db
                database_instance.session.execute(db.text("ALTER TABLE permissions ADD views VARCHAR(MAX) NULL"))
                database_instance.session.commit()
                logging.info("[DB Migration] Column 'views' added successfully to 'permissions' table.")
    except Exception as e:
        logging.error(f"[DB Migration] Error checking/adding 'views' column: {e}")

    # 1. Seed general config
    if ConfigSetting.query.count() == 0:
        config_path = os.path.join(data_dir, 'config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        # Save raw values (since they are already encrypted in config.json on disk)
                        setting = ConfigSetting(key=k, value=str(v) if v is not None else '')
                        database_instance.session.add(setting)
                database_instance.session.commit()
                logging.info("[DB Migration] Config settings seeded successfully.")
            except Exception as e:
                logging.error(f"[DB Migration] Error seeding config: {e}")
                database_instance.session.rollback()

    # 2. Seed schedules
    if Schedule.query.count() == 0:
        schedules_path = os.path.join(data_dir, 'schedules.json')
        if os.path.exists(schedules_path):
            try:
                with open(schedules_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        sched = Schedule(username=k, reactivation_date=v)
                        database_instance.session.add(sched)
                database_instance.session.commit()
                logging.info("[DB Migration] Schedules seeded successfully.")
            except Exception as e:
                logging.error(f"[DB Migration] Error seeding schedules: {e}")
                database_instance.session.rollback()

    # 3. Seed disable schedules
    if DisableSchedule.query.count() == 0:
        disable_schedules_path = os.path.join(data_dir, 'disable_schedules.json')
        if os.path.exists(disable_schedules_path):
            try:
                with open(disable_schedules_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        dsched = DisableSchedule(username=k, deactivation_date=v)
                        database_instance.session.add(dsched)
                database_instance.session.commit()
                logging.info("[DB Migration] Disable schedules seeded successfully.")
            except Exception as e:
                logging.error(f"[DB Migration] Error seeding disable schedules: {e}")
                database_instance.session.rollback()

    # 4. Seed group schedules (Zimbra mapping rules)
    if GroupSchedule.query.count() == 0:
        group_schedules_path = os.path.join(data_dir, 'group_schedules.json')
        if os.path.exists(group_schedules_path):
            try:
                with open(group_schedules_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            gsched = GroupSchedule(
                                group_dn=item.get('group_dn'),
                                target_mail=item.get('target_mail'),
                                sync_type=item.get('sync_type', 'zimbra'),
                                active=item.get('active', True)
                            )
                            database_instance.session.add(gsched)
                database_instance.session.commit()
                logging.info("[DB Migration] Group schedules seeded successfully.")
            except Exception as e:
                logging.error(f"[DB Migration] Error seeding group schedules: {e}")
                database_instance.session.rollback()

    # 5. Seed permissions
    if Permission.query.count() == 0:
        permissions_path = os.path.join(data_dir, 'permissions.json')
        if os.path.exists(permissions_path):
            try:
                with open(permissions_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        allowed_ous_str = json.dumps(v.get('allowed_ous', []))
                        actions_str = json.dumps(v.get('actions', {}))
                        views_str = json.dumps(v.get('views', {}))
                        perm = Permission(
                            group_name=k,
                            type=v.get('type', 'none'),
                            allowed_ous=allowed_ous_str,
                            actions=actions_str,
                            views=views_str
                        )
                        database_instance.session.add(perm)
                database_instance.session.commit()
                logging.info("[DB Migration] Permissions seeded successfully.")
            except Exception as e:
                logging.error(f"[DB Migration] Error seeding permissions: {e}")
                database_instance.session.rollback()

    # 6. Seed admin users
    if AdminUser.query.count() == 0:
        users_path = os.path.join(data_dir, 'users.json')
        if os.path.exists(users_path):
            try:
                with open(users_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        admin_user = AdminUser(
                            username=k,
                            password_hash=v,
                            display_name=k.capitalize(),
                            active=True
                        )
                        database_instance.session.add(admin_user)
                database_instance.session.commit()
                logging.info("[DB Migration] Admin users seeded successfully.")
            except Exception as e:
                logging.error(f"[DB Migration] Error seeding admin users: {e}")
                database_instance.session.rollback()

    # 7. Seed history logs
    if HistoryLog.query.count() == 0:
        history_path = os.path.join(data_dir, 'history.json')
        if os.path.exists(history_path):
            try:
                with open(history_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        # Import only the last 500 entries to prevent initial transaction bloat
                        for item in data[-500:]:
                            try:
                                dt = datetime.fromisoformat(item.get('timestamp').replace('Z', '+00:00'))
                            except Exception:
                                dt = datetime.utcnow()
                            log = HistoryLog(
                                timestamp=dt,
                                action=item.get('action'),
                                user_sam=item.get('user_sam'),
                                details=item.get('details')
                            )
                            database_instance.session.add(log)
                database_instance.session.commit()
                logging.info("[DB Migration] History logs seeded successfully.")
            except Exception as e:
                logging.error(f"[DB Migration] Error seeding history logs: {e}")
                database_instance.session.rollback()

    # 8. Seed Zimbra mappings
    if ZimbraMapping.query.count() == 0:
        zimbra_mappings_path = os.path.join(data_dir, 'zimbra_mappings.json')
        if os.path.exists(zimbra_mappings_path):
            try:
                with open(zimbra_mappings_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            mapping = ZimbraMapping(
                                ad_group_name=item.get('ad_group_name'),
                                zimbra_dl_email=item.get('zimbra_dl_email'),
                                active=item.get('active', True)
                            )
                            database_instance.session.add(mapping)
                database_instance.session.commit()
                logging.info("[DB Migration] Zimbra mappings seeded successfully.")
            except Exception as e:
                logging.error(f"[DB Migration] Error seeding Zimbra mappings: {e}")
                database_instance.session.rollback()

def ensure_db_registered():
    from flask import current_app
    try:
        if current_app:
            app_obj = current_app._get_current_object()
            if "sqlalchemy" not in app_obj.extensions or app_obj.extensions["sqlalchemy"] is not db:
                db.init_app(app_obj)
    except RuntimeError:
        pass

