import grpc
import threading
import time
import json
import demo_pb2
import demo_pb2_grpc
import random

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Input, Button, Static, Label, Select, Log
from textual.reactive import reactive

# --- Cấu hình Client ---
CLIENT_SIDE_CLUSTER_CONFIG = {
    "node1": "localhost:50051",
    "node2": "localhost:50052",
    "node3": "localhost:50053",
}
SERVER_ADDRESSES_OPTIONS = [(f"{nid} ({addr})", addr) for nid, addr in CLIENT_SIDE_CLUSTER_CONFIG.items()]
KEY_NOT_FOUND_MSG = "<KEY_NOT_FOUND>"
ASSUMED_SERVER_HEARTBEAT_INTERVAL = 3

# --- Hàm tiện ích ---
def get_primary_node_id_for_key_client(key: str) -> str:
    sorted_node_ids = sorted(CLIENT_SIDE_CLUSTER_CONFIG.keys())
    if not sorted_node_ids: return "N/A"
    key_hash = 0
    for char in key: key_hash = (key_hash * 31 + ord(char)) & 0xFFFFFFFF
    primary_node_index = key_hash % len(sorted_node_ids)
    return sorted_node_ids[primary_node_index]

class KVApp(App[None]):
    CSS_PATH = "kv_app.tcss"
    BINDINGS = [
        ("q", "quit", "Thoát"),
        ("ctrl+l", "clear_log", "Xóa Log Client")
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_server_address = SERVER_ADDRESSES_OPTIONS[0][1] if SERVER_ADDRESSES_OPTIONS else None
        self.cluster_status_widgets = {}
        self.status_lock = threading.Lock()
        self.cluster_status_data = {nid: "[dim]UNKNOWN[/dim]" for nid in CLIENT_SIDE_CLUSTER_CONFIG.keys()}

    def compose(self) -> ComposeResult:
        yield Header(name="Hệ Thống Key-Value Phân Tán - Demo TUI")
        with Horizontal(id="main_layout"):
            with Vertical(id="controls_panel"):
                yield Label("Chọn Server Node:")
                if SERVER_ADDRESSES_OPTIONS:
                    yield Select(SERVER_ADDRESSES_OPTIONS, value=self.selected_server_address, id="server_select")
                else:
                    yield Static("Lỗi: Cấu hình server rỗng.")

                yield Label("Lệnh (PUT key value / GET key / DELETE key):")
                yield Input(placeholder="VD: PUT mykey myvalue", id="command_input")
                with Horizontal(id="button_bar"):
                    yield Button("Gửi Lệnh", id="send_button_widget", variant="primary") # ID widget
                    yield Button("Làm Mới Trạng Thái", id="refresh_status_button_widget", variant="default") # ID widget
                
                yield Label("Log Client:", id="log_label")
                self.client_log_widget = Log(highlight=True, id="client_log_area")
                yield self.client_log_widget

            with Vertical(id="status_panel"):
                yield Label("Trạng Thái Cụm:")
                for node_id in CLIENT_SIDE_CLUSTER_CONFIG.keys():
                    status_widget = Static(f"{node_id}: [dim]UNKNOWN[/dim]", id=f"status_{node_id}")
                    self.cluster_status_widgets[node_id] = status_widget
                    yield status_widget
        yield Footer()

    def on_mount(self) -> None:
        self.command_input_widget = self.query_one("#command_input", Input)
        if SERVER_ADDRESSES_OPTIONS:
            self.server_select_widget = self.query_one("#server_select", Select)
        
        self.health_check_thread = threading.Thread(target=self._periodic_health_check, daemon=True)
        self.health_check_thread.start()
        self.append_client_log("TUI Client sẵn sàng. Nhập lệnh hoặc 'q' để thoát.")

    def action_quit(self) -> None:
        self.exit()

    def action_clear_log(self) -> None:
        self.client_log_widget.clear()
        self.append_client_log("Log Client đã được xóa.")

    def append_client_log(self, message: str, is_error: bool = False):
        timestamp = time.strftime("%H:%M:%S")
        style = "[red]" if is_error else "[bright_blue]"
        self.client_log_widget.write_line(f"{style}[{timestamp}] {message}[/]")

    def _periodic_health_check(self):
        while True:
            new_statuses = {}
            # self.call_from_thread(self.append_client_log, "TUI: Bắt đầu chu kỳ kiểm tra health...") 
            for node_id, address in CLIENT_SIDE_CLUSTER_CONFIG.items():
                status_str = "[red]DEAD[/]" 
                # self.call_from_thread(self.append_client_log, f"TUI: Đang check {node_id} tại {address}")
                try:
                    with grpc.insecure_channel(address) as channel:
                        stub = demo_pb2_grpc.KeyValueStub(channel)
                        response = stub.CheckHealth(demo_pb2.HealthCheckRequest(), timeout=0.8)
                        if response.status == "SERVING": status_str = "[green]ALIVE[/]"
                        else: status_str = f"[yellow]UNHEALTHY ({response.status})[/]"
                except grpc.RpcError: pass 
                except Exception: status_str = "[magenta]ERROR_CONNECT[/]"
                new_statuses[node_id] = status_str
            
            def update_ui_from_thread():
                with self.status_lock: self.cluster_status_data = new_statuses
                for node_id, status_text_markup in new_statuses.items():
                    if node_id in self.cluster_status_widgets:
                        self.cluster_status_widgets[node_id].update(f"{node_id}: {status_text_markup}")
            self.call_from_thread(update_ui_from_thread)
            # self.call_from_thread(self.append_client_log, f"TUI: Hoàn thành chu kỳ health. Trạng thái: {new_statuses}")
            time.sleep(ASSUMED_SERVER_HEARTBEAT_INTERVAL)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value is not None:
            self.selected_server_address = str(event.value)
            self.append_client_log(f"Đã chọn server: {self.selected_server_address}")
        else:
            self.selected_server_address = None
            self.append_client_log("Lựa chọn server không hợp lệ.", is_error=True)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        self.append_client_log(f"Nút được nhấn: {event.button.id}") # DEBUG LOG

        if event.button.id == "send_button_widget": # SỬA ID Ở ĐÂY
            command_text = self.command_input_widget.value.strip()
            self.command_input_widget.value = "" 
            if not command_text:
                self.append_client_log("Lệnh không được để trống.", is_error=True)
                return
            if not self.selected_server_address:
                self.append_client_log("Chưa chọn server đích.", is_error=True)
                return

            self.append_client_log(f"Chuẩn bị gửi lệnh: '{command_text}' đến {self.selected_server_address}")
            self.append_client_log("Đang tạo luồng để thực thi lệnh...") # DEBUG LOG
            threading.Thread(target=self._execute_command_thread, args=(command_text, self.selected_server_address)).start()
            self.append_client_log("Luồng thực thi lệnh đã được khởi chạy.") # DEBUG LOG

        elif event.button.id == "refresh_status_button_widget": # SỬA ID Ở ĐÂY
            self.append_client_log("Làm mới trạng thái cụm...")
            threading.Thread(target=self._manual_refresh_status).start()

    def _manual_refresh_status(self):
        temp_statuses = {}
        for node_id, address in CLIENT_SIDE_CLUSTER_CONFIG.items():
            status_str = "[red]DEAD[/]"
            try:
                with grpc.insecure_channel(address) as channel:
                    stub = demo_pb2_grpc.KeyValueStub(channel)
                    response = stub.CheckHealth(demo_pb2.HealthCheckRequest(), timeout=0.8)
                    if response.status == "SERVING": status_str = "[green]ALIVE[/]"
                    else: status_str = f"[yellow]UNHEALTHY ({response.status})[/]"
            except grpc.RpcError: pass
            except Exception: status_str = "[magenta]ERROR_CONNECT[/]"
            temp_statuses[node_id] = status_str
        
        def update_ui_from_manual_refresh():
            with self.status_lock: self.cluster_status_data = temp_statuses
            for node_id, status_text_markup in temp_statuses.items():
                if node_id in self.cluster_status_widgets:
                    self.cluster_status_widgets[node_id].update(f"{node_id}: {status_text_markup}")
            self.append_client_log("Trạng thái cụm đã được làm mới (thủ công).")
        self.call_from_thread(update_ui_from_manual_refresh)

    def _execute_command_thread(self, command_text: str, server_address: str):
        self.call_from_thread(self.append_client_log, f"Thread: Bắt đầu thực thi '{command_text}'") # DEBUG LOG

        parts = command_text.split(maxsplit=2)
        operation, key, value_str = "", "", ""
        if len(parts) > 0: operation = parts[0].upper()
        if len(parts) > 1: key = parts[1]
        if len(parts) > 2: value_str = parts[2]
        
        result_message = f"Lệnh không hợp lệ: '{command_text}'. Dùng PUT key value | GET key | DELETE key"
        is_error_rpc = False
        
        if key:
            expected_primary = get_primary_node_id_for_key_client(key)
            self.call_from_thread(self.append_client_log, f"Dự kiến primary cho '{key}': {expected_primary}")

        try:
            with grpc.insecure_channel(server_address) as channel:
                stub = demo_pb2_grpc.KeyValueStub(channel)
                if operation == "PUT" and key and value_str:
                    response = stub.PutKey(demo_pb2.PutKeyRequest(key=key, value=value_str, is_replica=False), timeout=10)
                    result_message = f"PUT: {response.message}"
                elif operation == "GET" and key:
                    response = stub.GetKey(demo_pb2.Key(key=key), timeout=10)
                    if response.value == KEY_NOT_FOUND_MSG:
                        result_message = f"GET '{key}': KHÔNG TÌM THẤY"
                    else:
                        result_message = f"GET '{key}': '{response.value}'"
                elif operation == "DELETE" and key:
                    response = stub.DeleteKey(demo_pb2.DeleteKeyRequest(key=key, is_replica=False), timeout=10)
                    result_message = f"DELETE: {response.msg}"
        except grpc.RpcError as e:
            result_message = f"Lỗi RPC: {e.code()} - {e.details()}"
            is_error_rpc = True 
        except Exception as ex:
            result_message = f"Lỗi Client: {ex}"
            is_error_rpc = True 

        self.call_from_thread(self.append_client_log, result_message, is_error=is_error_rpc)
        self.call_from_thread(self.append_client_log, f"Thread: Hoàn thành thực thi '{command_text}'") # DEBUG LOG

if __name__ == "__main__":
    app = KVApp()
    app.run()