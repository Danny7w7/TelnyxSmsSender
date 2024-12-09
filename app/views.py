# Standard library imports
from datetime import datetime, timedelta
from decimal import Decimal
import json
import requests
import smtplib

# Third-party imports
import telnyx
import stripe
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

# Django imports
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.signing import Signer, BadSignature
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.utils.timezone import timedelta
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.hashers import make_password
import logging

# Local application imports
from .models import *
from .utils.email_sender import *

# Create your views here.
logger = logging.getLogger('django')

# auth
def login_(request):
    if request.user.is_authenticated:
        return redirect(index)
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        try:
            user = Users.objects.get(username=username)
            if not user.is_active:
                error_message = "Your account is disabled. Please contact support."
            else:
                user = authenticate(request, username=username, password=password)
                if user is not None:
                    login(request, user)
                    return redirect('index')
                else:
                    error_message = "Invalid password."
        except Users.DoesNotExist:
            error_message = "User does not exist."
        
        return render(request, 'auth/login.html', {'error_message': error_message})
    
    return render(request, 'auth/login.html')
    
def logout_(request):
    logout(request)
    return redirect(index)

@csrf_exempt
def sendMessage(request):
    if comprobate_company(request.user.company):
        return JsonResponse({'message':'No money'})
    telnyx.api_key = settings.TELNYX_API_KEY
    telnyx.Message.create(
        from_=f"+{request.user.assigned_phone.phone_number}", # Your Telnyx number
        to=f'+{request.POST['phoneNumber']}',
        text= request.POST['messageContent']
    )
    client = createOrUpdateClient(request.POST['phoneNumber'], request.user.company)
    if request.user.role == 'Customer':
        chat = createOrUpdateChat(client, request.user.company)
    else:
        chat = createOrUpdateChat(client, request.user.company, request.user)
    saveMessageInDb('Agent', request.POST['messageContent'], chat, request.user)
    
    return JsonResponse({'message':'ok'})

@csrf_exempt
@require_POST
def sms(request, company_id):
    try:
        body = json.loads(request.body)
        company = Companies.objects.get(id=company_id)
        
        # Imprimir el cuerpo completo
        # print("Cuerpo completo de la solicitud:")
        # print(json.dumps(body, indent=2))
        
        # Acceder a datos específicos
        if 'data' in body and 'payload' in body['data']:
            payload = body['data']['payload']
            if body['data'].get('event_type') == 'message.received':
                client, created = createOrUpdateClient(int(payload.get('from', {}).get('phone_number')), company)
                chat = createOrUpdateChat(client, company)
                message = saveMessageInDb('Client', payload.get('text'), chat)
                
                if not client.is_active:
                    activateClient(client, payload.get('text'))

                if payload.get('type') == 'MMS':
                    media = payload.get('media', [])
                    if media:
                        media_url = media[0].get('url')
                        fileUrl = save_image_from_url(message, media_url)
                        SendMessageWebsocketChannel('MMS', payload, client, fileUrl)
                        if company.id != 1:
                            discountRemainingBalance(company, '0.027')
                        
                else:
                    SendMessageWebsocketChannel('SMS', payload, client)
                    if company.id != 1:
                        discountRemainingBalance(company, '0.025')

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
    # logger.debug('UwU:Intento enviar el mensaje al websocket')
    # logger.debug(f"Intentando enviar mensaje - Tipo: {typeMessage}")
    # logger.debug(f"Cliente: {client.phone_number}")
    # logger.debug(f"Payload: {payload}")
    # logger.debug(f"MediaUrl: {mediaUrl}")
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
    
def createOrUpdateChat(client, company, agent=None):
    try:
        # Intenta obtener un chat existente para el cliente en la empresa especificada
        chat = Chat.objects.get(client_id=client.id, company_id=company.id)

        # Si se proporciona un nuevo agente, actualiza el chat
        if agent:
            chat.agent = agent
            chat.save()

    except Chat.DoesNotExist:
        # Si el chat no existe, crea uno nuevo
        if not agent:
            # Define un agente por defecto si no se proporciona (opcional)
            agent = Users.objects.get(id=2)  # ID de un agente genérico

        chat = Chat(
            agent=agent,
            client=client,
            company=company  # Asocia el chat con la compañía
        )
        chat.save()

    return chat

def createOrUpdateClient(phoneNumber, company, name=None):
    # Intenta obtener o crear un cliente
    client, created = Clients.objects.get_or_create(
        phone_number=phoneNumber,
        company=company,
        defaults={
            'name': name,
            'is_active': False
            }
    )
    if not created and name:
        # Si el cliente ya existía y se proporcionó un nombre, actualizamos el nombre
        client.name = name
        client.save()
        created = False  # El cliente no fue creado, solo actualizado
    return client, created

def deleteClient(request, id):
    if request.user.is_superuser:
        client = Clients.objects.get(id=id)
        client.delete()
    return redirect(index)

def activateClient(client, message):
    message_upper = message.upper()
    if 'YES' in message_upper or 'SI' in message_upper:
        client.is_active = True
        client.save()
        print(f'Cliente {client} activado.')
    else:
        print('El mensaje no contiene "YES". No se activa al cliente.')

@login_required(login_url='/login')
def index(request):
    if request.user.is_staff:
        chats = Chat.objects.select_related('client').filter(company=request.user.company).order_by('-last_message')
    else:
        chats = Chat.objects.select_related('client').filter(agent_id=request.user.id).order_by('-last_message')
    chats = get_last_message_for_chats(chats)

    if request.method == 'POST':
        phoneNumber = request.POST.get('phoneNumber')
        name = request.POST.get('name', None)
        client, created = createOrUpdateClient(phoneNumber, request.user.company, name)
        chat = createOrUpdateChat(client, request.user.company, request.user)
        if created:
            if request.POST.get('language') == 'english':
                message = "Reply YES to receive updates and information about your policy from Lapeira & Associates LLC. Msg & data rates may apply. Up to 5 msgs/month. Reply STOP to opt-out at any time."
            else: 
                message = "Favor de responder SI para recibir actualizaciones e información sobre su póliza de Lapeira & Associates LLC. Pueden aplicarse tarifas estándar de mensaje y datos. Hasta 5 mensajes/mes. Responder STOP para cancelar en cualquier momento."
            sendIndividualsSms(
                request.user.assigned_phone.phone_number,
                phoneNumber,
                request.user,
                request.user.company,
                message
            )
        return redirect('chat', client.phone_number)
    return render(request, 'sms/index.html', {'chats': chats})

@login_required(login_url='/login')
def chat(request, phoneNumber):
    if request.method == 'POST':
        phoneNumber = request.POST.get('phoneNumber')
        name = request.POST.get('name', None)
        client = createOrUpdateClient(phoneNumber, request.user.company, name)
        chat = createOrUpdateChat(client, request.user.company, request.user)
        return redirect('chat', client.phone_number)
    
    client = Clients.objects.get(phone_number=phoneNumber, company=request.user.company)
    chat = Chat.objects.get(client=client.id, company=request.user.company)
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
        chats = Chat.objects.select_related('client').filter(company=request.user.company).order_by('-last_message')
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

def sendIndividualsSms(from_number, to_number, user, company, message_context):
    telnyx.api_key = settings.TELNYX_API_KEY
    telnyx.Message.create(
        from_=f"+{from_number}", # Your Telnyx number
        to=f'+{to_number}',
        text= message_context
    )
    client, created = createOrUpdateClient(to_number, company)
    chat = createOrUpdateChat(client, company)
    saveMessageInDb('Agent', message_context, chat, user)
    
    return True

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
    saveMessageInDb('Agent', 'Link to secret key sent', chat, request.user)
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

    saveMessageInDb('Agent', 'Secret key creation link sent', chat, request.user)
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

def payment_type(request, type, company_id):
    if type == 'Thank-You-Page':
        return render(request, 'email_templates/thank_you_page.html')
    elif type == 'Payment-Error':
        context = {
            'retry_payment_url': create_stripe_checkout_session(company_id)
        }
        return render(request, 'email_templates/payment_error.html', context)

stripe.api_key = settings.STRIPE_SECRET_KEY
def create_stripe_checkout_session(company_id):
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': 'price_1QSSDDHakpVhxYcD1d0EM7XV',
                    'quantity': 1,
                },
            ],
            mode='payment',
            success_url=f"{settings.DOMAIN}/payment/Thank-You-Page/{company_id}/",
            cancel_url=f"{settings.DOMAIN}/payment/Payment-Error/{company_id}/",
            automatic_tax={'enabled': True},
            metadata={
                'company_id': company_id
            }
        )
        return checkout_session.url
    except stripe.error.StripeError as e:
        raise Exception(f"Stripe error: {str(e)}")
    except Exception as e:
        raise Exception(f"Unexpected error: {str(e)}")
                                             
@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET  # Configura esto en tu cuenta de Stripe

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return JsonResponse({'error': 'Invalid signature'}, status=400)

    # Manejar el evento
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']  # Sesión completada
        company_id = session['metadata']['company_id']
        amount = format_number(session['amount_total'])

        company = Companies.objects.get(id=company_id)
        company.remaining_balance += amount
        company.save()

        send_email(
            subject=f"✅ Confirmación de Pago en SMS Blue - {company.company_name}",
            receiver_email=company.company_email,
            template_name="email_templates/payment_confirmation",
            context_data={
                "Owner_name": company.owner,
                "company": company.company_name,
                "payment_amount":amount,
                "current_balance": f'{company.remaining_balance:.2f}',
                "payment_date": timezone.now().strftime('%d/%m/%Y %H:%M:%S')
            }
        )

        # Aquí puedes actualizar tu base de datos, enviar correos, etc.

    return JsonResponse({'status': 'success'})

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

def comprobate_company(company):
    if company.id == 1: #No descuenta el saldo a Lapeira
        return False
    if company.remaining_balance <= 0:
        disableAllUserCompany(company)
        return True
    else:
        discountRemainingBalance(company, '0.035')
        paymend_recording(company)
        return False

def discountRemainingBalance(companyObject, discount):
    companyObject.remaining_balance -= Decimal(discount)
    companyObject.save()

def disableAllUserCompany(companyObject):
    usersCompany = Users.objects.filter(role=companyObject.user_role)
    send_email(
        subject=f"Tu cuenta SMS Blue ha sido desactivada por saldo insuficiente",
        receiver_email=companyObject.company_email,
        template_name="email_templates/service_cancelled",
        context_data={
            "Owner_name": companyObject.owner,
            "company": companyObject.company_name,
            "remaining_balance": f'{companyObject.remaining_balance:.2f}',
            "url_pay": create_stripe_checkout_session(companyObject.id)
        }
    )

    for user in usersCompany:
        user.is_active = 0
        user.save()

def paymend_recording(company):
    def format_mail_recording(company):
        send_email(
            subject=f"Tu saldo en SMS Blue es de {company.remaining_balance:.2f} USD. No te quedes sin servicio",
            receiver_email=company.company_email,
            template_name="email_templates/payment_reminder",
            context_data={
                "Owner_name": company.owner,
                "company": company.company_name,
                "remaining_balance": f'{company.remaining_balance:.2f}',
                "url_pay": create_stripe_checkout_session(company.id)
            }
        )

    if company.remaining_balance <= 10 and not company.notified_at_10:
        format_mail_recording(company)
        company.notified_at_10 = True
        company.save()
    
    if company.remaining_balance <= 5 and not company.notified_at_5:
        format_mail_recording(company)
        company.notified_at_5 = True
        company.save()
    
    if company.remaining_balance <= 1 and not company.notified_at_1:
        format_mail_recording(company)
        company.notified_at_1 = True
        company.save()

def format_number(number):
    return Decimal(number) / Decimal(100)

# Admin
def admin(request):
    if not request.user.is_staff:
        return redirect('index')
    # Obtener la fecha actual
    now = datetime.now()
    seven_days_ago = now - timedelta(days=6)

    # Obtener usuarios de la compañia
    company_users = Users.objects.filter(company=request.user.company)
    company = Companies.objects.get(id=request.user.company.id)

    # Filtrar mensajes de los últimos 7 días y asociados a chats de usuarios
    messages = Messages.objects.filter(
        chat__agent__in=company_users,
        created_at__gte=seven_days_ago
    )

    # Diccionario para los días de la semana
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    result = {day_name: 0 for day_name in day_names}

    # Agrupar los mensajes usando el día de la semana
    for message in messages:
        message_day = message.created_at.weekday()  # Obtiene el día de la semana (0=Monday, 6=Sunday)
        day_name = day_names[message_day]
        result[day_name] += 1

    context = {
        'day_names':json.dumps(day_names),
        'messages':json.dumps(result),
        "url_recharge": create_stripe_checkout_session(company.id),
        "company":company,
        "message_count":messages.count()
    }
    return render(request, 'admin/admin.html', context)