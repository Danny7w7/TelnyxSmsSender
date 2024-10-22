from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout

from .models import *
from django.http import HttpResponse, JsonResponse

from django.conf import settings

from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

import json
from django.views.decorators.http import require_POST

import telnyx
# Create your views here.

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
    
@login_required(login_url='/login')
def index(request):
    return render(request, 'sms/index.html')

@csrf_exempt
def sendMessage(request):
    telnyx.api_key = settings.TELNYX_API_KEY
    telnyx.Message.create(
    from_="+17866931008", # Your Telnyx number
    to=request.POST['phoneNumber'],
    text= request.POST['messageContent']
    )
    client = createOrUpdateClient(request.POST['phoneNumber'])
    chat = createOrUpdateChat(client, request.user)
    saveMessageInDb('Agent', request.POST['messageContent'], chat, request.user)
    
    return JsonResponse({'ok':'ok'})

@csrf_exempt
@require_POST
def sms(request):
    try:
        # Parsear el cuerpo JSON de la solicitud
        body = json.loads(request.body)
        
        # Imprimir el cuerpo completo
        # print("Cuerpo completo de la solicitud:")
        # print(json.dumps(body, indent=2))
        
        # Acceder a datos específicos
        if 'data' in body and 'payload' in body['data']:
            payload = body['data']['payload']
            if body['data'].get('event_type') == 'message.received':
                print('Por lo menos aqui si esta entrando negro')
                client = createOrUpdateClient(int(payload.get('from', {}).get('phone_number')))
                chat = createOrUpdateChat(client)
                saveMessageInDb('Client', payload.get('text'), chat)
        
        return HttpResponse("Webhook recibido correctamente", status=200)
    except json.JSONDecodeError:
        print("Error al decodificar JSON")
        return HttpResponse("Error en el formato JSON", status=400)
    except Exception as e:
        print(f"Error inesperado: {str(e)}")
        return HttpResponse("Error interno del servidor", status=500)
    
def saveMessageInDb(inboundOrOutbound, message_content, chat, sender=None):
    message = Messages(
        sender_type=inboundOrOutbound,
        message_content=message_content,
        chat=chat,
    )
    if sender:
        message.sender = sender
    message.save()
    
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
    print(f'Al final cliente quedo como {client}')
    return client

@login_required(login_url='/login')
def index(request):
    clients = Clients.objects.all()
    return render(request, 'sms/index.html', {'clients':clients})

@login_required(login_url='/login')
def chat(request, phoneNumber):
    client = Clients.objects.get(phone_number=phoneNumber) 
    chat = Chat.objects.get(client=client.id)
    messages = Messages.objects.filter(chat=chat.id)
    print(chat)
    clients = Clients.objects.all()
    context = {
        'client':client,
        'clients':clients,
        'messages':messages
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