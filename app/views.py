# Standard library imports
from datetime import timedelta
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
from django.core.signing import Signer, BadSignature
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.hashers import make_password
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
    from_=f"+{request.user.assigned_phone.phone_number}", # Your Telnyx number
    to=f'+{request.POST['phoneNumber']}',
    text= request.POST['messageContent']
    )
    client = createOrUpdateClient(request.POST['phoneNumber'])
    chat = createOrUpdateChat(client, request.user)
    saveMessageInDb('Agent', request.POST['messageContent'], chat, request.user)
    
    return JsonResponse({'ok':'ok'})

@csrf_exempt
@require_POST
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
        message.is_read = True
    else:
        message.is_read = False

    message.save()
    
    #Upload last message
    chat.last_message = timezone.localtime(timezone.now())
    chat.save()
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
            phone_number=phoneNumber,
            name=name
        )
        client.save()
    return client

def deleteClient(request ,id):
    if request.user.is_superuser:
        client = Clients.objects.get(id=id)
        client.delete()
    return redirect(index)

@login_required(login_url='/login')
def index(request):
    if request.user.is_superuser:
        chats = Chat.objects.select_related('client').all().order_by('-last_message')
    else:
        chats = Chat.objects.select_related('client').filter(agent_id=request.user.id).order_by('-last_message')
    chats = get_last_message_for_chats(chats)

    if request.method == 'POST':
        phoneNumber = request.POST.get('phoneNumber')
        name = request.POST.get('name', None)
        client = createOrUpdateClient(phoneNumber, name)
        chat = createOrUpdateChat(client, request.user)
        return redirect('chat', client.phone_number)
    return render(request, 'sms/index.html', {'chats': chats})

@login_required(login_url='/login')
def chat(request, phoneNumber):
    if request.method == 'POST':
        phoneNumber = request.POST.get('phoneNumber')
        name = request.POST.get('name', None)
        client = createOrUpdateClient(phoneNumber, name)
        chat = createOrUpdateChat(client, request.user)
        return redirect('chat', client.phone_number)
    
    client = Clients.objects.get(phone_number=phoneNumber)
    chat = Chat.objects.get(client=client.id)
    secretKey = SecretKey.objects.filter(client=client).filter()
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
        
        message.is_read = True
        message.save()

        # Intentamos obtener el archivo asociado
        try:
            message_dict['file'] = message.files
        except Files.DoesNotExist:
            pass
            
        messages_with_files.append(message_dict)

    if request.user.is_superuser:
        chats = Chat.objects.select_related('client').all().order_by('-last_message')
    else:
        chats = Chat.objects.select_related('client').filter(agent_id=request.user.id).order_by('-last_message')
    chats = get_last_message_for_chats(chats)
    context = {
        'client': client,
        'chats': chats,
        'messages': messages_with_files,
        'secretKey':secretKey
    }
    return render(request, 'sms/chat.html', context)

def sendSecretKey(request, client_id):
    client = Clients.objects.get(id=client_id)
    secretKey = SecretKey.objects.get(client=client)
    chat = Chat.objects.get(client=client)

    telnyx.api_key = settings.TELNYX_API_KEY
    telnyx.Message.create(
    from_=f"+17869848405", # Your Telnyx number
    to=f'+{client.phone_number}',
    text=generate_temporary_url(request, client, secretKey.secretKey)
    )
    saveMessageInDb('Agent', 'Link to secret key sent', chat, chat.agent)
    return redirect('chat', client.phone_number)

def sendCreateSecretKey(request, id):
    client = Clients.objects.get(id=id)
    chat = Chat.objects.get(client=client)
    telnyx.api_key = settings.TELNYX_API_KEY
    telnyx.Message.create(
    from_=f"+17869848405", # Your Telnyx number
    to=f'+{client.phone_number}',
    text= generate_temporary_url(request, client)
    )

    saveMessageInDb('Agent', 'Secret key creation link sent', chat, chat.agent)
    return redirect('chat', client.phone_number)

def createSecretKey(request):
    result = validate_temporary_url(request)
    is_valid, note, *client = result

    #Aqui valido si es valido el token, si no que retorne el mensaje de error
    if not is_valid:
        return HttpResponse(note)

    if request.method == 'POST':
        secret_key_request = request.POST['secret_key']

        # Verifica si existe un SecretKey para el cliente
        secret_key = SecretKey.objects.filter(client=client[0].id).first()
        if not secret_key:
            secret_key = SecretKey()
            secret_key.client = client[0]
        secret_key.secretKey = secret_key_request
        secret_key.save()

        invalidate_temporary_url(request, note) #Aqui el note equivale al Token
        return render(request, 'secret_key/create_secret_key.html', {'secret_key':secret_key_request})
    
    token = request.GET.get('token')

    signer = Signer()   
    signed_data = force_str(urlsafe_base64_decode(token))
    data = json.loads(signer.unsign(signed_data))

    secret_key = data.get('secret_key')

    return render(request, 'secret_key/create_secret_key.html', {'secret_keyG':secret_key})

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

def get_last_message_for_chats(chats):
    """
    Función que enriquece los chats con información del último mensaje
    y cuenta los mensajes no leídos
    """
    for chat in chats:
        # Obtener el último mensaje del chat
        last_message = Messages.objects.filter(chat=chat).order_by('-created_at').first()
        
        # Contar mensajes no leídos
        unread_count = Messages.objects.filter(
            chat=chat,
            is_read=False,
            sender_type='Client'  # Solo mensajes del cliente
        ).count()
        
        # Si existe último mensaje, agregar atributos personalizados
        if last_message:
            # Truncar el mensaje a 27 caracteres
            content = last_message.message_content
            if len(content) > 24:
                content = content[:24] + "..."

            chat.last_message_content = content
            chat.last_message_time = last_message.created_at
            chat.has_attachment = hasattr(last_message, 'files')
            chat.is_message_unread = not last_message.is_read
        else:
            chat.last_message_content = "No hay mensajes"
            chat.last_message_time = None
            chat.has_attachment = False
            chat.is_message_unread = False
        
        # Agregar contador de mensajes no leídos
        chat.unread_messages = unread_count
    
    return chats

from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str

# Vista para generar el enlace temporal
def generate_temporary_url(request, client, secret_key=None):
    signer = Signer()

    # Define una fecha de expiración (por ejemplo, 1 hora desde ahora)
    expiration_time = timezone.now() + timedelta(minutes=10)

    # Crear el token con la fecha de expiración usando JSON
    data = {
        'client_id': client.id,
        'phone_number': client.phone_number,
        'expiration': expiration_time.isoformat(),
    }
    if secret_key:
        data['secret_key'] = secret_key
    signed_data = signer.sign(json.dumps(data))  # Firmar los datos serializados
    token = urlsafe_base64_encode(force_bytes(signed_data))  # Codificar seguro para URL

    # Guardar la URL temporal en la base de datos
    TemporaryURL.objects.create(
        client=client,
        token=token,
        expiration=expiration_time
    )
    if secret_key:
        temporary_url = f"{request.build_absolute_uri('/secret-key/')}?token={token}"
    else:
        temporary_url = f"{request.build_absolute_uri('/secret-key/')}?token={token}"

    # Crear la URL temporal

    return temporary_url

# Vista para verificar y procesar la URL temporal
def validate_temporary_url(request):
    token = request.POST.get('token') or request.GET.get('token')

    if not token:
        return False, 'Token no proporcionado. Not found token.'

    signer = Signer()
    
    try:
        signed_data = force_str(urlsafe_base64_decode(token))
        data = json.loads(signer.unsign(signed_data))

        client_id = data.get('client_id')
        expiration_time = timezone.datetime.fromisoformat(data['expiration'])
        # Verificar si el token está activo y no ha expirado
        temp_url = TemporaryURL.objects.get(token=token, client_id=client_id)

        if not temp_url.is_active:
            return False, 'Enlace desactivado. Link deactivated.'

        if temp_url.is_expired():
            return False, 'Enlace ha expirado. Link expired.'

        # Procesar si la URL es válida
        client = temp_url.client
        
        return True, token, client
    
    except (BadSignature, ValueError, KeyError):
        return False, 'Token inválido o alterado. Invalid token.'
        
def invalidate_temporary_url(request, token):
    try:
        temp_url = TemporaryURL.objects.get(token=token)
        temp_url.is_active = False
        temp_url.save()
    except TemporaryURL.DoesNotExist:
        print("Esta URL temporal no existe chamo")
# Admin
