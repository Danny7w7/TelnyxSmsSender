from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from storages.backends.s3boto3 import S3Boto3Storage

# Create your models here.

class Numbers(models.Model):
    phone_number = models.BigIntegerField()

#Lo declaro por si en un momento se llega a modificar la tabla User.
class Users(AbstractUser):
    ROLES_CHOICES = (
        ('A', 'Agent'),
        ('S', 'Supervisor'),
        ('Admin', 'Admin'),
    )
    assigned_phone = models.ForeignKey(Numbers, on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLES_CHOICES)

    def __str__(self):
        return self.username
    
    def formatted_phone_number(self):
        if self.assigned_phone and self.assigned_phone.phone_number:
            phone_str = str(self.assigned_phone.phone_number)
            formatted = f"+{phone_str[0]} ({phone_str[1:4]}) {phone_str[4:7]} {phone_str[7:]}"
            return formatted
        return None
    
class Clients(models.Model):
    name = models.CharField(max_length=50, null=True)
    phone_number = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    update_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name} - {self.phone_number}'

class SecretKey(models.Model):
    client = models.OneToOneField(Clients, on_delete=models.CASCADE)
    secretKey = models.CharField(max_length=200)

class TemporaryURL(models.Model):
    client = models.ForeignKey(Clients, on_delete=models.CASCADE)
    token = models.TextField()  # Guardar el token firmado
    expiration = models.DateTimeField()
    is_active = models.BooleanField(default=True)  # Para invalidar manualmente

    def is_expired(self):
        return timezone.now() > self.expiration

    def __str__(self):
        return f"Temporary URL for {self.client.name} (Active: {self.is_active})"

class Chat(models.Model):
    agent = models.ForeignKey(Users, on_delete=models.CASCADE)
    client = models.ForeignKey(Clients, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message = models.DateTimeField(null=True)
    
    def __str__(self):
        return f'{self.agent.username} - {self.client.phone_number}'

class Messages(models.Model):
    SENDER_TYPE_CHOICES = (
        ('A', 'Agent'),
        ('C', 'Client'),
    )
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE)
    sender_type = models.CharField(max_length=20, choices=SENDER_TYPE_CHOICES)
    sender = models.ForeignKey(Users, on_delete=models.CASCADE, null=True)
    message_content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

class Files(models.Model):
    file = models.FileField(
        upload_to='files',
        storage=S3Boto3Storage()
    )
    message = models.OneToOneField(Messages, on_delete=models.CASCADE)