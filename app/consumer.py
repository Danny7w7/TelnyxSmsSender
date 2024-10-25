import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['chat_id']
        self.room_group_name = f'chat_{self.room_name}'
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):

        try:
            text_data_json = json.loads(text_data)
            message = text_data_json['message']

            # Obtenemos el ID del usuario que envía el mensaje
            if self.scope['user'].is_authenticated:
                sender_id = self.scope['user'].id
                username = self.scope['user'].username
            else:
                sender_id = None
                username = 'Anonymous'

            # if sender_id:
            #     # Enviar mensaje al grupo de la sala
            #     await self.channel_layer.group_send(
            #         self.room_group_name,
            #         {
            #             'type': 'chat_message',
            #             'message': message,
            #             'username': username,
            #             'datetime': timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M:%S'),
            #             'sender_id': sender_id
            #         }
            #     )
            # else:
            #     # Manejar el caso de usuario no autenticado si es necesario
            #     pass

        except json.JSONDecodeError:
            print("Error decodificando JSON")
        except KeyError:
            print("Error: 'message' no encontrado en los datos")

    async def chat_message(self, event):
        message = event['message']
        username = event['username']
        datetime = event['datetime']
        sender_id = event['sender_id']
        
        current_user_id = self.scope['user'].id if self.scope['user'].is_authenticated else None
        
        await self.send(text_data=json.dumps({
            'type': 'SMS',
            'message': message,
            'username': username,
            'datetime': datetime,
            'is_sms': isinstance(sender_id, str)
        }))

    async def MMS(self, event):
        message = event['message']  # Esta será la URL del medio
        username = event['username']
        datetime = event['datetime']
        sender_id = event['sender_id']
        
        current_user_id = self.scope['user'].id if self.scope['user'].is_authenticated else None
        
        await self.send(text_data=json.dumps({
            'type': 'MMS',
            'message': message,
            'username': username,
            'datetime': datetime,
            'is_sms': isinstance(sender_id, str),
            'media_url': message  # Incluimos la URL del medio en el mensaje
        }))