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
import uuid
from app.utils import DatabaseHandler
from datetime import datetime

mongodb = DatabaseHandler.DatabaseHandler()

load_dotenv()

mongodb = DatabaseHandler.DatabaseHandler()

USER_FILES_PATH = os.environ.get('USER_FILES_PATH', '')
WEB_FILES_PATH = os.environ.get('WEB_FILES_PATH', '')
ORIGINAL_FILES_PATH = os.environ.get('ORIGINAL_FILES_PATH', '')
TEMPORAL_FILES_PATH = os.environ.get('TEMPORAL_FILES_PATH', '')

state = {}

TYPE, SENDING = range(2)

class ExtendedPluginClass(PluginClass):
    def __init__(self, path, import_name, name, description, version, author, type, settings):
        super().__init__(path, __file__, import_name, name, description, version, author, type, settings)
        if not os.environ.get('CELERY_WORKER'):
            print("No es un worker")
            self.activate_settings()

    @shared_task(ignore_result=False, name='telegramIntegration.bot', queue='telegram')
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
            if update.message.from_user.last_name is None:
                return update.message.from_user.first_name + ' [' + str(update.message.from_user.id) + ']'
            elif update.message.from_user.first_name is None:
                return update.message.from_user.last_name + ' [' + str(update.message.from_user.id) + ']'
            else:
                return update.message.from_user.first_name + ' ' + update.message.from_user.last_name + ' [' + str(update.message.from_user.id) + ']'

        async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            print(get_username(update))
            if update.message.from_user.id not in state:
                await update.message.reply_text("Hola, bienvenido al bot del Museo Afro. En este momento la única funcionalidad que tengo es la de organizar la información que me mandes en un recurso en la plataforma. Tan solo debes seleccionar el nombre del taller desde /config y luego enviar el material que deseas agregar al taller.")
            else:
                await update.message.reply_text("Para agregar contenido al taller seleccionado ["+state[update.message.from_user.id]['type']+"], envía el material que deseas agregar.")

        async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            from app.api.lists.services import get_all as get_all_lists
            list = instance.get_plugin_settings()['list']
            from app.api.lists.services import get_by_id
            list = get_by_id(list)
            options = list['options']
            welcome_text = "¡Hola y bienvenido/a/e! 🎉\n\n"
            welcome_text += "Gracias por participar en este ejercicio colaborativo para la sistematización de información en eventos en vivo del Museo Afro de Colombia. 🙌\n"
            welcome_text += "Nuestro objetivo es capturar de manera ágil y organizada citas, fotografías, videos y audios que surgen durante estos encuentros. Todo el contenido que compartas será clave para documentar y preservar la memoria de los eventos, así como para dar visibilidad a las voces y experiencias de las comunidades afro.\n\n"
            welcome_text += "¿Cómo puedes participar? Es muy sencillo:\n"
            welcome_text += "- Envía citas o comentarios relevantes del evento en forma de texto 📝.\n"
            welcome_text += "- Comparte fotos, videos o audios que consideres importantes 🎥📸🎙️.\n\n"
            welcome_text += "Recuerda que este espacio es para contribuir al proceso de construcción colectiva, ¡así que tus aportes son muy valiosos! 💬"

            await update.message.reply_text(welcome_text, reply_markup=ReplyKeyboardRemove())

            reply_text = "Antes de empezar, selecciona el taller al que deseas agregar contenido:\n\n"
            step = 0
            for option in options:
                step += 1
                reply_text += f"{step} - {option['term']}\n"

            reply_text += "\nSi en algún momento deseas volver a configurar o cambiar el taller, solo escribe /configurar y podrás realizar los ajustes que necesites. 🔄\n"
            await update.message.reply_text(reply_text, reply_markup=ReplyKeyboardRemove())

            final_text = "Cada aporte que realices será parte de la memoria colectiva de ese taller. ¡Gracias por tu colaboración! 🎨✨"
            await update.message.reply_text(final_text, reply_markup=ReplyKeyboardRemove())

            return TYPE

        async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            from app.api.lists.services import get_all as get_all_lists
            list = instance.get_plugin_settings()['list']
            from app.api.lists.services import get_by_id
            list = get_by_id(list)
            options = list['options']

            reply_text = "Selecciona el taller al que deseas agregar contenido:\n\n"
            step = 0
            for option in options:
                step += 1
                reply_text += f"{step} - {option['term']}\n"

            reply_text += "\nSi en algún momento deseas volver a configurar o cambiar el taller, solo escribe /configurar y podrás realizar los ajustes que necesites. 🔄\n"
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
                if msg < 1:
                    raise Exception
            except:
                await update.message.reply_text('Debes seleccionar un número de la lista para continuar. Esto nos ayudará a organizar correctamente el contenido que compartas. 😊')
                return TYPE
            
            try:
                state[update.message.from_user.id] = {
                    'type': options[msg - 1]['term'],
                    'id': options[msg - 1]['id']
                }

                await update.message.reply_text('Envía el contenido que deseas agregar al taller 📝📸🎥. Ya sea un texto, foto, video o audio, todo lo que compartas se organizará automáticamente, así que no tendrás que preocuparte de nada más. ¡Solo envía tu aporte y yo me encargo del resto! 🙌\n\n¡Gracias por contribuir a la documentación del evento! 🌍✨')

                return SENDING
            except:
                await update.message.reply_text('Debes seleccionar un número de la lista para continuar. Esto nos ayudará a organizar correctamente el contenido que compartas. 😊')
                return TYPE

        async def sendig_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            form = None
            if update.message.document or update.message.photo or update.message.video or update.message.audio or update.message.voice:
                if update.message.document:
                    file = await update.message.document.get_file()
                elif update.message.photo:
                    file = await update.message.photo[-1].get_file()
                elif update.message.video:
                    file = await update.message.video.get_file()
                elif update.message.audio:
                    file = await update.message.audio.get_file()
                elif update.message.voice:
                    file = await update.message.voice.get_file()

                file_id = str(uuid.uuid4())
                file_ext = file.file_path.split('.')[-1]
                file_path = os.path.join(TEMPORAL_FILES_PATH, file_id + '.' + file_ext)
                await file.download_to_drive(file_path)
                form = []
                form.append((file_id + '.' + file_ext, open(file_path, 'rb')))

                type = instance.get_plugin_settings()['type']
                resource_title = "["+state[update.message.from_user.id]['type']+"] " + get_username(update)
                # verificar si existe el recurso
                resources = list(mongodb.get_all_records('resources', {'metadata.firstLevel.title': resource_title, 'post_type': type}, fields={'_id': 1}))

                if len(resources) == 0:
                    payload = {}

                    payload['post_type'] = type
                    payload['metadata'] = {
                        'firstLevel': {
                            'title': resource_title,
                        }
                    }
                    payload['status'] = 'draft'
                    payload['filesIds'] = [
                        {
                            'file': 0,
                            'filetag': 'Archivos'
                        }
                    ]

                    from app.api.resources.services import create
                    resource = create(payload, 'beta', [{'file': file_path, 'filename': file_id + '.' + file_ext}])
                else:
                    resource = mongodb.get_record('resources', {'_id': resources[0]['_id']}, fields={'_id': 1, 'metadata': 1, 'filesObj': 1})
                    payload = resource

                    payload = {**payload, 
                               'filesIds': [
                                      {
                                        'file': len(payload['filesObj']),
                                        'filetag': 'Archivos'
                                      }
                                 ],
                                 'post_type': type,
                                    'status': 'draft',
                                    'deletedFiles': [],
                                    'updatedFiles': []
                    }

                    from app.api.resources.services import update_by_id
                    resource = update_by_id(str(resource['_id']), payload, 'beta', [{'file': file_path, 'filename': file_id + '.' + file_ext}])

            
            await update.message.reply_text('Procesando contenido...')
            await update.message.reply_text('Contenido procesado correctamente, se agrega a la lista '+state[update.message.from_user.id]['type'] + ' del usuario '+str(get_username(update)))


        async def sendig_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            form = None
            if update.message.text and not update.message.text.startswith('/'):
                text = update.message.text

                type = instance.get_plugin_settings()['type']
                resource_title = "["+state[update.message.from_user.id]['type']+"] " + get_username(update)
                # verificar si existe el recurso
                resources = list(mongodb.get_all_records('resources', {'metadata.firstLevel.title': resource_title, 'post_type': type}, fields={'_id': 1}))

                if len(resources) == 0:
                    payload = {}
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    quote = '- ' + current_time + ' [ ' + text + ' ]\n'

                    payload['post_type'] = type
                    payload['metadata'] = {
                        'firstLevel': {
                            'title': resource_title,
                            'quotes': quote
                        }
                    }
                    payload['status'] = 'draft'
                    payload['filesIds'] = []

                    from app.api.resources.services import create
                    resource = create(payload, 'beta', [])
                    await update.message.reply_text('Contenido procesado correctamente, se agrega a la lista '+state[update.message.from_user.id]['type'] + ' del usuario '+str(get_username(update)))
                else:
                    resource = mongodb.get_record('resources', {'_id': resources[0]['_id']}, fields={'_id': 1, 'metadata': 1, 'filesObj': 1})
                    payload = resource

                    if 'quotes' not in payload['metadata']['firstLevel']:
                        payload['metadata']['firstLevel']['quotes'] = ''

                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    quote = payload['metadata']['firstLevel']['quotes'] + '- ' + current_time + ' [ ' + text + ' ]\n'
                    payload['metadata']['firstLevel']['quotes'] = quote

                    payload = {**payload, 
                               'filesIds': [],
                                 'post_type': type,
                                    'status': 'draft',
                                    'deletedFiles': [],
                                    'updatedFiles': []
                    }

                    from app.api.resources.services import update_by_id
                    resource = update_by_id(str(resource['_id']), payload, 'beta', [])
                    await update.message.reply_text('Contenido procesado correctamente, se agrega a la lista '+state[update.message.from_user.id]['type'] + ' del usuario '+str(get_username(update)))

                

        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
        )
        logging.getLogger("httpx").setLevel(logging.WARNING)

        # Initialize and run the application
        application = Application.builder().token(bot_token).build()

        conversation = ConversationHandler(
            entry_points=[CommandHandler("start", start_command)],
            states={
                TYPE: [MessageHandler(filters.TEXT, type)],
                SENDING: [MessageHandler(filters.PHOTO | filters.ATTACHMENT | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.ANIMATION, sendig_files),MessageHandler(filters.TEXT & ~filters.COMMAND, sendig_text)],
            },
            fallbacks=[
                CommandHandler("configurar", config_command),
                CommandHandler("ayuda", help_command),
            ],
        )

        application.add_handler(conversation)
        application.run_polling(drop_pending_updates=True)

        mongodb.delete_records('tasks', {'name': 'telegramIntegration.bot', 'status': 'pending'})
        
        return 'ok'

    def activate_settings(self):
        if not os.environ.get('CELERY_WORKER'):
            current = self.get_plugin_settings()
            if current is None:
                return
            
            if 'bot_token' in current:
                if current['bot_token'] != '':
                    has_task = self.has_task('telegramIntegration.bot', 'automatic')
                    if not has_task:
                        task = self.run_telegram_bot.delay(current['bot_token'])
                        self.add_task_to_user(task.id, 'telegramIntegration.bot','automatic', 'msg')

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
    'author': 'Museo Afro',
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