# Hệ Thống Lưu Trữ Key-Value Phân Tán Đơn Giản

Dự án này triển khai một hệ thống lưu trữ key-value phân tán đơn giản bằng Python và gRPC. Hệ thống bao gồm nhiều node, mỗi node lưu trữ một phần dữ liệu (sẽ được cập nhật sau với sharding) và có khả năng sao lưu dữ liệu sang các node khác để đảm bảo tính sẵn sàng và chịu lỗi.

## Mục Lục

- [Tính Năng Hiện Tại](#tính-năng-hiện-tại)
- [Yêu Cầu Hệ Thống](#yêu-cầu-hệ-thống)
- [Cài Đặt](#cài-đặt)
- [Cấu Trúc Dự Án](#cấu-trúc-dự-án)
- [Cách Xây Dựng (Sinh Code gRPC)](#cách-xây-dựng-sinh-code-grpc)
- [Cách Chạy Hệ Thống](#cách-chạy-hệ-thống)
  - [Chạy Server Nodes](#chạy-server-nodes)
  - [Chạy Client Demo](#chạy-client-demo)
  - [Kiểm Tra Trạng Thái Node (Health Check)](#kiểm-tra-trạng-thái-node-health-check)
- [Kiểm Thử](#kiểm-thử)
- [Hướng Phát Triển Tiếp Theo](#hướng-phát-triển-tiếp-theo)

## Tính Năng Hiện Tại

*   **Lưu trữ Key-Value:** Hỗ trợ các thao tác `PUT(key, value)`, `GET(key)`, và `DELETE(key)`.
*   **Cụm Đa Node:** Có thể triển khai nhiều node server (ví dụ: 3 node) để tạo thành một cụm lưu trữ.
*   **Sao Lưu Dữ Liệu (Full Replication):**
    *   Mỗi thao tác `PUT` trên một node sẽ được sao lưu đến tất cả các node khác trong cụm.
    *   Mỗi thao tác `DELETE` trên một node sẽ được sao lưu lệnh xóa đến tất cả các node khác trong cụm.
    *   Mỗi key-value có bản sao trên tất cả các node.
*   **Giao Tiếp gRPC:** Các node và client giao tiếp với nhau qua gRPC.
*   **Lưu Trữ Dữ Liệu:** Mỗi node lưu trữ dữ liệu của mình vào một file JSON cục bộ (`data_node_<port>.json`).
*   **Client Demo:** Một client CLI đơn giản để tương tác với hệ thống và thực hiện các kịch bản demo.
*   **Health Check:** Các node cung cấp một endpoint `CheckHealth` để kiểm tra trạng thái.

## Yêu Cầu Hệ Thống

*   Python 3.7+
*   pip (Python package installer)

## Cài Đặt

1.  Clone repository này (nếu có) hoặc tạo một thư mục dự án và đặt các file vào đó.
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
Cách Chạy Hệ Thống
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
Sau khi khởi động, mỗi server sẽ in ra log cho biết nó đang lắng nghe trên cổng nào và các peer của nó. Dữ liệu của mỗi node sẽ được lưu trong file data_node_<port>.json (ví dụ: data_node_50051.json).
Chạy Client Demo
Sau khi tất cả các server node đã khởi động và chạy, mở một Terminal thứ 4 và chạy chương trình client:
```bash
python client.py
```
Client sẽ tự động thực hiện một loạt các kịch bản PUT, GET, DELETE với các node khác nhau để demo tính năng sao lưu và hoạt động cơ bản. Quan sát log từ client và từ các server node để thấy sự tương tác.
Kiểm Tra Trạng Thái Node (Health Check)
Bạn có thể sử dụng health_check_client.py để kiểm tra trạng thái của từng node:
```bash
python health_check_client.py localhost:50051 localhost:50052 localhost:50053
```
Hoặc kiểm tra từng node riêng lẻ:
```bash
python health_check_client.py localhost:50051
```
## Kiểm Thử

### Kiểm tra PUT và Sao lưu:

- Chạy `client.py`. Quan sát thao tác PUT được gửi đến một node.  
- Kiểm tra log của node đó và các node peer để thấy dữ liệu được lưu và sao lưu.  
- Kiểm tra các file `data_node_*.json` để xác nhận dữ liệu được ghi.  
- Client sẽ tự động GET key từ tất cả các node để xác nhận sao lưu.

---

### Kiểm tra DELETE và Sao lưu:

- `client.py` sẽ thực hiện thao tác DELETE. Quan sát lệnh xóa được gửi đến một node.  
- Kiểm tra log của node đó và các node peer để thấy lệnh xóa được xử lý và sao lưu.  
- Client sẽ tự động GET key đã xóa từ tất cả các node để xác nhận nó không còn tồn tại.

---

### Kiểm tra khi một node tắt (Mô phỏng lỗi - Sẽ hoàn thiện hơn ở các bước sau):

- Chạy 3 server.  
- Thực hiện PUT một vài key-value bằng `client.py`.  
- Tắt một trong các server node (ví dụ, bằng cách nhấn Ctrl+C trong terminal của nó).  
- Sử dụng `client.py` để thử GET các key đã PUT từ các node còn lại. Chúng vẫn nên trả về dữ liệu do cơ chế sao lưu.  
- Thử PUT một key mới vào một node còn sống.  
  - Thao tác này vẫn nên thành công trên node đó và được sao lưu đến các node còn sống khác.  
  - Log trên node thực hiện PUT có thể báo lỗi khi cố gắng sao lưu đến node đã chết.

---

## Hướng Phát Triển Tiếp Theo (Theo Yêu Cầu Dự Án)

- **Phân Vùng Dữ Liệu (Sharding):**  
  Triển khai cơ chế để mỗi node chỉ chịu trách nhiệm chính cho một phần dữ liệu (ví dụ: sử dụng consistent hashing hoặc `hash(key) % N`).

- **Chuyển Tiếp Yêu Cầu (Request Forwarding):**  
  Nếu một node nhận request cho một key không thuộc phân vùng của nó, nó sẽ chuyển tiếp request đến node phù hợp.

- **Phát Hiện Lỗi Chủ Động (Heartbeat):**  
  Các node gửi heartbeat cho nhau để phát hiện node nào bị lỗi/tắt.

- **Quản Lý Thành Viên Cụm Nâng Cao:**  
  Cập nhật danh sách node "sống" và "chết".

- **Khôi Phục Dữ Liệu:**  
  Khi một node bị lỗi khởi động lại, nó cần đồng bộ dữ liệu bị thiếu từ các node khác.

- **Cải thiện Client CLI:**  
  Thêm các lệnh tương tác cho client.
