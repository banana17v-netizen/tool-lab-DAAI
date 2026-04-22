# Oil Price Tracker

Tool Python đơn giản để theo dõi giá dầu liên tục theo giờ, hiển thị rõ ràng và lưu lịch sử vào file CSV.

## Tính năng

- Lấy giá dầu WTI (`CL=F`) và Brent (`BZ=F`) từ Yahoo Finance
- Tự động chuyển sang Stooq nếu Yahoo Finance lỗi
- Hiển thị bảng dữ liệu dễ nhìn trên terminal
- Lưu lịch sử giá vào `oil_price_history.csv`
- Chạy liên tục với chu kỳ mặc định 60 phút
- Có thể chạy tự động mỗi giờ bằng GitHub Actions

## Cách dùng

1. Mở terminal và chuyển đến thư mục `Lab/lab`
2. Chạy:

```powershell
python oil_price_tracker.py
```

3. Chạy một lần rồi dừng:

```powershell
python oil_price_tracker.py --once
```

4. Thay đổi chu kỳ cập nhật (ví dụ 30 phút):

```powershell
python oil_price_tracker.py --interval 30
```

5. Thay đổi tên file lưu dữ liệu:

```powershell
python oil_price_tracker.py --output my_oil_history.csv
```

## Ghi chú

- Nếu muốn mở rộng thêm sản phẩm, thêm mã Yahoo Finance vào `--symbols`, ví dụ:

```powershell
python oil_price_tracker.py --symbols CL=F,BZ=F,NG=F
```

- Để chạy tự động mỗi giờ trên Windows, dùng Task Scheduler và gọi script này.
- Repo hiện có workflow GitHub Actions chạy mỗi giờ và tự cập nhật `oil_price_history.csv`.
