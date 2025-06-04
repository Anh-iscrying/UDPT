import grpc
import demo_pb2 # Đảm bảo import sau khi đã generate lại
import demo_pb2_grpc # Đảm bảo import sau khi đã generate lại
import sys

def test_health_check(host):
    try:
        with grpc.insecure_channel(host) as channel:
            # Đặt timeout cho RPC call để không bị treo nếu server không phản hồi
            stub = demo_pb2_grpc.KeyValueStub(channel)
            response = stub.CheckHealth(demo_pb2.HealthCheckRequest(), timeout=1) # Thêm timeout 1 giây
            print(f"[✓] {host} is alive. Status: {response.status}")
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.UNAVAILABLE:
            print(f"[✗] {host} is unreachable or not responding.")
        elif e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            print(f"[✗] {host} timed out.")
        else:
            print(f"[✗] {host} - Lỗi RPC: {e.details()}")
    except Exception as e: # Bắt các lỗi khác, ví dụ không resolve được host
         print(f"[✗] {host} - Lỗi không xác định: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Cách dùng: python health_check_client.py <host:port> [<host:port> ...]")
        print("Ví dụ: python health_check_client.py localhost:50051 localhost:50052")
        sys.exit(1)

    print("Bắt đầu kiểm tra health:")
    for host_arg in sys.argv[1:]:
        test_health_check(host_arg)