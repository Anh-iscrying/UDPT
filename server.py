import os
import sys
import json
import time 
import threading 
from concurrent import futures
import grpc
import demo_pb2 
import demo_pb2_grpc 

# --- Cấu hình Node và Cụm ---
PORT = None
NODE_ID = None 
store = {}
DATA_FILE = None

CLUSTER_CONFIG = {
    "node1": "localhost:50051",
    "node2": "localhost:50052",
    "node3": "localhost:50053",
}
SORTED_NODE_IDS = sorted(CLUSTER_CONFIG.keys())

# --- Heartbeat Configuration ---
HEARTBEAT_INTERVAL_SECONDS = 5 
HEARTBEAT_TIMEOUT_SECONDS = 2  

peer_status = {}
peer_status_lock = threading.Lock()
# --- Kết thúc Heartbeat ---

# --- Data Recovery Configuration ---
INITIAL_RECOVERY_DELAY_SECONDS = 3 # Chờ 1 chút sau khi khởi động trước khi cố gắng khôi phục
# --- Kết thúc Data Recovery ---


def load_store():
    global store
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                store = json.load(f)
                print(f"[INFO] Node {NODE_ID} ({PORT}): Dữ liệu được nạp từ {DATA_FILE}")
            except json.JSONDecodeError:
                print(f"[ERROR] Node {NODE_ID} ({PORT}): Lỗi đọc file {DATA_FILE}. Khởi tạo store rỗng.")
                store = {}
    else:
        store = {}
        print(f"[INFO] Node {NODE_ID} ({PORT}): Không tìm thấy {DATA_FILE}, khởi tạo store rỗng.")

def save_store():
    # Thêm lock nếu có nhiều luồng cùng lúc gọi save_store,
    # nhưng hiện tại save_store chủ yếu được gọi từ luồng chính của RPC handler.
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    # print(f"[DEBUG] Node {NODE_ID}: Dữ liệu đã lưu vào {DATA_FILE}")


def get_primary_node_id_for_key(key: str) -> str:
    if not SORTED_NODE_IDS:
        print("[CRITICAL] CLUSTER_CONFIG không được định nghĩa hoặc rỗng.")
        return None
    key_hash = 0
    for char in key:
        key_hash = (key_hash * 31 + ord(char)) & 0xFFFFFFFF
    primary_node_index = key_hash % len(SORTED_NODE_IDS)
    primary_node_id = SORTED_NODE_IDS[primary_node_index]
    return primary_node_id

# --- Heartbeat Functions ---
def update_peer_status(peer_id, status):
    global peer_status
    with peer_status_lock:
        current_status = peer_status.get(peer_id)
        if current_status != status:
            print(f"[HEARTBEAT] Node {NODE_ID}: Trạng thái của peer {peer_id} thay đổi từ {current_status} -> {status}")
            peer_status[peer_id] = status

def _send_single_heartbeat(peer_id_to_check: str, peer_address_to_check: str):
    try:
        with grpc.insecure_channel(peer_address_to_check) as channel:
            stub = demo_pb2_grpc.KeyValueStub(channel)
            response = stub.CheckHealth(demo_pb2.HealthCheckRequest(), timeout=HEARTBEAT_TIMEOUT_SECONDS)
            if response.status == "SERVING":
                update_peer_status(peer_id_to_check, "ALIVE")
            else:
                update_peer_status(peer_id_to_check, "UNHEALTHY")
    except grpc.RpcError:
        update_peer_status(peer_id_to_check, "DEAD")
    except Exception: # Bắt các lỗi khác như không resolve được host
        update_peer_status(peer_id_to_check, "DEAD")

def heartbeat_worker():
    print(f"[INFO] Node {NODE_ID}: Luồng Heartbeat bắt đầu.")
    time.sleep(INITIAL_RECOVERY_DELAY_SECONDS / 2) 
    while True: 
        # Tạo bản sao của keys để tránh lỗi "dictionary changed size during iteration"
        # nếu CLUSTER_CONFIG có thể thay đổi động (hiện tại là không)
        current_cluster_keys = list(CLUSTER_CONFIG.keys())
        for peer_id in current_cluster_keys:
            if peer_id == NODE_ID: 
                continue
            peer_address = CLUSTER_CONFIG[peer_id] # Giả sử CLUSTER_CONFIG không thay đổi sau khi worker bắt đầu
            _send_single_heartbeat(peer_id, peer_address)
        time.sleep(HEARTBEAT_INTERVAL_SECONDS)
# --- Kết thúc Heartbeat Functions ---


class KeyValueServicer(demo_pb2_grpc.KeyValueServicer):
    
    def _get_stub_and_channel(self, target_node_id: str):
        target_address = CLUSTER_CONFIG.get(target_node_id)
        if not target_address:
            print(f"[ERROR] Node {NODE_ID}: Không tìm thấy địa chỉ cho target_node_id '{target_node_id}' trong CLUSTER_CONFIG.")
            return None, None
        # Channel nên được quản lý cẩn thận hơn trong môi trường production (ví dụ: connection pooling)
        # Ở đây, tạo mới và đóng sau mỗi lần sử dụng cho đơn giản.
        channel = grpc.insecure_channel(target_address)
        stub = demo_pb2_grpc.KeyValueStub(channel)
        return stub, channel

    def RequestFullSnapshot(self, request, context):
        print(f"[SNAPSHOT] Node {NODE_ID} ({PORT}): Nhận yêu cầu RequestFullSnapshot.")
        try:
            # Giả sử ở đây việc đọc `store` để dump là an toàn.
            data_json_snapshot = json.dumps(store)
            print(f"[SNAPSHOT] Node {NODE_ID} ({PORT}): Đã tạo snapshot, kích thước: {len(data_json_snapshot)} bytes. Gửi phản hồi.")
            return demo_pb2.FullSnapshotResponse(data_json=data_json_snapshot)
        except Exception as e:
            print(f"[ERROR] Node {NODE_ID} ({PORT}): Lỗi khi tạo snapshot: {e}")
            context.abort(grpc.StatusCode.INTERNAL, "Lỗi khi tạo snapshot trên server.")
            return demo_pb2.FullSnapshotResponse()

    def GetKey(self, request, context):
        key = request.key
        primary_node_id_for_key = get_primary_node_id_for_key(key)

        if not primary_node_id_for_key: 
             context.abort(grpc.StatusCode.INTERNAL, "Lỗi cấu hình: Không thể xác định primary node.")
             return demo_pb2.Value() 

        # print(f"[DEBUG] Node {NODE_ID}: GetKey('{key}'). Primary: {primary_node_id_for_key}")
        if NODE_ID == primary_node_id_for_key:
            if key in store:
                return demo_pb2.Value(value=store[key])
            else:
                return demo_pb2.Value(value="<KEY_NOT_FOUND>")
        else:
            with peer_status_lock: 
                primary_status = peer_status.get(primary_node_id_for_key, "UNKNOWN")
            
            if primary_status != "ALIVE" and primary_status != "UNKNOWN": 
                print(f"[WARN] Node {NODE_ID}: GetKey('{key}') - Primary node {primary_node_id_for_key} không ALIVE (trạng thái: {primary_status}). Không thể forward.")
                context.abort(grpc.StatusCode.UNAVAILABLE, f"Primary node {primary_node_id_for_key} ({CLUSTER_CONFIG.get(primary_node_id_for_key)}) không sẵn sàng.")
                return demo_pb2.Value()

            stub, channel = self._get_stub_and_channel(primary_node_id_for_key)
            if not stub:
                context.abort(grpc.StatusCode.INTERNAL, f"Lỗi tạo stub khi chuyển tiếp GetKey đến {primary_node_id_for_key}")
                return demo_pb2.Value()
            try:
                # print(f"[DEBUG] Node {NODE_ID}: Forwarding GetKey('{key}') to {primary_node_id_for_key}")
                response = stub.GetKey(demo_pb2.Key(key=key), timeout=5) 
                return response
            except grpc.RpcError as e:
                print(f"[ERROR] Node {NODE_ID}: Lỗi RPC khi forward GetKey('{key}') đến {primary_node_id_for_key}: {e.details()}")
                context.abort(e.code(), f"Lỗi khi chuyển tiếp GetKey: {e.details()}")
            finally:
                if channel:
                    channel.close()

    def PutKey(self, request, context):
        key = request.key
        value = request.value
        is_replica_req = request.is_replica 
        
        primary_node_id_for_key = get_primary_node_id_for_key(key)
        if not primary_node_id_for_key:
             context.abort(grpc.StatusCode.INTERNAL, "Lỗi cấu hình: Không thể xác định primary node.")
             return demo_pb2.PutKeyReturn()

        # print(f"[DEBUG] Node {NODE_ID}: PutKey('{key}'). Primary: {primary_node_id_for_key}. IsReplica: {is_replica_req}")
        if NODE_ID == primary_node_id_for_key: 
            if is_replica_req: 
                # print(f"[DEBUG] Node {NODE_ID} (Primary): Nhận PutKey is_replica=True cho '{key}'. Chỉ ghi.")
                store[key] = value
                save_store()
                return demo_pb2.PutKeyReturn(code=0, message=f"Đã lưu (Primary - Ghi từ replica request): {key}")

            # print(f"[DEBUG] Node {NODE_ID} (Primary): Xử lý ghi cho '{key}'.")
            store[key] = value
            save_store()
            
            successful_replicas = 0
            replica_node_ids = [nid for nid in SORTED_NODE_IDS if nid != NODE_ID]
            if replica_node_ids:
                # print(f"[DEBUG] Node {NODE_ID} (Primary): Bắt đầu sao lưu PutKey('{key}') tới replicas: {replica_node_ids}")
                for replica_id in replica_node_ids:
                    with peer_status_lock:
                        status = peer_status.get(replica_id, "UNKNOWN") 
                    
                    if status != "ALIVE":
                        print(f"[WARN] Node {NODE_ID} (Primary): Bỏ qua sao lưu PutKey('{key}') tới replica {replica_id} (trạng thái: {status}).")
                        continue

                    r_stub, r_channel = self._get_stub_and_channel(replica_id)
                    if not r_stub: continue
                    try:
                        # print(f"[DEBUG] Node {NODE_ID} (Primary): Gửi PutKey replica tới {replica_id} cho key '{key}'")
                        r_stub.PutKey(demo_pb2.PutKeyRequest(key=key, value=value, is_replica=True), timeout=5)
                        successful_replicas += 1
                    except grpc.RpcError as e:
                        print(f"[WARN] Node {NODE_ID} (Primary): Lỗi RPC khi sao lưu PutKey('{key}') tới replica {replica_id}: {e.details()}")
                    finally:
                        if r_channel: r_channel.close()
            
            return demo_pb2.PutKeyReturn(code=0, message=f"Đã lưu (Primary): {key}. Sao lưu tới {successful_replicas}/{len(replica_node_ids)} replicas.")

        else: 
            if is_replica_req: 
                # print(f"[DEBUG] Node {NODE_ID} (Replica): Nhận lệnh ghi từ primary cho '{key}'.")
                store[key] = value
                save_store()
                return demo_pb2.PutKeyReturn(code=0, message=f"Đã lưu (Replica): {key}")
            else: 
                with peer_status_lock:
                    primary_status = peer_status.get(primary_node_id_for_key, "UNKNOWN")

                if primary_status != "ALIVE" and primary_status != "UNKNOWN":
                    print(f"[WARN] Node {NODE_ID}: PutKey('{key}') - Primary node {primary_node_id_for_key} không ALIVE (trạng thái: {primary_status}). Không thể forward.")
                    context.abort(grpc.StatusCode.UNAVAILABLE, f"Primary node {primary_node_id_for_key} ({CLUSTER_CONFIG.get(primary_node_id_for_key)}) không sẵn sàng.")
                    return demo_pb2.PutKeyReturn()

                stub, channel = self._get_stub_and_channel(primary_node_id_for_key)
                if not stub:
                    context.abort(grpc.StatusCode.INTERNAL, f"Lỗi tạo stub khi chuyển tiếp PutKey đến {primary_node_id_for_key}")
                    return demo_pb2.PutKeyReturn()
                try:
                    # print(f"[DEBUG] Node {NODE_ID}: Forwarding PutKey('{key}') to {primary_node_id_for_key}")
                    response = stub.PutKey(demo_pb2.PutKeyRequest(key=key, value=value, is_replica=False), timeout=5)
                    return response
                except grpc.RpcError as e:
                    print(f"[ERROR] Node {NODE_ID}: Lỗi RPC khi forward PutKey('{key}') đến {primary_node_id_for_key}: {e.details()}")
                    context.abort(e.code(), f"Lỗi khi chuyển tiếp PutKey: {e.details()}")
                finally:
                    if channel: channel.close()

    def DeleteKey(self, request, context):
        key = request.key
        is_replica_req = request.is_replica

        primary_node_id_for_key = get_primary_node_id_for_key(key)
        if not primary_node_id_for_key:
             context.abort(grpc.StatusCode.INTERNAL, "Lỗi cấu hình: Không thể xác định primary node.")
             return demo_pb2.Message()

        # print(f"[DEBUG] Node {NODE_ID}: DeleteKey('{key}'). Primary: {primary_node_id_for_key}. IsReplica: {is_replica_req}")
        if NODE_ID == primary_node_id_for_key: 
            if is_replica_req:
                # print(f"[DEBUG] Node {NODE_ID} (Primary): Nhận DeleteKey is_replica=True cho '{key}'. Chỉ xóa.")
                if key in store: del store[key]; save_store()
                return demo_pb2.Message(msg=f"Đã xóa (Primary - Replica request): '{key}'.")
            
            # print(f"[DEBUG] Node {NODE_ID} (Primary): Xử lý xóa cho '{key}'.")
            existed = key in store
            if existed:
                del store[key]
                save_store()
            
            successful_replicas = 0
            if existed: 
                replica_node_ids = [nid for nid in SORTED_NODE_IDS if nid != NODE_ID]
                if replica_node_ids:
                    # print(f"[DEBUG] Node {NODE_ID} (Primary): Bắt đầu sao lưu DeleteKey('{key}') tới replicas: {replica_node_ids}")
                    for replica_id in replica_node_ids:
                        with peer_status_lock:
                            status = peer_status.get(replica_id, "UNKNOWN")
                        
                        if status != "ALIVE":
                            print(f"[WARN] Node {NODE_ID} (Primary): Bỏ qua sao lưu DeleteKey('{key}') tới replica {replica_id} (trạng thái: {status}).")
                            continue
                        
                        r_stub, r_channel = self._get_stub_and_channel(replica_id)
                        if not r_stub: continue
                        try:
                            # print(f"[DEBUG] Node {NODE_ID} (Primary): Gửi DeleteKey replica tới {replica_id} cho key '{key}'")
                            r_stub.DeleteKey(demo_pb2.DeleteKeyRequest(key=key, is_replica=True), timeout=5)
                            successful_replicas +=1
                        except grpc.RpcError as e:
                            print(f"[WARN] Node {NODE_ID} (Primary): Lỗi RPC khi sao lưu DeleteKey('{key}') tới replica {replica_id}: {e.details()}")
                        finally:
                            if r_channel: r_channel.close()
            
            return demo_pb2.Message(msg=f"Khóa '{key}' {'đã được xóa' if existed else 'không tồn tại'} (Primary). Sao lưu tới {successful_replicas}/{len(replica_node_ids) if existed else 0} replicas.")

        else: 
            if is_replica_req: 
                # print(f"[DEBUG] Node {NODE_ID} (Replica): Nhận lệnh xóa từ primary cho '{key}'.")
                if key in store:
                    del store[key]
                    save_store()
                return demo_pb2.Message(msg=f"Lệnh xóa cho '{key}' đã xử lý trên replica.")
            else: 
                with peer_status_lock:
                    primary_status = peer_status.get(primary_node_id_for_key, "UNKNOWN")

                if primary_status != "ALIVE" and primary_status != "UNKNOWN":
                    print(f"[WARN] Node {NODE_ID}: DeleteKey('{key}') - Primary node {primary_node_id_for_key} không ALIVE (trạng thái: {primary_status}). Không thể forward.")
                    context.abort(grpc.StatusCode.UNAVAILABLE, f"Primary node {primary_node_id_for_key} ({CLUSTER_CONFIG.get(primary_node_id_for_key)}) không sẵn sàng.")
                    return demo_pb2.Message()

                stub, channel = self._get_stub_and_channel(primary_node_id_for_key)
                if not stub:
                    context.abort(grpc.StatusCode.INTERNAL, f"Lỗi tạo stub khi chuyển tiếp DeleteKey đến {primary_node_id_for_key}")
                    return demo_pb2.Message()
                try:
                    # print(f"[DEBUG] Node {NODE_ID}: Forwarding DeleteKey('{key}') to {primary_node_id_for_key}")
                    response = stub.DeleteKey(demo_pb2.DeleteKeyRequest(key=key, is_replica=False), timeout=5)
                    return response
                except grpc.RpcError as e:
                    print(f"[ERROR] Node {NODE_ID}: Lỗi RPC khi forward DeleteKey('{key}') đến {primary_node_id_for_key}: {e.details()}")
                    context.abort(e.code(), f"Lỗi khi chuyển tiếp DeleteKey: {e.details()}")
                finally:
                    if channel: channel.close()
    
    def TinhTong(self, request, context): # Giữ lại nếu bạn vẫn dùng
        result = request.a + request.b
        return demo_pb2.KetQuaTinhTong(answer=result)

    def CheckHealth(self, request, context):
        return demo_pb2.HealthCheckResponse(status="SERVING")

# --- Data Recovery Function ---
def attempt_data_recovery():
    global store
    # Chỉ thực hiện khôi phục nếu đây không phải là lần khởi động đầu tiên (ví dụ, file data đã tồn tại)
    # hoặc có một cơ chế khác để quyết định khi nào cần khôi phục.
    
    print(f"[RECOVERY] Node {NODE_ID}: Chờ {INITIAL_RECOVERY_DELAY_SECONDS} giây trước khi thử khôi phục dữ liệu...")
    time.sleep(INITIAL_RECOVERY_DELAY_SECONDS)
    print(f"[RECOVERY] Node {NODE_ID}: Bắt đầu quá trình khôi phục dữ liệu.")
    
    potential_source_nodes = [nid for nid in SORTED_NODE_IDS if nid != NODE_ID]
    if not potential_source_nodes:
        print(f"[RECOVERY] Node {NODE_ID}: Không có node nào khác để khôi phục.")
        return

    recovered_successfully = False
    # Sắp xếp ngẫu nhiên danh sách node nguồn để tránh tất cả cùng hỏi 1 node
    import random
    random.shuffle(potential_source_nodes)

    for candidate_id in potential_source_nodes:
        with peer_status_lock: # Kiểm tra trạng thái đã biết từ heartbeat
            status = peer_status.get(candidate_id, "UNKNOWN") 
        
        if status == "DEAD": 
            print(f"[RECOVERY] Node {NODE_ID}: Bỏ qua khôi phục từ {candidate_id} (đã biết là DEAD).")
            continue

        print(f"[RECOVERY] Node {NODE_ID}: Thử khôi phục dữ liệu từ {candidate_id} (trạng thái hiện tại: {status})...")
        target_address = CLUSTER_CONFIG.get(candidate_id)
        if not target_address: continue

        try:
            # Sử dụng with statement để đảm bảo channel được đóng
            with grpc.insecure_channel(target_address) as recovery_channel:
                recovery_stub = demo_pb2_grpc.KeyValueStub(recovery_channel)
                
                print(f"[RECOVERY] Node {NODE_ID}: Gửi RequestFullSnapshot đến {candidate_id}.")
                response = recovery_stub.RequestFullSnapshot(demo_pb2.EmptyRequest(), timeout=15) # Tăng timeout
                
                if response and response.data_json:
                    print(f"[RECOVERY] Node {NODE_ID}: Nhận snapshot từ {candidate_id} (kích thước: {len(response.data_json)} bytes).")
                    new_store_data = json.loads(response.data_json)
                    
                    # Chiến lược: Ghi đè hoàn toàn store cục bộ
                    print(f"[RECOVERY] Node {NODE_ID}: Store hiện tại có {len(store)} keys. Snapshot có {len(new_store_data)} keys.")
                    store = new_store_data 
                    save_store()
                    print(f"[RECOVERY] Node {NODE_ID}: Khôi phục dữ liệu thành công từ {candidate_id}. Store đã được cập nhật.")
                    recovered_successfully = True
                    break 
                else:
                    print(f"[WARN] Node {NODE_ID}: Phản hồi snapshot rỗng hoặc không có data_json từ {candidate_id}.")

        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNAVAILABLE or e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                 print(f"[WARN] Node {NODE_ID}: Không thể kết nối hoặc timeout khi yêu cầu snapshot từ {candidate_id}.")
            else:
                 print(f"[WARN] Node {NODE_ID}: Lỗi RPC khác khi yêu cầu snapshot từ {candidate_id}: Code={e.code()}, Details={e.details()}")
        except json.JSONDecodeError as e:
            print(f"[ERROR] Node {NODE_ID}: Lỗi giải mã JSON từ snapshot của {candidate_id}: {e}")
        except Exception as e:
            print(f"[ERROR] Node {NODE_ID}: Lỗi không xác định khi khôi phục từ {candidate_id}: {e}")
            
    if not recovered_successfully:
        print(f"[WARN] Node {NODE_ID}: Không thể khôi phục dữ liệu từ bất kỳ node nào khác. Sử dụng dữ liệu cục bộ (nếu có).")
# --- Kết thúc Data Recovery Function ---


def serve():
    global PORT, NODE_ID, DATA_FILE, peer_status

    if len(sys.argv) != 2:
        print("Cách dùng: python server.py <port>")
        sys.exit(1)

    PORT = sys.argv[1]
    
    current_node_id_found = False
    for nid, addr in CLUSTER_CONFIG.items():
        if addr.endswith(f":{PORT}"):
            NODE_ID = nid
            current_node_id_found = True
            break
    
    if not current_node_id_found:
        print(f"Lỗi: Port {PORT} không được tìm thấy trong CLUSTER_CONFIG.")
        sys.exit(1)

    DATA_FILE = f"data_{NODE_ID}.json"
    load_store() # Tải dữ liệu cục bộ trước

    # Khởi tạo trạng thái ban đầu của các peer là UNKNOWN
    with peer_status_lock:
        for peer_id_init in CLUSTER_CONFIG:
            if peer_id_init != NODE_ID:
                peer_status[peer_id_init] = "UNKNOWN"

    # Khởi động luồng heartbeat
    hb_thread = threading.Thread(target=heartbeat_worker, daemon=True)
    hb_thread.start()

    # Bắt đầu quá trình khôi phục dữ liệu (chạy trong một luồng riêng để không block server chính)
    # Hoặc chạy tuần tự trước khi server.start() nếu muốn đảm bảo khôi phục xong mới phục vụ
    recovery_thread = threading.Thread(target=attempt_data_recovery, daemon=True)
    recovery_thread.start()


    server_obj = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    demo_pb2_grpc.add_KeyValueServicer_to_server(KeyValueServicer(), server_obj)

    print(f"[INFO] === Node ID: {NODE_ID}, Port: {PORT}. Server bắt đầu. ===")
    print(f"[INFO] Cấu hình cụm: {CLUSTER_CONFIG}")
    
    server_obj.add_insecure_port(f"[::]:{PORT}")
    server_obj.start()
    print(f"[INFO] Node {NODE_ID} ({PORT}): Đang lắng nghe...")
    try:
        # Chờ cho đến khi server dừng hoặc luồng khôi phục hoàn tất (nếu chạy tuần tự)
        # server_obj.wait_for_termination()
        # Để server chạy và cho phép luồng khôi phục/heartbeat hoạt động ngầm:
        while True:
            time.sleep(60) # Giữ luồng chính sống
    except KeyboardInterrupt:
        print(f"\n[INFO] Node {NODE_ID} ({PORT}): Nhận tín hiệu tắt (Ctrl+C). Đang tắt server...")
        save_store() 
        # server_obj.stop(0) # Dừng server gRPC một cách nhẹ nhàng 
        print(f"[INFO] Node {NODE_ID} ({PORT}): Server đã tắt.")


if __name__ == "__main__":
    serve()