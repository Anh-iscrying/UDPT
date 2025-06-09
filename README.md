# Hệ Thống Lưu Trữ Key-Value Phân Tán Đơn Giản

Dự án này triển khai một hệ thống lưu trữ key-value phân tán bằng Python và gRPC. Hệ thống bao gồm nhiều node, mỗi node chịu trách nhiệm chính cho một phần dữ liệu (sharding), có khả năng chuyển tiếp yêu cầu, sao lưu dữ liệu sang các node khác, phát hiện lỗi node, và khôi phục dữ liệu khi một node khởi động lại. Một giao diện người dùng đầu cuối (TUI) được cung cấp để tương tác và demo hệ thống.

## Mục Lục

- [Tính Năng Chính](#tính-năng-chính)
- [Yêu Cầu Hệ Thống](#yêu-cầu-hệ-thống)
- [Cài Đặt](#cài-đặt)
- [Cấu Trúc Dự Án](#cấu-trúc-dự-án)
- [Cách Xây Dựng (Sinh Code gRPC)](#cách-xây-dựng-sinh-code-grpc)
- [Cấu Hình Cụm](#cấu-hình-cụm)
- [Cách Chạy Hệ Thống](#cách-chạy-hệ-thống)
  - [Chạy Server Nodes](#chạy-server-nodes)
  - [Chạy Client TUI (Terminal User Interface)](#chạy-client-tui-terminal-user-interface)
- [Kiểm Thử Các Tính Năng (Sử dụng Client TUI)](#kiểm-thử-các-tính-năng-sử-dụng-client-tui)
  - [Hoạt Động Cơ Bản (Sharding, Forwarding, Sao Lưu)](#hoạt-động-cơ-bản-sharding-forwarding-sao-lưu)
  - [Kiểm Thử Tính Chịu Lỗi (Node Down)](#kiểm-thử-tính-chịu-lỗi-node-down)
  - [Kiểm Thử Khôi Phục Dữ Liệu (Node Restart)](#kiểm-thử-khôi-phục-dữ-liệu-node-restart)
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
    *   Khi node primary thực hiện `PUT` hoặc `DELETE`, thao tác này sẽ được **sao lưu** đến tất cả các node khác (replicas) trong cụm đang hoạt động.
    *   Mỗi cặp key-value có ít nhất 2 bản sao (1 primary, và các bản sao trên các node còn lại).
*   **Phát Hiện Lỗi Node (Heartbeat):**
    *   Các node server gửi heartbeat định kỳ cho nhau để theo dõi trạng thái (`ALIVE`, `DEAD`, `UNKNOWN`).
    *   Client TUI cũng thực hiện kiểm tra health định kỳ để hiển thị trạng thái cụm.
    *   Node primary sẽ không cố gắng sao lưu đến các replica đang ở trạng thái `DEAD`.
    *   Node sẽ không cố gắng chuyển tiếp request đến primary node đang ở trạng thái `DEAD` (client sẽ nhận lỗi `UNAVAILABLE`).
*   **Khôi Phục Dữ Liệu (Snapshot Recovery):**
    *   Khi một node server khởi động lại sau khi bị lỗi, nó sẽ cố gắng yêu cầu một **ảnh chụp (snapshot) đầy đủ** dữ liệu từ một node khác đang hoạt động trong cụm.
    *   Node khởi động lại sẽ ghi đè store cục bộ của mình bằng dữ liệu từ snapshot để đồng bộ lại.
*   **Giao Tiếp gRPC:** Các node và client giao tiếp với nhau qua gRPC và Protocol Buffers.
*   **Lưu Trữ Dữ Liệu:** Mỗi node lưu trữ dữ liệu của mình vào một file JSON cục bộ (`data_<node_id>.json`).
*   **Client TUI (Terminal User Interface):** Một giao diện người dùng đầu cuối tương tác được xây dựng bằng Textual, cho phép:
    *   Chọn server đích để gửi request.
    *   Thực hiện các lệnh PUT, GET, DELETE.
    *   Hiển thị log của client.
    *   Hiển thị trạng thái (`ALIVE`/`DEAD`) của tất cả các node trong cụm theo thời gian thực.

## Yêu Cầu Hệ Thống

*   Python 3.7+
*   pip (Python package installer)

## Cài Đặt

1.  Clone repository này (nếu có) hoặc tạo một thư mục dự án và đặt các file vào đó.
2.  Cài đặt các thư viện Python cần thiết:
    ```bash
    pip install grpcio grpcio-tools textual
    ```
    *(Lưu ý: `textual` đã được thêm vào cho client TUI).*

## Cấu Trúc Dự Án
```
.
├── demo.proto # Định nghĩa Protocol Buffer cho gRPC services và messages
├── demo_pb2.py # Code Python được sinh tự động từ demo.proto (messages)
├── demo_pb2_grpc.py # Code Python được sinh tự động từ demo.proto (services/stubs)
├── server.py # Logic của một node server trong cụm
├── textual_kv_client.py # Client TUI để tương tác và demo hệ thống
├──  kv_app.tcss # File CSS cho client TUI (Textual)
└── README.md # File này
```

## Cách Xây Dựng (Sinh Code gRPC)

Mỗi khi bạn thay đổi file `demo.proto` (ví dụ: thêm RPC mới, sửa message), bạn cần phải sinh lại code Python tương ứng.

Trong thư mục gốc của dự án (nơi chứa `demo.proto`), chạy lệnh sau:

```bash
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. demo.proto
```

Lệnh này sẽ cập nhật (hoặc tạo mới) các file demo_pb2.py và demo_pb2_grpc.py.

### Cấu Hình Cụm
Thông tin về các node trong cụm (Node ID và địa chỉ IP:Port) được hardcode trong biến CLUSTER_CONFIG ở đầu file server.py và CLIENT_SIDE_CLUSTER_CONFIG trong client.py. 

Hiện tại, hệ thống được cấu hình với 3 node:

node1: localhost:50051

node2: localhost:50052

node3: localhost:50053

### Cách Chạy Hệ Thống
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
- Mỗi server sẽ in ra NODE_ID và PORT của nó.
- Nó sẽ cố gắng tải dữ liệu từ file data_<node_id>.json (nếu có).
- Luồng Heartbeat sẽ bắt đầu.
- Luồng Khôi phục dữ liệu (attempt_data_recovery) sẽ chạy. Ban đầu, nếu tất cả các node cùng khởi động, chúng có thể không khôi phục được gì từ nhau hoặc khôi phục từ một store rỗng.
- Sau một vài giây, các node sẽ bắt đầu nhận diện trạng thái ALIVE của nhau qua heartbeat.

### Chạy Client TUI (Terminal User Interface)
Sau khi tất cả các server node đã khởi động và chạy ổn định (đợi khoảng 15-20 giây để heartbeat và khôi phục ban đầu hoàn tất), mở một Terminal thứ 4 và chạy chương trình client:
```bash
python textual_kv_client.py
```
Giao diện TUI sẽ xuất hiện, hiển thị các ô nhập liệu, log client, và trạng thái của các node trong cụm.

## Kiểm Thử
Sử dụng TUI client để thực hiện các kịch bản sau và quan sát log trên TUI cũng như trên các terminal của server.

### Hoạt Động Cơ Bản (Sharding, Forwarding, Sao Lưu)
1. Chọn Server Đích: Trong TUI, chọn một server (ví dụ node1) từ dropdown.
2. PUT Dữ Liệu: Nhập lệnh PUT mykey myvalue và nhấn "Gửi Lệnh".
- Quan sát Log TUI: Sẽ hiển thị "Dự kiến primary cho 'mykey': nodeX" và kết quả PUT.
- Quan sát Log Server:
Node được chọn (node1) sẽ nhận request. Nếu nó không phải primary (nodeX), nó sẽ log "Chuyển tiếp...".
Node primary (nodeX) sẽ log việc xử lý PUT và "Bắt đầu sao lưu...".
Các node replica sẽ log việc nhận lệnh sao lưu.
3. GET Dữ Liệu:
- Từ TUI (vẫn kết nối node1), nhập GET mykey. Kết quả phải là myvalue.
- Trong TUI, đổi server đích sang một node khác (ví dụ node3). Nhập lại GET mykey. Kết quả vẫn phải là myvalue (chứng tỏ sao lưu và/hoặc forwarding hoạt động).
4. DELETE Dữ Liệu: Tương tự như PUT, thực hiện lệnh DELETE mykey và quan sát log.

---

### Kiểm Thử Tính Chịu Lỗi
1. Hoạt động bình thường: PUT một key (key_cho_node2) mà bạn biết primary của nó là node2 (TUI sẽ báo "Dự kiến primary..."). PUT một key khác (key_cho_node1) có primary là node1.
2. Tắt Node Primary: Tắt server node2 (Ctrl+C ở terminal của nó).
3. Quan sát TUI: Sau vài giây, "Trạng Thái Cụm" sẽ hiển thị node2: [red]DEAD[/].
4. Thao tác với Key của Node Đã Chết:
- Trong TUI (kết nối qua node1), thử GET key_cho_node2.
- Log TUI: Sẽ báo lỗi RPC UNAVAILABLE (vì node1 từ chối forward đến node2 đã chết).
5. Thao tác với Key của Node Còn Sống:
- Trong TUI (kết nối qua node1), thử PUT key_cho_node1 newValue.
- Log TUI: Lệnh PUT thành công.
- Log Server node1: Sẽ xử lý PUT và log "Bỏ qua sao lưu ... tới replica node2 (trạng thái: DEAD)".

---

### Kiểm Thử Khôi Phục Dữ Liệu
1. Node2 vẫn đang tắt (từ kịch bản trên).
2. Ghi Dữ Liệu Mới: Trong TUI (kết nối qua node1), PUT key_moi_khi_node2_tat "important_data". Key này sẽ được lưu trên node1 và node3.
3. Khởi Động Lại Node2: Chạy lại python server.py 50052 ở terminal của node2.
4. Quan sát:
- Log Server node2: Sẽ có các dòng [RECOVERY], cho thấy nó yêu cầu và nhận snapshot từ node1 hoặc node3. Log sẽ báo "Khôi phục dữ liệu thành công...".
- TUI "Trạng Thái Cụm": node2 sẽ chuyển lại thành [green]ALIVE[/].
5. Kiểm Tra Dữ Liệu trên Node2:
- Trong TUI, chọn server đích là node2.
- Nhập lệnh GET key_moi_khi_node2_tat.
- Log TUI: Nên trả về "important_data", chứng tỏ node2 đã khôi phục được dữ liệu được ghi khi nó offline.
- Thử GET các key cũ hơn (key_cho_node1, key_cho_node2) từ node2 để đảm bảo chúng cũng được khôi phục.

---

## Các RPC Chính (trong demo.proto)
- PutKey(PutKeyRequest) returns (PutKeyReturn): Ghi hoặc cập nhật một cặp key-value. Có cờ is_replica.
- GetKey(Key) returns (Value): Lấy giá trị của một key.
- DeleteKey(DeleteKeyRequest) returns (Message): Xóa một key. Có cờ is_replica.
- CheckHealth(HealthCheckRequest) returns (HealthCheckResponse): Được sử dụng cho heartbeat.
- RequestFullSnapshot(EmptyRequest) returns (FullSnapshotResponse): Được sử dụng bởi node khởi động lại để yêu cầu dữ liệu từ node khác.
