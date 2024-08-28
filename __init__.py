from app.utils.PluginClass import PluginClass
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils import DatabaseHandler
from flask import request
from celery import shared_task
from dotenv import load_dotenv
import os
from app.api.records.models import RecordUpdate
from app.api.users.services import has_role
from bson.objectid import ObjectId
import json
import daemon


load_dotenv()

mongodb = DatabaseHandler.DatabaseHandler()

USER_FILES_PATH = os.environ.get('USER_FILES_PATH', '')
WEB_FILES_PATH = os.environ.get('WEB_FILES_PATH', '')
ORIGINAL_FILES_PATH = os.environ.get('ORIGINAL_FILES_PATH', '')

state = {}

TYPE, SENDING = range(2)

class ExtendedPluginClass(PluginClass):
    def __init__(self, path, import_name, name, description, version, author, type, settings):
        super().__init__(path, __file__, import_name, name, description, version, author, type, settings)
        if not os.environ.get('CELERY_WORKER'):
            self.activate_settings()

    @shared_task(name='telegramIntegration.bot', queue='telegram')
    def run_telegram_bot(bot_token):
        import logging
        from telegram import ForceReply, Update, ReplyKeyboardRemove
        # from telegram.ext import Application, CommandHandler, ContextTypes
        from telegram.ext import (
            Application,
            CommandHandler,
            ContextTypes,
            ConversationHandler,
            MessageHandler,
            filters,
        )
        instance = ExtendedPluginClass('telegramIntegration','', **plugin_info)

        def get_username(update):
            return update.message.from_user.first_name + ' ' + update.message.from_user.last_name + ' [' + str(update.message.from_user.id) + ']'

        async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            print(get_username(update))
            if update.message.from_user.id not in state:
                await update.message.reply_text("Hola, bienvenido al bot del Museo Afro. En este momento la única funcionalidad que tengo es la de organizar la información que me mandes en un recurso en la plataforma. Tan solo debes seleccionar el nombre del taller desde /config y luego enviar el material que deseas agregar al taller.")
            else:
                await update.message.reply_text("Para agregar contenido al taller seleccionado ["+state[update.message.from_user.id]['type']+"], envía el material que deseas agregar.")

        async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            print(get_username(update))
            from app.api.lists.services import get_all as get_all_lists
            list = instance.get_plugin_settings()['list']
            from app.api.lists.services import get_by_id
            list = get_by_id(list)
            options = list['options']

            reply_text = "Selecciona el taller al que deseas agregar contenido\n\n"
            step = 0
            for option in options:
                step += 1
                reply_text += f"{step} - {option['term']}\n"

            await update.message.reply_text(reply_text, reply_markup=ReplyKeyboardRemove())

            return TYPE
        
        async def type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            from app.api.lists.services import get_all as get_all_lists
            list = instance.get_plugin_settings()['list']
            from app.api.lists.services import get_by_id
            list = get_by_id(list)
            options = list['options'] 
            msg = update.message.text

            try:
                msg = int(msg)
            except:
                await update.message.reply_text('Debes seleccionar un número de la lista')
                return TYPE
            
            try:
                state[update.message.from_user.id] = {
                    'type': options[msg - 1]['term'],
                    'id': options[msg - 1]['id']
                }

                await update.message.reply_text('Envía el contenido que deseas agregar al taller')

                return SENDING
            except:
                await update.message.reply_text('Debes seleccionar un número de la lista')
                return TYPE

        async def sendig_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            print(update)

        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
        )
        logging.getLogger("httpx").setLevel(logging.WARNING)

        # Initialize and run the application
        application = Application.builder().token(bot_token).build()

        conversation = ConversationHandler(
            entry_points=[CommandHandler("inicio", config_command)],
            states={
                TYPE: [MessageHandler(filters.TEXT, type)],
                SENDING: [MessageHandler(filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.ANIMATION, sendig_files)],
            },
            fallbacks=[
                CommandHandler("config", config_command),
                CommandHandler("ayuda", help_command),
            ],
        )

        application.add_handler(conversation)
        application.run_polling(drop_pending_updates=True)

        return 'ok'

    def activate_settings(self):
        current = self.get_plugin_settings()
        if current is None:
            return
        
        if 'bot_token' in current:
            if current['bot_token'] != '':
                self.run_telegram_bot.delay(current['bot_token'])
        
        

    def add_routes(self):
        @self.route('/bulk', methods=['POST'])
        @jwt_required()
        def process_files():
            current_user = get_jwt_identity()
            body = request.get_json()

            self.validate_fields(body, 'bulk')
            self.validate_roles(current_user, ['admin', 'processing'])

            task = self.bulk.delay(body, current_user)
            self.add_task_to_user(task.id, 'telegramIntegration.bulk', current_user, 'msg')
            
            return {'msg': 'Se agregó la tarea a la fila de procesamientos'}, 201
        
    @shared_task(ignore_result=False, name='telegramIntegration.bulk')
    def bulk(body, user):
        filters = {
            'post_type': body['post_type']
        }

        if 'parent' in body:
            if body['parent']:
                filters = {'$or': [{'parents.id': body['parent'], 'post_type': body['post_type']}, {'_id': ObjectId(body['parent'])}]}
                
        if 'resources' in body:
            if body['resources']:
                if len(body['resources']) > 0:
                    filters = {'_id': {'$in': [ObjectId(resource) for resource in body['resources']]}, **filters}

        return 'ok'
    
    def get_settings(self):
        @self.route('/settings/<type>', methods=['GET'])
        @jwt_required()
        def get_settings(type):
            try:
                current_user = get_jwt_identity()

                if not has_role(current_user, 'admin') and not has_role(current_user, 'processing'):
                    return {'msg': 'No tiene permisos suficientes'}, 401
                
                from app.api.types.services import get_all as get_all_types
                types = get_all_types()
                from app.api.lists.services import get_all as get_all_lists
                lists = get_all_lists()
                lists = lists[0]

                if isinstance(types, list):
                    types = tuple(types)[0]

                current = self.get_plugin_settings()
                print(current)

                resp = {**self.settings}
                resp = json.loads(json.dumps(resp))

                if type == 'all':
                    return resp
                elif type == 'settings':
                    resp['settings'][0]['default'] = current['bot_token'] if 'bot_token' in current else ''
                    resp['settings'].append({
                        'type': 'select',
                        'id': 'type',
                        'label': 'Tipo de contenido a activar',
                        'default': current['type'] if 'type' in current else '',
                        'options': [{'value': t['slug'], 'label': t['name']} for t in types],
                        'required': True
                    })
                    resp['settings'].append({
                        'type': 'select',
                        'id': 'list',
                        'label': 'Lista de contenido a activar',
                        'default': current['list'] if 'list' in current else '',
                        'options': [{'value': l['id'], 'label': l['name']} for l in lists],
                        'required': True
                    })
                    return resp['settings']
                else:
                    return resp['settings_' + type]
            except Exception as e:
                return {'msg': str(e)}, 500
            
        @self.route('/settings', methods=['POST'])
        @jwt_required()
        def set_settings_update():
            try:
                current_user = get_jwt_identity()

                if not has_role(current_user, 'admin') and not has_role(current_user, 'processing'):
                    return {'msg': 'No tiene permisos suficientes'}, 401
                
                body = request.form.to_dict()
                data = body['data']
                data = json.loads(data)

                self.set_plugin_settings(data)

                return {'msg': 'Configuración guardada'}, 200
            
            except Exception as e:
                return {'msg': str(e)}, 500
    
plugin_info = {

    'name': 'Telegram BOT',
    'description': 'Plugin para integración con bots de Telegram',
    'version': '0.1',
    'author': 'Bitsol',
    'type': ['settings'],
    'settings': {
        'settings': [
            {
                'type': 'text',
                'label': 'BOT Token',
                'id': 'bot_token',
                'default': '',
                'required': True
            }
        ]
    }
}