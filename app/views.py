# Standard library imports
import json
import requests

# Third-party imports
import telnyx
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

# Django imports
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import logging

# Local application imports
from .models import *


# Create your views here.

logger = logging.getLogger('django')

# auth
def login_(request):
    if request.user.is_authenticated:
        return redirect(index)
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(index)
        else:
            msg = 'Datos incorrectos, intente de nuevo'
            return render(request, 'auth/login.html', {'msg':msg})
    else:
        return render(request, 'auth/login.html')
    
def logout_(request):
    logout(request)
    return redirect(index)

@csrf_exempt
def sendMessage(request):
    telnyx.api_key = settings.TELNYX_API_KEY
    telnyx.Message.create(
    from_="+17866931008", # Your Telnyx number
    to=f'+{request.POST['phoneNumber']}',
    text= request.POST['messageContent']
    )
    client = createOrUpdateClient(request.POST['phoneNumber'])
    chat = createOrUpdateChat(client, request.user)
    saveMessageInDb('Agent', request.POST['messageContent'], chat, request.user)
    
    return JsonResponse({'ok':'ok'})

@csrf_exempt
# @require_POST
def sms(request):
    logger.debug('UwU:LLego el post bby')
    try:
        body = json.loads(request.body)
        
        # Imprimir el cuerpo completo
        # print("Cuerpo completo de la solicitud:")
        # print(json.dumps(body, indent=2))
        
        # Acceder a datos específicos
        if 'data' in body and 'payload' in body['data']:
            payload = body['data']['payload']
            if body['data'].get('event_type') == 'message.received':
                client = createOrUpdateClient(int(payload.get('from', {}).get('phone_number')))
                chat = createOrUpdateChat(client)
                message = saveMessageInDb('Client', payload.get('text'), chat)

                if payload.get('type') == 'MMS':
                    media = payload.get('media', [])
                    if media:
                        media_url = media[0].get('url')
                        fileUrl = save_image_from_url(message, media_url)
                        SendMessageWebsocketChannel('MMS', payload, client, fileUrl)
                else:
                    SendMessageWebsocketChannel('SMS', payload, client)

            return HttpResponse("Webhook recibido correctamente", status=200)
    except json.JSONDecodeError:
        logger.debug("UwU:Error al decodificar JSON")
        return HttpResponse("Error en el formato JSON", status=400)
    except Exception as e:
        logger.debug(f"UwU:Error inesperado: {str(e)}")
        return HttpResponse("Error interno del servidor", status=500)

def SendMessageWebsocketChannel(typeMessage, payload, client, mediaUrl=None):
    # Enviar mensaje al canal de WebSocket
    channel_layer = get_channel_layer()
    logger.debug('UwU:Intento enviar el mensaje al websocket')
    logger.debug(f"Intentando enviar mensaje - Tipo: {typeMessage}")
    logger.debug(f"Cliente: {client.phone_number}")
    logger.debug(f"Payload: {payload}")
    logger.debug(f"MediaUrl: {mediaUrl}")
    if typeMessage == 'MMS':
        async_to_sync(channel_layer.group_send)(
            f'chat_{client.phone_number}',  # Asegúrate de que este formato coincida con tu room_group_name
            {
                'type': typeMessage,
                'message': mediaUrl,
                'username': f"Cliente {client.phone_number}",  # O como quieras identificar al cliente
                'datetime': timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M:%S'),
                'sender_id': True  # O cualquier identificador único que uses
            }
        )
    else:
        async_to_sync(channel_layer.group_send)(
            f'chat_{client.phone_number}',  # Asegúrate de que este formato coincida con tu room_group_name
            {
                'type': 'chat_message',
                'message': payload.get('text'),
                'username': f"Cliente {client.phone_number}",  # O como quieras identificar al cliente
                'datetime': timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M:%S'),
                'sender_id': True  # O cualquier identificador único que uses
            }
        )
        
    logger.debug('UwU:No fallo en el intento jaja XD')
    
def saveMessageInDb(inboundOrOutbound, message_content, chat, sender=None):
    message = Messages(
        sender_type=inboundOrOutbound,
        message_content=message_content,
        chat=chat,
    )
    if sender:
        message.sender = sender
    message.save()
    return message
    
def createOrUpdateChat(client, agent=None):
    try:
        chat = Chat.objects.get(client_id=client.id)
        if agent:
            chat.agent = agent
            chat.save()
    except Chat.DoesNotExist:
        if not agent:
            agent = Users.objects.get(id=2)
        chat = Chat(
            agent=agent,
            client=client
        )
        chat.save()
    return chat

def createOrUpdateClient(phoneNumber, name=None):
    try:
        client = Clients.objects.get(phone_number=phoneNumber)
        if name:
            client.name = name
            client.save()
    except Clients.DoesNotExist:
        client = Clients(
            phone_number=phoneNumber
        )
        client.save()
    return client

@login_required(login_url='/login')
def index(request):
    logger.debug('UwU:REGUETON')

    clients = Clients.objects.all()
    return render(request, 'sms/index.html', {'clients':clients})

@login_required(login_url='/login')
def chat(request, phoneNumber):
    client = Clients.objects.get(phone_number=phoneNumber)
    chat = Chat.objects.get(client=client.id)
    # Usamos select_related para optimizar las consultas
    messages = Messages.objects.filter(chat=chat.id).select_related('files')
    
    # Creamos una lista para almacenar los mensajes con sus archivos
    messages_with_files = []
    for message in messages:
        message_dict = {
            'id': message.id,
            'sender_type': message.sender_type,
            'sender': message.sender,
            'message_content': message.message_content,
            'created_at': message.created_at,
            'is_read': message.is_read,
            'file': None
        }
        
        # Intentamos obtener el archivo asociado
        try:
            message_dict['file'] = message.files
        except Files.DoesNotExist:
            pass
            
        messages_with_files.append(message_dict)

    clients = Clients.objects.all()
    context = {
        'client': client,
        'clients': clients,
        'messages': messages_with_files
    }
    return render(request, 'sms/index.html', context)

@login_required(login_url='/login')
def chat_messages(request, phone_number):
    chat = Chat.objects.get(client__phone_number=phone_number, agent=request.user)
    messages = Messages.objects.filter(chat=chat).order_by('created_at')
    return JsonResponse([{
        'message': msg.message_content,
        'sender_type': msg.sender_type,
        'timestamp': msg.created_at.isoformat()
    } for msg in messages], safe=False)

def save_image_from_url(message, url):
    try:        
        # Descargar la imagen
        response = requests.get(url)
        response.raise_for_status()
        
        filename = url.split('/')[-1]

        file = Files()
        file.message = message
        file.file.save(filename, ContentFile(response.content), save=True)

        return file.file.url
        
    except Exception as e:
        print(f'Error {e}')