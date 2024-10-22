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

            addMessage(msj, 'receive');
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
                addMessage(message, 'send');
                chatSocket.send(JSON.stringify({
                    message: message
                }));
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
        console.log('Estas entrando?');
        
        // Asignar la función correctamente
        buttonSendMessage.addEventListener('click', function() {
            sendFirstMessage(inputMessage.value);
        });

        phones.forEach(element => {
            console.log('Entro aqui');
            console.log(element);
        });

        inputMessage.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                sendFirstMessage(inputMessage.value);
            }
        });
    }
});

function sendFirstMessage(message) {
    phones.forEach(phoneNumber => {
        const formData = new FormData();
        formData.append('phoneNumber', phoneNumber);
        formData.append('messageContent', message);

        // Realizar el fetch para enviar el FormData
        fetch('/sendMessage/', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            console.log('Success:', data);
        })
        .catch((error) => {
            console.error('Error:', error);
        });
    });
}
