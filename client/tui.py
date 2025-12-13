
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, Button, Input, ListView, ListItem, Label, TabbedContent, TabPane
from textual.screen import Screen
from pathlib import Path
import requests
import json
import os

CLIENT_DIR = Path(__file__).parent
CLIENT_CONFIG_PATH = CLIENT_DIR / "client_config.json"

def get_api_url():
    if CLIENT_CONFIG_PATH.exists():
        try:
            cfg = json.loads(CLIENT_CONFIG_PATH.read_text())
            return cfg.get("backend_url", "http://localhost:8000")
        except:
            pass
    return None

def save_api_url(url):
    config = {"backend_url": url}
    CLIENT_CONFIG_PATH.write_text(json.dumps(config), encoding="utf-8")

class ConnectScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Configuración de Conexión", classes="header"),
            Label("URL del Backend:"),
            Input(placeholder="http://localhost:8000", id="inp_url"),
            Button("Conectar y Guardar", id="btn_connect", variant="primary"),
            Label("", id="status_connect"),
            classes="connect-container"
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn_connect":
            url = self.query_one("#inp_url", Input).value.rstrip("/")
            if not url:
                url = "http://localhost:8000"
            
            self.query_one("#status_connect", Label).update("Probando conexión...")
            try:
                # Simple ping check
                r = requests.get(f"{url}/config", timeout=3)
                if r.status_code == 200:
                    save_api_url(url)
                    self.app.api_url = url
                    self.dismiss(True)
                else:
                    self.query_one("#status_connect", Label).update(f"Error: Status {r.status_code}")
            except Exception as e:
                self.query_one("#status_connect", Label).update(f"Error de conexión: {e}")

class ConfigForm(Static):
    def compose(self) -> ComposeResult:
        yield Label("Output Dir:")
        yield Input(id="conf_output", placeholder="/downloads")
        yield Label("Concurrency:")
        yield Input(id="conf_concurrency", placeholder="2")
        yield Button("Guardar Configuración", id="btn_save_config", variant="primary")
        yield Label("", id="status_config")
    
    def load_data(self):
        try:
            r = requests.get(f"{self.app.api_url}/config", timeout=2)
            if r.status_code == 200:
                data = r.json()
                self.query_one("#conf_output", Input).value = str(data.get("output_dir", ""))
                self.query_one("#conf_concurrency", Input).value = str(data.get("concurrency", ""))
        except:
            self.query_one("#status_config", Label).update("Error conectando al servidor")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn_save_config":
            out_dir = self.query_one("#conf_output", Input).value
            conc = self.query_one("#conf_concurrency", Input).value
            try:
                requests.post(f"{self.app.api_url}/config", json={
                    "output_dir": out_dir,
                    "concurrency": int(conc) if conc.isdigit() else 2
                })
                self.query_one("#status_config", Label).update("Guardado correctamente")
            except Exception as e:
                self.query_one("#status_config", Label).update(f"Error: {e}")

class PlaylistManager(Static):
    def compose(self) -> ComposeResult:
        yield Label("Gestión de Playlists", classes="header")
        yield Horizontal(
            Input(id="inp_pl_name", placeholder="Nombre Playlist"),
            Input(id="inp_pl_url", placeholder="URL inicial"),
            Button("Añadir", id="btn_add_pl", variant="success"),
            classes="input-row"
        )
        yield ListView(id="list_playlists")
        yield Label("", id="status_pl")

    def on_mount(self):
        # We delay refresh until we know we have an API URL
        # But this widget might be mounted before connection...
        # We'll rely on the Tab change or manual refresh if mounted early.
        # Actually, if we use a Screen for connection, the main app slots won't be fully active/visible until dismissed?
        # Textual mounts everything in the DOM. 
        # We'll add a check in refresh.
        self.set_interval(5, self.refresh_playlists)

    def refresh_playlists(self):
        if not hasattr(self.app, "api_url") or not self.app.api_url:
            return

        list_view = self.query_one("#list_playlists", ListView)
        
        try:
            r = requests.get(f"{self.app.api_url}/playlists", timeout=2)
            if r.status_code == 200:
                playlists = r.json()
                
                # Mapa de playlists nuevas
                new_map = {p["id"]: p for p in playlists}
                new_ids = set(new_map.keys())
                
                # Identificar existentes en la UI
                existing_ids = set()
                for child in list_view.children:
                    if child.id and child.id.startswith("item_"):
                        existing_ids.add(child.id.replace("item_", ""))
                
                # Borrar las que ya no están
                to_delete = existing_ids - new_ids
                for pl_id in to_delete:
                    try:
                        list_view.get_child_by_id(f"item_{pl_id}").remove()
                    except:
                        pass
                
                # Añadir las nuevas
                to_add = new_ids - existing_ids
                for pl_id in to_add:
                    pl = new_map[pl_id]
                    item = ListItem(
                        Horizontal(
                            Label(f"{pl.get('name')} ({len(pl.get('urls',[]))} URLs)", classes="pl-label"),
                            Button("Borrar", id=f"del_{pl.get('id')}", variant="error", classes="btn-del")
                        ),
                        id=f"item_{pl.get('id')}"
                    )
                    list_view.append(item)
                    
        except Exception as e:
             # Evitar spam de errores si el backend cae
             pass

    def on_button_pressed(self, event: Button.Pressed):
        if not hasattr(self.app, "api_url"): return

        btn_id = event.button.id
        if not btn_id: return

        if btn_id == "btn_add_pl":
            name = self.query_one("#inp_pl_name", Input).value
            url = self.query_one("#inp_pl_url", Input).value
            if name and url:
                import uuid
                payload = {
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "urls": [url]
                }
                try:
                    resp = requests.post(f"{self.app.api_url}/playlists", json=payload)
                    resp.raise_for_status()
                    self.query_one("#inp_pl_name", Input).value = ""
                    self.query_one("#inp_pl_url", Input).value = ""
                    self.refresh_playlists()
                    self.query_one("#status_pl", Label).update("Playlist añadida")
                except Exception as e:
                    self.query_one("#status_pl", Label).update(f"Error al añadir: {e}")
        
        elif btn_id.startswith("del_"):
            pl_id = btn_id.split("_")[1]
            try:
               requests.delete(f"{self.app.api_url}/playlists/{pl_id}")
               self.refresh_playlists()
            except:
               pass

class Dashboard(Static):
    def compose(self) -> ComposeResult:
        yield Label("Estado del Servicio", classes="header")
        yield Button("EJECUTAR AHORA", id="btn_run", variant="error")
        yield Label("", id="run_status")

    def on_button_pressed(self, event: Button.Pressed):
        if not hasattr(self.app, "api_url"): return
        
        if event.button.id == "btn_run":
            try:
                requests.post(f"{self.app.api_url}/run")
                self.query_one("#run_status", Label).update("Ejecución iniciada en background")
            except:
                self.query_one("#run_status", Label).update("Error de conexión")

class DownloaderApp(App):
    CSS = """
    .toolbar { height: 3; dock: top; }
    .input-row { height: 3; margin: 1; }
    #inp_pl_name { width: 1fr; }
    #inp_pl_url { width: 2fr; }
    .pl-label { width: 1fr; content-align: left middle; }
    .btn-del { dock: right; }
    #btn_run { margin: 2; }
    .header { text-align: center; text-style: bold; }
    .connect-container { align: center middle; }
    #inp_url { width: 50%; }
    """
    BINDINGS = [("q", "quit", "Salir")]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Dashboard", id="tab_dash"):
                yield Dashboard()
            with TabPane("Playlists", id="tab_pl"):
                yield PlaylistManager()
            with TabPane("Configuración", id="tab_conf"):
                yield ConfigForm()
        yield Footer()

    def on_mount(self):
        saved_url = get_api_url()
        if saved_url:
            self.api_url = saved_url
            # Trigger initial load
            self.query_one(ConfigForm).load_data()
            self.query_one(PlaylistManager).refresh_playlists()
        else:
            self.push_screen(ConnectScreen(), self.on_connect)

    def on_connect(self, result):
        # Result is True if connected
        if result:
            self.query_one(ConfigForm).load_data()
            self.query_one(PlaylistManager).refresh_playlists()

if __name__ == "__main__":
    DownloaderApp().run()
