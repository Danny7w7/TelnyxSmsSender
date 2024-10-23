const phoneInput = document.getElementById('phoneInput');
const phoneList = document.getElementById('phoneList');
const phones = new Set();

function addPhone(phone) {
    if (phone && !phones.has(phone)) {
        phones.add(phone);
        const tag = document.createElement('span');
        tag.className = 'phone-tag';
        tag.innerHTML = `${phone}<span class="remove-phone">&times;</span>`;
        tag.querySelector('.remove-phone').addEventListener('click', () => {
            phones.delete(phone);
            phoneList.removeChild(tag);
        });
        phoneList.appendChild(tag);
    }
}

phoneInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ',' || e.key === ' ') {
        e.preventDefault();
        const phone = phoneInput.value.trim();
        if (phone) {
            addPhone(phone);
            phoneInput.value = '';
        }
    }
});

phoneInput.addEventListener('blur', () => {
    const phone = phoneInput.value.trim();
    if (phone) {
        addPhone(phone);
        phoneInput.value = '';
    }
});

// Hasta aqui llega el script del input multiple de los numeros

$(function () {
    var url = 'ws://' + window.location.host + '/ws/chat/' + chat_id + '/';
    
    const buttonSendMessage = document.getElementById('sendMessage');
    const inputMessage = document.getElementById('messageContent');
    const boxMessage = document.getElementById('boxMessage');
    if (chat_id != '') {
        var chatSocket = new WebSocket(url);

        chatSocket.onopen = function (e) {
            console.log('webSocket abierto');
        };

        chatSocket.onclose = function (e) {
            console.log('webSocket cerrado');
        };

        chatSocket.onmessage = function (data) {
            const datamsj = JSON.parse(data.data);
            var msj = datamsj.message;
            var username = datamsj.username;
            var datetime = datamsj.datetime;

            addMessage(msj, 'recieve');
        };

        buttonSendMessage.addEventListener('click', sendMessage);
        inputMessage.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });

        function sendMessage() {
            const message = inputMessage.value.trim();
            if (message) {
                chatSocket.send(JSON.stringify({
                    message: message
                }));
                sendFirstMessage(message)
                addMessage(message, 'Agent');
                inputMessage.value = ''; // Limpiar el input después de enviar
            } else {
                console.log('El mensaje está vacío');
            }
        }

        function addMessage(text, type) {
            const newMessage = document.createElement('p');
            newMessage.classList.add(type);
            newMessage.textContent = text;
            boxMessage.appendChild(newMessage);
        }
    } else {        
        // Asignar la función correctamente
        buttonSendMessage.addEventListener('click', function() {
            sendFirstMessage(inputMessage.value);
        });

        inputMessage.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                sendFirstMessage(inputMessage.value);
            }
        });
    }
});

async function sendFirstMessage(message) {
    // Convertir el Set a un Array para usar map
    const fetchPromises = Array.from(phones).map(phoneNumber => {
        const formData = new FormData();
        formData.append('phoneNumber', phoneNumber);
        formData.append('messageContent', message);

        return fetch('/sendMessage/', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            console.log('Success:', data);
            return data;
        })
        .catch((error) => {
            console.error('Error:', error);
            throw error;
        });
    });

    try {
        // Esperar a que todos los fetch se completen
        await Promise.all(fetchPromises);
        
        // Agregar un delay de 1 segundo
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // Obtener el primer número de teléfono del Set
        const firstPhone = Array.from(phones)[0];

        if (chat_id == '') {
            window.location.href = `/chat/${firstPhone}/`;
        }
    } catch (error) {
        console.error('Error en el proceso:', error);
    }
}