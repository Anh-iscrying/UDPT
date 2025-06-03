# Hệ Thống Lưu Trữ Key-Value Phân Tán Đơn Giản

Dự án này triển khai một hệ thống lưu trữ key-value phân tán bằng Python và gRPC. Hệ thống bao gồm nhiều node, mỗi node chịu trách nhiệm chính cho một phần dữ liệu (sharding), có khả năng chuyển tiếp yêu cầu, sao lưu dữ liệu sang các node khác, phát hiện lỗi node, và khôi phục dữ liệu khi một node khởi động lại.

## Mục Lục

- [Tính Năng Chính](#tính-năng-chính)
- [Yêu Cầu Hệ Thống](#yêu-cầu-hệ-thống)
- [Cài Đặt](#cài-đặt)
- [Cấu Trúc Dự Án](#cấu-trúc-dự-án)
- [Cách Xây Dựng (Sinh Code gRPC)](#cách-xây-dựng-sinh-code-grpc)
- [Cấu Hình Cụm](#cấu-hình-cụm)
- [Cách Chạy Hệ Thống](#cách-chạy-hệ-thống)
  - [Chạy Server Nodes](#chạy-server-nodes)
  - [Chạy Client Demo](#chạy-client-demo)
- [Kiểm Thử Các Tính Năng](#kiểm-thử-các-tính-năng)
  - [Hoạt Động Cơ Bản (Sharding, Forwarding, Sao Lưu)](#hoạt-động-cơ-bản-sharding-forwarding-sao-lưu)
  - [Kiểm Thử Tính Chịu Lỗi](#kiểm-thử-tính-chịu-lỗi)
  - [Kiểm Thử Khôi Phục Dữ Liệu](#kiểm-thử-khôi-phục-dữ-liệu)
- [Các RPC Chính](#các-rpc-chính)

## Tính Năng Chính

*   **Lưu trữ Key-Value:** Hỗ trợ các thao tác `PUT(key, value)`, `GET(key)`, và `DELETE(key)`.
*   **Cụm Đa Node:** Triển khai với 3 node server tạo thành một cụm lưu trữ.
*   **Phân Vùng Dữ Liệu (Sharding):**
    *   Mỗi key được hash để xác định một **node primary** chịu trách nhiệm chính cho key đó.
    *   Node primary lưu trữ bản gốc của dữ liệu.
*   **Chuyển Tiếp Yêu Cầu (Request Forwarding):**
    *   Client có thể kết nối tới bất kỳ node nào.
    *   Nếu node nhận request không phải là primary cho key đó, request sẽ được tự động chuyển tiếp đến node primary phù hợp.
*   **Sao Lưu Dữ Liệu:**
    *   Khi node primary thực hiện `PUT` hoặc `DELETE`, thao tác này sẽ được **sao lưu** đến tất cả các node khác (replicas) trong cụm.
    *   Mỗi cặp key-value có ít nhất 2 bản sao (1 primary, và các bản sao trên các node còn lại).
*   **Phát Hiện Lỗi Node (Heartbeat):**
    *   Các node gửi heartbeat định kỳ cho nhau để theo dõi trạng thái (`ALIVE`, `DEAD`, `UNKNOWN`).
    *   Node primary sẽ không cố gắng sao lưu đến các replica đang ở trạng thái `DEAD`.
    *   Node sẽ không cố gắng chuyển tiếp request đến primary node đang ở trạng thái `DEAD` (client sẽ nhận lỗi `UNAVAILABLE`).
*   **Khôi Phục Dữ Liệu (Snapshot Recovery):**
    *   Khi một node khởi động lại sau khi bị lỗi, nó sẽ cố gắng yêu cầu một **ảnh chụp (snapshot) đầy đủ** dữ liệu từ một node khác đang hoạt động trong cụm.
    *   Node khởi động lại sẽ ghi đè store cục bộ của mình bằng dữ liệu từ snapshot để đồng bộ lại.
*   **Giao Tiếp gRPC:** Các node và client giao tiếp với nhau qua gRPC và Protocol Buffers.
*   **Lưu Trữ Dữ Liệu:** Mỗi node lưu trữ dữ liệu của mình (bao gồm cả phần nó là primary và các bản sao) vào một file JSON cục bộ (`data_<node_id>.json`).
*   **Client Demo Nâng Cao:** Một client CLI thực hiện các kịch bản demo tự động để kiểm thử hoạt động bình thường, tính chịu lỗi, và khả năng khôi phục dữ liệu.

## Yêu Cầu Hệ Thống

*   Python 3.7+
*   pip (Python package installer)

## Cài Đặt

1.  Clone repository này (nếu có) hoặc tạo một thư mục dự án và đặt các file (`server.py`, `client.py`, `demo.proto`) vào đó.
2.  Cài đặt các thư viện Python cần thiết:
    ```bash
    pip install grpcio grpcio-tools
    ```

## Cấu Trúc Dự Án
```
.
├── demo.proto # Định nghĩa Protocol Buffer cho gRPC services và messages
├── demo_pb2.py # Code Python được sinh tự động từ demo.proto (messages)
├── demo_pb2_grpc.py # Code Python được sinh tự động từ demo.proto (services/stubs)
├── server.py # Logic của một node server trong cụm
├── client.py # Chương trình client để tương tác với hệ thống
├── health_check_client.py # Client đơn giản để kiểm tra health của các node
└── README.md # File này
```

## Cách Xây Dựng (Sinh Code gRPC)

Mỗi khi bạn thay đổi file `demo.proto` (ví dụ: thêm RPC mới, sửa message), bạn cần phải sinh lại code Python tương ứng.

Trong thư mục gốc của dự án (nơi chứa `demo.proto`), chạy lệnh sau:

```bash
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. demo.proto
```

Lệnh này sẽ cập nhật (hoặc tạo mới) các file demo_pb2.py và demo_pb2_grpc.py.

#Cấu Hình Cụm
Thông tin về các node trong cụm (Node ID và địa chỉ IP:Port) được hardcode trong biến CLUSTER_CONFIG ở đầu file server.py và CLIENT_SIDE_CLUSTER_CONFIG trong client.py. Hiện tại, hệ thống được cấu hình với 3 node:
node1: localhost:50051
node2: localhost:50052
node3: localhost:50053

#Cách Chạy Hệ Thống
Hệ thống được thiết kế để chạy với cụm 3 node trên các cổng 50051, 50052, và 50053 trên localhost.
Chạy Server Nodes
Bạn cần mở 3 cửa sổ terminal riêng biệt.
Trong Terminal 1:
```bash
python server.py 50051
```
Trong Terminal 2:
```bash
python server.py 50052
```
Trong Terminal 3:
```bash
python server.py 50053
```
Quan sát Log Server Khi Khởi Động:
Mỗi server sẽ in ra NODE_ID và PORT của nó.
Nó sẽ cố gắng tải dữ liệu từ file data_<node_id>.json (nếu có).
Luồng Heartbeat sẽ bắt đầu.
Luồng Khôi phục dữ liệu (attempt_data_recovery) sẽ chạy. Ban đầu, nếu tất cả các node cùng khởi động, chúng có thể không khôi phục được gì từ nhau hoặc khôi phục từ một store rỗng.
Sau một vài giây, các node sẽ bắt đầu nhận diện trạng thái ALIVE của nhau qua heartbeat.

#Chạy Client Demo
Sau khi tất cả các server node đã khởi động và chạy ổn định (đợi khoảng 15-20 giây để heartbeat và khôi phục ban đầu hoàn tất), mở một Terminal thứ 4 và chạy chương trình client:
```bash
python client.py
```
Client sẽ tự động thực hiện một loạt các kịch bản:
Kiểm tra health ban đầu của các server.
Kịch bản demo thông thường (PUT/GET nhiều key để kiểm tra sharding, forwarding, sao lưu).
Kịch bản kiểm thử tính chịu lỗi (yêu cầu người dùng tắt một node và quan sát hành vi hệ thống).
Kịch bản kiểm thử khôi phục dữ liệu (yêu cầu người dùng khởi động lại node đã tắt và quan sát quá trình khôi phục).

## Kiểm Thử
File client.py được thiết kế để tự động kiểm thử các tính năng chính.

### Hoạt Động Cơ Bản (Sharding, Forwarding, Sao Lưu)
Cách thực hiện: Chạy client.py (phần "KỊCH BẢN DEMO THÔNG THƯỜNG").
Quan sát:
Client PUT các key khác nhau. Log của client và server sẽ cho thấy key được hash về primary node nào.
Nếu client gửi request đến node không phải primary, log server sẽ cho thấy request được chuyển tiếp (forward).
Log của primary node sẽ cho thấy nó sao lưu dữ liệu (PUT) hoặc lệnh xóa (DELETE) đến các replica.
Log của các replica node sẽ cho thấy chúng nhận và áp dụng lệnh sao lưu.
Client GET key từ các node khác nhau đều nhận được dữ liệu đúng (hoặc KHÔNG TÌM THẤY nếu đã xóa).

---

### Kiểm Thử Tính Chịu Lỗi
Cách thực hiện: client.py sẽ tự động vào "KỊCH BẢN KIỂM THỬ CHỊU LỖI".
Client PUT một key (fault_key...) có primary là node2 và một key (survive_key...) có primary là một node khác (ví dụ node1).
Client sẽ yêu cầu bạn tắt node2.
Sau khi bạn tắt node2 và nhấn Enter trên client, client sẽ chờ để các node còn lại (node1, node3) phát hiện node2 đã DEAD qua heartbeat.
Quan sát:
Log của node1 và node3 sẽ báo [HEARTBEAT] ... peer node2 ... -> DEAD.
Client thử GET/PUT fault_key...: Request sẽ thất bại với lỗi UNAVAILABLE vì node1 (hoặc node3) từ chối forward đến node2 (đã DEAD).
Client thử GET/PUT survive_key...: Request sẽ thành công. node1 (primary) sẽ xử lý, nhưng khi sao lưu, nó sẽ log là bỏ qua node2 vì DEAD.

---

### Kiểm Thử Khôi Phục Dữ Liệu
Cách thực hiện: Sau kịch bản chịu lỗi, client.py sẽ vào "KỊCH BẢN KIỂM THỬ KHÔI PHỤC DỮ LIỆU". node2 vẫn đang tắt.
Client PUT một key mới (rec_down_key...) vào hệ thống (ví dụ qua node1). Key này sẽ được lưu trên node1 và node3. node2 không có nó.
Client sẽ yêu cầu bạn khởi động lại node2.
Sau khi bạn khởi động lại node2 và nhấn Enter trên client, client sẽ chờ để node2 sống lại, được phát hiện, và quan trọng nhất là thực hiện khôi phục dữ liệu.
Quan sát:
Log của node2 khi khởi động lại: Sẽ có các dòng [RECOVERY], cho thấy nó đang cố gắng lấy snapshot từ node1 hoặc node3. Nó sẽ log "Khôi phục dữ liệu thành công từ nodeX..."
Log của node1 và node3: Sẽ báo [HEARTBEAT] ... peer node2 ... -> ALIVE. Node được node2 yêu cầu snapshot sẽ log [SNAPSHOT] ... Nhận yêu cầu RequestFullSnapshot....
Client thử GET rec_down_key... từ node2: Request này nên thành công và trả về giá trị đúng, chứng tỏ node2 đã khôi phục được dữ liệu được ghi khi nó offline.

---

## Các RPC Chính (trong demo.proto)
PutKey(PutKeyRequest) returns (PutKeyReturn): Ghi hoặc cập nhật một cặp key-value. Có cờ is_replica.
GetKey(Key) returns (Value): Lấy giá trị của một key.
DeleteKey(DeleteKeyRequest) returns (Message): Xóa một key. Có cờ is_replica.
CheckHealth(HealthCheckRequest) returns (HealthCheckResponse): Được sử dụng cho heartbeat.
RequestFullSnapshot(EmptyRequest) returns (FullSnapshotResponse): Được sử dụng bởi node khởi động lại để yêu cầu dữ liệu từ node khác.
