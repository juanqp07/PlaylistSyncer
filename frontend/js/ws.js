
export class WebSocketClient {
    constructor(url, callbacks) {
        this.url = url;
        this.callbacks = callbacks; // { onOpen, onMessage, onClose }
        this.socket = null;
        this.reconnectTimer = null;
    }

    connect() {
        this.socket = new WebSocket(this.url);

        this.socket.onopen = () => {
            console.log("WS Connected");
            if (this.callbacks.onOpen) this.callbacks.onOpen();
            if (this.reconnectTimer) clearInterval(this.reconnectTimer);
        };

        this.socket.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (this.callbacks.onMessage) this.callbacks.onMessage(msg);
            } catch (e) { console.error("WS Parse Error", e); }
        };

        this.socket.onclose = () => {
            console.log("WS Disconnected");
            if (this.callbacks.onClose) this.callbacks.onClose();
            this.reconnectTimer = setTimeout(() => this.connect(), 3000);
        };
    }
}
