$(function () {
    const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
    const url = protocol + window.location.host + '/ws/chat/' + chat_id + '/';
    
    const buttonSendMessage = document.getElementById('sendMessage');
    const inputMessage = document.getElementById('messageContent');
    const boxMessage = document.getElementById('chat-content');
    
    if (chat_id != ''){
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
            var type = datamsj.type
            addMessage(msj, 'Client', type);
        };

        buttonSendMessage.addEventListener('click', sendMessage);
        inputMessage.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
    }

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

    function addMessage(text, type, typemsj, clientData = {}, messageTime = '2:35 PM') {
        if (type == 'Client') {
            const chatContent = document.createElement('div');
            chatContent.classList.add('chat-content-leftside');
        
            const flexContainer = document.createElement('div');
            flexContainer.classList.add('d-flex');
        
            // Create SVG user icon
            const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
            svg.setAttribute('width', '45');
            svg.setAttribute('height', '45');
            svg.setAttribute('viewBox', '0 0 24 24');
            svg.setAttribute('fill', 'none');
            svg.setAttribute('stroke', 'currentColor');
            svg.setAttribute('stroke-width', '2');
            svg.setAttribute('stroke-linecap', 'round');
            svg.setAttribute('stroke-linejoin', 'round');
            svg.classList.add('feather', 'feather-user');
        
            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
            path.setAttribute('d', 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2');
            
            const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            circle.setAttribute('cx', '12');
            circle.setAttribute('cy', '7');
            circle.setAttribute('r', '4');
        
            svg.appendChild(path);
            svg.appendChild(circle);
        
            // Create content container
            const contentContainer = document.createElement('div');
            contentContainer.classList.add('flex-grow-1', 'ms-2');
        
            // Create time paragraph
            const timeParagraph = document.createElement('p');
            timeParagraph.classList.add('mb-0', 'chat-time');
            const clientName = clientData.name || chat_id;
            timeParagraph.textContent = `${clientName}, ${messageTime}`;
        
            // Create message content
            const messageParagraph = document.createElement('p');
            messageParagraph.classList.add('chat-left-msg');
        
            if (typemsj === 'MMS') {
                const image = document.createElement('img');
                image.src = text;
                image.classList.add('img-responsive');
                image.alt = 'Mensaje multimedia';
                messageParagraph.appendChild(image);
            } else {
                messageParagraph.textContent = text;
            }
        
            // Assemble the components
            contentContainer.appendChild(timeParagraph);
            contentContainer.appendChild(messageParagraph);
        
            flexContainer.appendChild(svg);
            flexContainer.appendChild(contentContainer);
        
            chatContent.appendChild(flexContainer);
            boxMessage.appendChild(chatContent);
        } else {
            // User message (right side)
            const chatContent = document.createElement('div');
            chatContent.classList.add('chat-content-rightside');
    
            const flexContainer = document.createElement('div');
            flexContainer.classList.add('d-flex', 'ms-auto');
    
            // Create content container
            const contentContainer = document.createElement('div');
            contentContainer.classList.add('flex-grow-1', 'me-2');
    
            // Create time paragraph
            const timeParagraph = document.createElement('p');
            timeParagraph.classList.add('mb-0', 'chat-time', 'text-end');
            timeParagraph.textContent = `you, ${messageTime}`;
    
            // Create message content
            const messageParagraph = document.createElement('p');
            if (typemsj === 'MMS') {
                messageParagraph.classList.add('chat-left-msg');
                const image = document.createElement('img');
                image.src = text;
                image.classList.add('img-responsive');
                image.alt = 'Mensaje multimedia';
                messageParagraph.appendChild(image);
            } else {
                messageParagraph.classList.add('chat-right-msg');
                messageParagraph.textContent = text;
            }
    
            // Assemble the components
            contentContainer.appendChild(timeParagraph);
            contentContainer.appendChild(messageParagraph);
    
            flexContainer.appendChild(contentContainer);
            chatContent.appendChild(flexContainer);
            boxMessage.appendChild(chatContent);
        }
    }
});

async function sendFirstMessage(message) {
    const formData = new FormData();
    formData.append('phoneNumber', chat_id);
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
}

// Obtener el formulario cuando el DOM esté cargado
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('newChat');
    const phoneInput = form.querySelector('input[name="phoneNumber"]');

    form.addEventListener('submit', function(event) {
        // Prevenir el envío por defecto
        event.preventDefault();
        
        // Validar el número de teléfono
        const isValid = validatePhoneNumber(phoneInput.value);
        
        if (isValid) {
            // Si es válido, actualizar el valor del input con el formato correcto
            phoneInput.value = isValid;
            // Enviar el formulario
            form.submit();
        } else {
            // Si no es válido, mostrar un mensaje de error
            alert('Por favor, ingresa un número de teléfono válido de 10 dígitos');
            phoneInput.focus();
        }
    });
});
function validatePhoneNumber(phoneNumber) {
    // Eliminar cualquier caracter que no sea número
    const cleanNumber = phoneNumber.toString().replace(/\D/g, '');
    
    // Si el número empieza con 1 y tiene 11 dígitos, es válido
    if (cleanNumber.startsWith('1') && cleanNumber.length === 11) {
        return cleanNumber;
    }
    
    // Si el número tiene exactamente 10 dígitos, agregar 1 al inicio
    if (cleanNumber.length === 10) {
        return '1' + cleanNumber;
    }
    
    // En cualquier otro caso, el número no es válido
    return false;
}

const listChats = document.getElementById('listChats');
const anchorsArray = Array.from(listChats.querySelectorAll('a'));

const searchInput = document.getElementById('searchInput');
searchInput.addEventListener('input', function() {
    anchorsArray.forEach(anchor => {
        if (isSubsequence(searchInput.value.toLowerCase(), anchor.id.toLowerCase())){
            anchor.style.display = 'block'; 
        }else{
            anchor.style.display = 'none';
        }
    });
});

function isSubsequence(sub, str) {
    let subIndex = 0;

    for (let i = 0; i < str.length; i++) {
        if (str[i] === sub[subIndex]) {
            subIndex++;
        }
        if (subIndex === sub.length) {
            return true;
        }
    }
    return false;
}