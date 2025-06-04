# client.py
import sys
import grpc
import time 
import demo_pb2
import demo_pb2_grpc
import random # Để tìm key ngẫu nhiên

# --- Cấu hình Client (nên đồng bộ với server) ---
SERVERS = [ 
    "localhost:50051",
    "localhost:50052",
    "localhost:50053"
]
KEY_NOT_FOUND_MSG = "<KEY_NOT_FOUND>"

CLIENT_SIDE_CLUSTER_CONFIG = {
    "node1": "localhost:50051",
    "node2": "localhost:50052",
    "node3": "localhost:50053",
}
CLIENT_SIDE_SORTED_NODE_IDS = sorted(CLIENT_SIDE_CLUSTER_CONFIG.keys())

# Giả định khoảng thời gian heartbeat của server (tính bằng giây)
# Giá trị này nên tương ứng với HEARTBEAT_INTERVAL_SECONDS trong server.py
# và INITIAL_RECOVERY_DELAY_SECONDS để client chờ đủ lâu.
ASSUMED_SERVER_HEARTBEAT_INTERVAL = 5 
ASSUMED_SERVER_INITIAL_RECOVERY_DELAY = 3

def get_primary_node_id_for_key_client(key: str) -> str:
    if not CLIENT_SIDE_SORTED_NODE_IDS:
        return "N/A (Chưa cấu hình client cluster)"
    key_hash = 0
    for char in key:
        key_hash = (key_hash * 31 + ord(char)) & 0xFFFFFFFF
    primary_node_index = key_hash % len(CLIENT_SIDE_SORTED_NODE_IDS)
    return CLIENT_SIDE_SORTED_NODE_IDS[primary_node_index]

def put_key(server_address, key, value, suppress_error_for_test=False):
    expected_primary_node = get_primary_node_id_for_key_client(key)
    print(f"\n>>> Client: Gửi PUT ('{key}' = '{value}') đến {server_address}. (Dự kiến primary: {expected_primary_node})")
    try:
        with grpc.insecure_channel(server_address) as channel:
            stub = demo_pb2_grpc.KeyValueStub(channel)
            response = stub.PutKey(demo_pb2.PutKeyRequest(key=key, value=value, is_replica=False), timeout=10) 
            print(f"<<< Server {server_address} phản hồi PutKey: {response.message} (Code: {response.code})")
            return True # Thành công
    except grpc.RpcError as e:
        if not suppress_error_for_test: # Chỉ in lỗi nếu không phải đang cố tình test lỗi
            print(f"!!! Lỗi RPC khi PUT đến {server_address} cho key '{key}': {e.code()} - {e.details()}")
        else:
            print(f"--- (Mong đợi) Lỗi RPC khi PUT đến {server_address} cho key '{key}': {e.code()} - {e.details()}")
        return False # Thất bại

def get_key(server_address, key, suppress_error_for_test=False):
    expected_primary_node = get_primary_node_id_for_key_client(key)
    print(f"\n>>> Client: Gửi GET ('{key}') đến {server_address}. (Dự kiến primary: {expected_primary_node})")
    try:
        with grpc.insecure_channel(server_address) as channel:
            stub = demo_pb2_grpc.KeyValueStub(channel)
            response = stub.GetKey(demo_pb2.Key(key=key), timeout=10)
            if response.value == KEY_NOT_FOUND_MSG:
                print(f"<<< Server {server_address} phản hồi GetKey('{key}'): KHÔNG TÌM THẤY")
            else:
                print(f"<<< Server {server_address} phản hồi GetKey('{key}'): '{response.value}'")
            return response.value
    except grpc.RpcError as e:
        if not suppress_error_for_test:
            print(f"!!! Lỗi RPC khi GET từ {server_address} cho key '{key}': {e.code()} - {e.details()}")
        else:
            print(f"--- (Mong đợi) Lỗi RPC khi GET từ {server_address} cho key '{key}': {e.code()} - {e.details()}")
        return None

def delete_key(server_address, key, suppress_error_for_test=False):
    expected_primary_node = get_primary_node_id_for_key_client(key)
    print(f"\n>>> Client: Gửi DELETE ('{key}') đến {server_address}. (Dự kiến primary: {expected_primary_node})")
    try:
        with grpc.insecure_channel(server_address) as channel:
            stub = demo_pb2_grpc.KeyValueStub(channel)
            response = stub.DeleteKey(demo_pb2.DeleteKeyRequest(key=key, is_replica=False), timeout=10)
            print(f"<<< Server {server_address} phản hồi DeleteKey: {response.msg}")
            return True # Thành công
    except grpc.RpcError as e:
        if not suppress_error_for_test:
            print(f"!!! Lỗi RPC khi DELETE đến {server_address} cho key '{key}': {e.code()} - {e.details()}")
        else:
            print(f"--- (Mong đợi) Lỗi RPC khi DELETE đến {server_address} cho key '{key}': {e.code()} - {e.details()}")
        return False # Thất bại

def check_health(server_address):
    try:
        with grpc.insecure_channel(server_address) as channel:
            stub = demo_pb2_grpc.KeyValueStub(channel)
            response = stub.CheckHealth(demo_pb2.HealthCheckRequest(), timeout=1)
            print(f"--- Health của {server_address}: {response.status}")
            return True
    except grpc.RpcError:
        print(f"--- Health của {server_address}: FAILED (Không kết nối được hoặc timeout)")
        return False

def find_key_for_node(target_node_id: str, prefix="testkey", max_attempts=1000) -> str:
    """Tìm một key ngẫu nhiên mà hash về target_node_id."""
    print(f"Đang tìm key có primary là {target_node_id} với prefix '{prefix}'...")
    for i in range(max_attempts):
        random_key = f"{prefix}_{random.randint(10000, 99999)}_{i}"
        if get_primary_node_id_for_key_client(random_key) == target_node_id:
            print(f"Tìm thấy key: '{random_key}' cho node {target_node_id}")
            return random_key
    print(f"Không tìm thấy key cho {target_node_id} với prefix '{prefix}' sau {max_attempts} lần thử.")
    return None

def fault_tolerance_test_scenario():
    print("\n" + "="*20 + " BẮT ĐẦU KỊCH BẢN KIỂM THỬ CHỊU LỖI " + "="*20)

    node_to_kill_id = "node2" # Giả sử chúng ta sẽ "giết" node2
    node_to_kill_address = CLIENT_SIDE_CLUSTER_CONFIG.get(node_to_kill_id)
    
    if not node_to_kill_address:
        print(f"!!! Không tìm thấy địa chỉ cho node {node_to_kill_id}.")
        return

    key_on_killed_node = find_key_for_node(node_to_kill_id, prefix="fault_key")
    if not key_on_killed_node: return
    
    surviving_node_id_for_key = "node1" if node_to_kill_id != "node1" else "node3" 
    key_on_surviving_node = find_key_for_node(surviving_node_id_for_key, prefix="survive_key")
    if not key_on_surviving_node: return

    # Chọn server để client tương tác (không phải node sắp bị kill)
    client_connect_to_server = SERVERS[0]
    if client_connect_to_server == node_to_kill_address:
        client_connect_to_server = SERVERS[1] 
    print(f"Client sẽ tương tác chính với server: {client_connect_to_server}")


    print(f"\n--- Bước 1 (Chịu lỗi): Hoạt động bình thường ---")
    print(f"Key '{key_on_killed_node}' (primary: {node_to_kill_id})")
    print(f"Key '{key_on_surviving_node}' (primary: {surviving_node_id_for_key})")

    put_key(client_connect_to_server, key_on_killed_node, f"Value for {key_on_killed_node}")
    put_key(client_connect_to_server, key_on_surviving_node, f"Value for {key_on_surviving_node}")
    time.sleep(1) 
    get_key(client_connect_to_server, key_on_killed_node)
    get_key(client_connect_to_server, key_on_surviving_node)

    print(f"\n\n--- Bước 2 (Chịu lỗi): Mô phỏng {node_to_kill_id} ({node_to_kill_address}) bị lỗi ---")
    input(f"!!! HÃY TẮT SERVER NODE {node_to_kill_id} (cổng {node_to_kill_address.split(':')[1]}) BẰNG CTRL+C. SAU ĐÓ NHẤN ENTER...")
    
    wait_cycles = 2 
    wait_time = ASSUMED_SERVER_HEARTBEAT_INTERVAL * wait_cycles
    print(f"\nClient chờ {wait_time} giây để các server khác phát hiện {node_to_kill_id} lỗi...")
    time.sleep(wait_time)

    print(f"\n--- Bước 3 (Chịu lỗi): Kiểm tra hệ thống khi {node_to_kill_id} đã lỗi ---")
    
    print(f"\nThử GET key '{key_on_killed_node}' (primary là {node_to_kill_id} đã chết):")
    get_key(client_connect_to_server, key_on_killed_node, suppress_error_for_test=True) 

    print(f"\nThử PUT key '{key_on_killed_node}' (primary là {node_to_kill_id} đã chết):")
    put_key(client_connect_to_server, key_on_killed_node, "New value when primary dead", suppress_error_for_test=True) 

    print(f"\nThử GET key '{key_on_surviving_node}' (primary là {surviving_node_id_for_key} còn sống):")
    get_key(client_connect_to_server, key_on_surviving_node) 

    print(f"\nThử PUT key '{key_on_surviving_node}' (primary là {surviving_node_id_for_key} còn sống):")
    put_key(client_connect_to_server, key_on_surviving_node, "New value on surviving node") 

    print("\n" + "="*20 + " KẾT THÚC KỊCH BẢN CHỊU LỖI " + "="*20)
    # Không khởi động lại node ở đây, để cho kịch bản khôi phục xử lý riêng.

def recovery_test_scenario():
    print("\n" + "="*20 + " BẮT ĐẦU KỊCH BẢN KIỂM THỬ KHÔI PHỤC DỮ LIỆU " + "="*20)

    node_to_restart_id = "node2" # Giả sử node2 đã bị tắt từ kịch bản trước hoặc sẽ bị tắt bây giờ
    node_to_restart_address = CLIENT_SIDE_CLUSTER_CONFIG.get(node_to_restart_id)
    
    if not node_to_restart_address:
        print(f"!!! Không tìm thấy địa chỉ cho node {node_to_restart_id}.")
        return

    # Chọn một server client sẽ tương tác (không phải là node_to_restart_id)
    interacting_server_addr = SERVERS[0]
    if interacting_server_addr == node_to_restart_address:
        interacting_server_addr = SERVERS[1] if len(SERVERS) > 1 else SERVERS[0] # Cần ít nhất 1 server khác
        if interacting_server_addr == node_to_restart_address and len(CLIENT_SIDE_CLUSTER_CONFIG) ==1:
             print("!!! Cần ít nhất 2 node để test khôi phục. Bỏ qua.")
             return
    
    print(f"Client sẽ tương tác chính với: {interacting_server_addr}")
    print(f"Node sẽ được khởi động lại: {node_to_restart_id} ({node_to_restart_address})")

    # --- Bước 1 (Khôi phục): Đảm bảo node đã tắt và ghi dữ liệu mới ---
    print(f"\n--- Bước 1 (Khôi phục): Đảm bảo {node_to_restart_id} đã tắt và ghi dữ liệu mới ---")
    # Kiểm tra health của node sắp khởi động lại, nó nên là FAILED
    print(f"Kiểm tra health của {node_to_restart_id} (nên là FAILED nếu chưa chạy kịch bản chịu lỗi trước đó):")
    is_restarting_node_down = not check_health(node_to_restart_address)
    
    if not is_restarting_node_down:
        input(f"!!! Node {node_to_restart_id} có vẻ đang chạy. HÃY TẮT SERVER NODE {node_to_restart_id} (cổng {node_to_restart_address.split(':')[1]}) BẰNG CTRL+C. SAU ĐÓ NHẤN ENTER...")
        wait_time_for_detection = ASSUMED_SERVER_HEARTBEAT_INTERVAL * 2 
        print(f"\nClient chờ {wait_time_for_detection} giây để các server khác phát hiện {node_to_restart_id} lỗi...")
        time.sleep(wait_time_for_detection)

    key_initial_1 = find_key_for_node(CLIENT_SIDE_SORTED_NODE_IDS[0], prefix="rec_init_key") # Key cho node còn sống
    if not key_initial_1: return
    key_while_down = find_key_for_node(CLIENT_SIDE_SORTED_NODE_IDS[1] if CLIENT_SIDE_SORTED_NODE_IDS[1] != node_to_restart_id else CLIENT_SIDE_SORTED_NODE_IDS[0], prefix="rec_down_key") # Key cho node còn sống khác
    if not key_while_down: return
    
    print(f"\nPUT '{key_initial_1}' (Value_A) khi tất cả (trừ {node_to_restart_id}) đang chạy.")
    put_key(interacting_server_addr, key_initial_1, "Value_A_for_Recovery_Test")
    time.sleep(0.5)
    
    print(f"\nPUT '{key_while_down}' (Value_B) khi {node_to_restart_id} đang tắt.")
    put_key(interacting_server_addr, key_while_down, "Value_B_written_while_node_down")
    
    print("\nChờ 2 giây cho sao lưu (đến các node còn sống)...")
    time.sleep(2)

    print(f"\nKiểm tra '{key_while_down}' và '{key_initial_1}' trên các node còn sống:")
    for node_id_check, server_addr_check in CLIENT_SIDE_CLUSTER_CONFIG.items():
        if node_id_check != node_to_restart_id:
            print(f"-- Kiểm tra trên {node_id_check} --")
            get_key(server_addr_check, key_initial_1)
            get_key(server_addr_check, key_while_down) 

    # --- Bước 2 (Khôi phục): Khởi động lại node_to_restart_id ---
    print(f"\n\n--- Bước 2 (Khôi phục): Khởi động lại {node_to_restart_id} ---")
    input(f"!!! HÃY KHỞI ĐỘNG LẠI SERVER NODE {node_to_restart_id} (cổng {node_to_restart_address.split(':')[1]}). SAU ĐÓ NHẤN ENTER...")

    wait_time_for_recovery = ASSUMED_SERVER_HEARTBEAT_INTERVAL * 2 + ASSUMED_SERVER_INITIAL_RECOVERY_DELAY + 10 # Thêm 10s cho RPC snapshot
    print(f"\nClient chờ {wait_time_for_recovery} giây cho {node_to_restart_id} sống lại, được phát hiện, VÀ KHÔI PHỤC DỮ LIỆU...")
    time.sleep(wait_time_for_recovery)

    print(f"\nKiểm tra health của {node_to_restart_id} sau khi khởi động lại:")
    check_health(node_to_restart_address)

    # --- Bước 3 (Khôi phục): Kiểm tra dữ liệu trên node_to_restart_id sau khi khôi phục ---
    print(f"\n\n--- Bước 3 (Khôi phục): Kiểm tra dữ liệu trên {node_to_restart_id} ({node_to_restart_address}) sau khi khôi phục ---")
    print(f"GET '{key_initial_1}' từ {node_to_restart_address}:")
    get_key(node_to_restart_address, key_initial_1) 
    
    print(f"GET '{key_while_down}' từ {node_to_restart_address}:")
    get_key(node_to_restart_address, key_while_down) # **QUAN TRỌNG:** Nên có "Value_B_written_while_node_down"

    print(f"\nKiểm tra lại '{key_while_down}' trên một node khác ({interacting_server_addr}) (để đảm bảo nó không bị mất):")
    get_key(interacting_server_addr, key_while_down)

    print("\n" + "="*20 + " KẾT THÚC KỊCH BẢN KHÔI PHỤC " + "="*20)

def main():
    # Luôn kiểm tra health ban đầu
    print("Đang kiểm tra trạng thái các server...")
    initial_server_status = {addr: check_health(addr) for addr in CLIENT_SIDE_CLUSTER_CONFIG.values()}
    
    # --- Chạy kịch bản demo thông thường (tùy chọn) ---
    # print("\n" + "="*10 + " BẮT ĐẦU KỊCH BẢN DEMO THÔNG THƯỜNG " + "="*10)
    # keys_to_test = { "alpha": "Value for Alpha", "beta": "Value for Beta"}
    # for i, (k, v) in enumerate(keys_to_test.items()):
    #     target_server_for_put = SERVERS[i % len(SERVERS)] 
    #     put_key(target_server_for_put, k, v)
    #     if i < len(keys_to_test) -1 : time.sleep(0.5) 
    # print("\n(Client chờ 2 giây cho sao lưu...)"); time.sleep(2) 
    # print("\n\n--- GET các key đã PUT ---")
    # for i, k in enumerate(keys_to_test.keys()):
    #     target_server_for_get = SERVERS[(i + 1) % len(SERVERS)] 
    #     get_key(target_server_for_get, k)
    #     if i < len(keys_to_test) -1 : time.sleep(0.5)
    # print("\n" + "="*10 + " KẾT THÚC KỊCH BẢN DEMO THÔNG THƯỜNG " + "="*10)


    # --- Chạy kịch bản kiểm thử chịu lỗi ---
    # Chỉ chạy nếu có ít nhất 2 node được cấu hình và đang chạy để có ý nghĩa
    live_nodes_at_start = sum(1 for status in initial_server_status.values() if status)
    if live_nodes_at_start >= 2: # Cần ít nhất 2 node để test kịch bản tắt 1 node
        fault_tolerance_test_scenario()
    else:
        print("\n!!! Bỏ qua kịch bản chịu lỗi, cần ít nhất 2 node đang chạy để thực hiện.")
    
    # --- Chạy kịch bản kiểm thử khôi phục ---
    # Kịch bản này có thể chạy ngay cả khi một node ban đầu không chạy, vì nó sẽ yêu cầu khởi động lại.
    recovery_test_scenario()
    
    print("\n\n" + "="*20 + " KẾT THÚC TOÀN BỘ DEMO " + "="*20)
    print("\nKiểm tra tình trạng các server lần cuối:")
    all_possible_server_addresses = list(CLIENT_SIDE_CLUSTER_CONFIG.values())
    for server_addr in all_possible_server_addresses: 
        check_health(server_addr)

if __name__ == "__main__":
    main()