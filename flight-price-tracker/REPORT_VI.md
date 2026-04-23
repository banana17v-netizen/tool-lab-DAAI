# Báo Cáo Dự Án Theo Dõi Giá Vé Máy Bay Và Chi Phí Nhiên Liệu

## 1. Tổng quan dự án

Dự án này xây dựng một hệ thống theo dõi giá vé máy bay và chi phí nhiên liệu theo thời gian gần thực, phục vụ bài toán phân tích xu hướng giá vé nội địa Việt Nam trong bối cảnh biến động của giá dầu Brent và tỷ giá USD/VND. Hệ thống không đi theo cách crawl HTML truyền thống, mà ưu tiên hướng tiếp cận API-first: bắt request thật từ trình duyệt, xác thực request, sau đó để worker gọi trực tiếp endpoint bằng HTTP client.

Trong phiên bản hiện tại, hệ thống gồm 4 thành phần chính:

- `db-service`: PostgreSQL lưu dữ liệu giao dịch giá vé và dữ liệu nhiên liệu.
- `scraper-service`: worker Python gọi endpoint availability để lấy dữ liệu giá vé.
- `fuel-worker`: worker Python lấy giá Brent, tỷ giá USD/VND và tính chi phí Jet A1 ước tính.
- `dashboard-service`: ứng dụng Streamlit hiển thị dashboard phân tích.

Kiến trúc này được mô tả trong [docker-compose.yml](/c:/Lab%20aPhong/flight-price-tracker/docker-compose.yml).

## 2. Mục tiêu của dự án

Mục tiêu chính của dự án là xây dựng một công cụ có khả năng:

1. Theo dõi giá vé máy bay theo chu kỳ lặp lại, không phụ thuộc thao tác tay trên trình duyệt.
2. Lưu dữ liệu giá vé vào cơ sở dữ liệu để truy vết và vẽ biểu đồ.
3. Bổ sung góc nhìn kinh tế vĩ mô thông qua chi phí nhiên liệu hàng không.
4. Hiển thị dữ liệu dưới dạng dashboard để người dùng có thể quan sát xu hướng nhanh.
5. Lưu dữ liệu thô để phục vụ phân tích lịch sử và backtest sau này.

Nói cách khác, đây không chỉ là một script scrape giá vé, mà là một hệ thống thu thập dữ liệu, lưu trữ, diễn giải và quan sát theo dạng service.

## 3. Yêu cầu nghiệp vụ và yêu cầu kỹ thuật

### 3.1. Yêu cầu nghiệp vụ

- Theo dõi được giá vé theo từng đợt scrape.
- Hiển thị thông tin chuyến bay, thời gian bay, nhóm giá hoặc fare class và giá.
- Theo dõi biến động chi phí nhiên liệu có liên quan đến bài toán giá vé.
- Cho phép xem dữ liệu mới nhất và xu hướng theo thời gian.
- Có khả năng mở rộng sang thêm route, ngày bay hoặc nguồn dữ liệu khác.

### 3.2. Yêu cầu kỹ thuật

- Hệ thống phải chạy ổn định dạng dịch vụ nền.
- Có cơ chế retry và log lỗi khi endpoint lỗi tạm thời.
- Có thể đóng gói bằng Docker để dễ khởi động và triển khai.
- Tách biệt lớp thu thập dữ liệu, lớp lưu trữ và lớp hiển thị.
- Lưu dữ liệu có cấu trúc để có thể phân tích lại.
- Hạn chế phụ thuộc vào trình duyệt thật và thao tác giao diện.

## 4. Kiến trúc hệ thống

### 4.1. Kiến trúc tổng thể

Hệ thống được thiết kế theo mô hình service phân tách rõ ràng:

- Một service thu thập giá vé.
- Một service thu thập dữ liệu nhiên liệu.
- Một cơ sở dữ liệu tập trung.
- Một dashboard chỉ đọc để hiển thị.

Ưu điểm của mô hình này là dễ theo dõi, dễ debug, dễ thay thế từng khối thành phần và giảm mức độ phụ thuộc lẫn nhau.

### 4.2. Luồng dữ liệu giá vé

Luồng dữ liệu giá vé được thực hiện như sau:

1. Scheduler trong [scraper-worker/app/main.py](/c:/Lab%20aPhong/flight-price-tracker/scraper-worker/app/main.py) chạy theo chu kỳ.
2. Worker gọi endpoint availability bằng `httpx`.
3. Response JSON được parser thành danh sách `TicketPriceRecord`.
4. Bản ghi được ghi vào bảng `flight_price_ticks`.
5. Snapshot request/response được lưu vào `raw_data` để truy vết.

Bảng `flight_price_ticks` được định nghĩa tại [db/01-schema.sql](/c:/Lab%20aPhong/flight-price-tracker/db/01-schema.sql), gồm các cột:

- `timestamp`
- `flight_number`
- `departure_time`
- `fare_class`
- `price`

### 4.3. Luồng dữ liệu nhiên liệu

Luồng dữ liệu nhiên liệu được thực hiện như sau:

1. Fuel worker chạy theo lịch interval.
2. Lấy giá Brent từ chuỗi nguồn ưu tiên: Yahoo Chart, nếu bị chặn thì fallback sang Stooq.
3. Lấy tỷ giá USD/VND từ Vietcombank.
4. Tính giá Jet A1 và chi phí nhiên liệu ước tính cho chặng HAN-SGN.
5. Ghi vào bảng `fuel_metrics` và snapshot CSV tháng.

Bảng `fuel_metrics` trong [db/01-schema.sql](/c:/Lab%20aPhong/flight-price-tracker/db/01-schema.sql) không chỉ lưu giá trị, mà còn lưu provenance:

- `brent_source`
- `exchange_rate_source`
- `brent_price_timestamp`
- `exchange_rate_timestamp`
- `is_fallback`
- `source_note`

Đây là một điểm mạnh của dự án, vì nó giúp phân biệt dữ liệu live và dữ liệu fallback, tránh trường hợp dashboard nhìn có vẻ hợp lệ nhưng thực chất đang dùng giá trị thay thế.

### 4.4. Luồng hiển thị dashboard

Dashboard trong [dashboard-service/app.py](/c:/Lab%20aPhong/flight-price-tracker/dashboard-service/app.py) đọc read-only từ PostgreSQL, sau đó hiển thị:

- Fare ticks theo từng `flight_number | fare_class`
- Fuel metrics mới nhất
- Biểu đồ Jet A1 và chi phí nhiên liệu theo thời gian
- Chỉ số so sánh daily giữa giá vé trung bình và fuel cost

Vì dashboard chỉ đọc, nó giúp giảm rủi ro tác động ngược vào dữ liệu vận hành.

## 5. Công nghệ được sử dụng và lý do lựa chọn

### 5.1. Python

Python được chọn vì phù hợp với bài toán thu thập dữ liệu, xử lý JSON, thao tác với HTTP, và tạo dashboard nhanh. Hệ sinh thái Python có sẵn nhiều thư viện hỗ trợ mạnh cho web data, async và phân tích dữ liệu.

### 5.2. httpx

`httpx` là thành phần trung tâm trong scraper.

Lý do dùng `httpx`:

- Hỗ trợ async tốt.
- Hỗ trợ HTTP/2, phù hợp với một số endpoint hiện đại.
- Dễ cấu hình header, cookie, timeout, verify SSL.
- Nhẹ hơn so với việc dùng browser automation.

Trong bài toán này, `httpx` là lựa chọn hợp lý nhất vì dữ liệu mục tiêu đã tồn tại dưới dạng API response JSON. Nghĩa là bài toán cần một API client ổn định, không cần một HTML crawler.

### 5.3. PostgreSQL

PostgreSQL được dùng để lưu dữ liệu hot-path vì:

- Ổn định.
- Dễ truy vấn.
- Phù hợp với dữ liệu time-series nhỏ và vừa.
- Dễ kết hợp với dashboard.

So với việc lưu thường trực bằng file CSV hoặc JSON thuần, PostgreSQL cho phép truy vấn nhanh hơn, lọc tốt hơn, và là nền tảng phù hợp khi hệ thống cần mở rộng.

### 5.4. Streamlit

Streamlit được chọn cho dashboard vì:

- Dựng nhanh.
- Thích hợp prototype và monitoring nội bộ.
- Tích hợp tốt với Pandas và Plotly.
- Giảm thời gian xây UI so với React hoặc một web app full-stack.

Với dự án này, mục tiêu là dashboard phân tích dữ liệu, không phải sản phẩm front-end phức tạp. Vì vậy Streamlit là lựa chọn hiệu quả.

### 5.5. Plotly

Plotly được dùng để vẽ biểu đồ vì:

- Hiển thị dữ liệu tương tác tốt.
- Dễ tích hợp vào Streamlit.
- Hỗ trợ biểu đồ line, marker, hover metadata.

Điều này đặc biệt hữu ích trong phần provenance của fuel metrics.

### 5.6. Docker Compose

Docker Compose được dùng để đóng gói và khởi động toàn bộ hệ thống vì:

- Dễ tái lập môi trường.
- Dễ tách service.
- Giảm lỗi chênh lệch môi trường giữa máy phát triển và máy chạy.
- Dễ thao tác bằng một lệnh duy nhất.

## 6. Tại sao dự án không chọn crawl HTML truyền thống làm hướng chính

Đây là phần quan trọng nhất của báo cáo này.

Bản chất của dự án là theo dõi dữ liệu availability đã được website tải về từ endpoint bên dưới. Vì vậy, nếu đi crawl HTML theo cách truyền thống thì sẽ gặp nhiều bất lợi:

- HTML dễ thay đổi giao diện và DOM.
- Có thể phải xử lý JavaScript render.
- Khó được dữ liệu sạch bằng JSON gốc.
- Chi phí bảo trì parser cao.

Vì thế, hướng API-first được chọn là giải pháp đúng bản chất của hệ thống hơn: tìm request thật, gọi lại request đó, parser response JSON.

## 7. So sánh với các công cụ lấy dữ liệu web khác

### 7.1. So với Beautiful Soup

Beautiful Soup phù hợp khi:

- Cần parse HTML.
- Cần tìm thẻ, class, script nhúng trong trang.

Nhưng đối với dự án này, Beautiful Soup không phải công cụ chính vì:

- Response mục tiêu là JSON API, không phải HTML.
- Beautiful Soup không chạy JavaScript.
- Nếu DOM đổi, parser HTML sẽ vỡ nhanh.

Lợi thế của hướng hiện tại so với Beautiful Soup:

- Lấy dữ liệu trực tiếp ở lớp nguồn.
- Ít phụ thuộc vào giao diện website.
- Parser sạch và ổn định hơn.
- Hiệu năng tốt hơn.

Kết luận: Beautiful Soup chỉ nên dùng như công cụ phụ trong trường hợp cần đọc HTML bootstrap hoặc JSON nhúng trong `script`, không nên là runtime parser chính.

### 7.2. So với Scrapy

Scrapy rất mạnh khi:

- Crawl nhiều trang.
- Follow link.
- Quản lý queue URL lớn.
- Xây dựng pipeline item phức tạp.

Tuy nhiên, dự án này không phải bài toán crawl web quy mô lớn mà là bài toán gọi một số endpoint cụ thể theo lịch. Vì vậy Scrapy sẽ gây dư kiến trúc:

- Tăng độ phức tạp vận hành.
- Thêm framework Twisted và spider lifecycle.
- Không giải quyết tốt hơn bài toán session-bound API.

Lợi thế của hướng hiện tại so với Scrapy:

- Nhẹ hơn.
- Dễ debug hơn.
- Phù hợp hơn với mô hình poller-service.
- Tập trung đúng bài toán: API client thay vì crawler framework.

Kết luận: Scrapy là lựa chọn tốt nếu sau này cần mở rộng thành hệ thống crawl nhiều site, nhiều page, nhiều bước. Còn hiện tại, nó không phải công cụ tối ưu.

### 7.3. So với Selenium hoặc Playwright

Selenium và Playwright rất hữu ích khi:

- Phải mở trình duyệt thật.
- Phải xử lý JavaScript phức tạp.
- Phải login, click, chờ render xong mới lấy được dữ liệu.

Nhưng chi phí của chúng rất rõ:

- Nặng.
- Tốn RAM/CPU hơn.
- Chậm hơn.
- Khó scale hơn.
- Dễ bị anti-bot nhận diện hơn.

Trong dự án này, nếu request đã được reverse-engineer thành công thì dùng browser automation mỗi chu kỳ là không cần thiết.

Lợi thế của hướng hiện tại so với Selenium/Playwright:

- Nhanh hơn.
- Ổn định hơn.
- Giảm phụ thuộc vào giao diện.
- Dễ containerize hơn.

Kết luận: Playwright nên được xem là công cụ discovery hoặc bootstrap session, không nên là runtime chính nếu có thể gọi API trực tiếp.

### 7.4. So với RapidAPI Client, Postman, Insomnia

Những công cụ này rất hữu ích để:

- Khám phá request.
- Thử lại header, cookie, query, body.
- Xác thực response.

Nhưng chúng không phải runtime engine cho hệ thống production. Vì vậy, dự án chỉ nên dùng các công cụ này ở giai đoạn discovery và debug.

Lợi thế của hướng hiện tại:

- Worker được viết bằng code thật, tự động hóa, chạy theo lịch.
- Không phụ thuộc vào công cụ GUI ngoài.
- Dễ triển khai và version control hơn.

## 8. Những quyết định thiết kế quan trọng

### 8.1. Chọn API-first thay vì HTML-first

Đây là quyết định quan trọng nhất, vì nó giảm độ mong manh của hệ thống.

### 8.2. Tách worker giá vé và worker nhiên liệu

Hai bài toán này có chu kỳ cập nhật, nguồn dữ liệu và cách xử lý khác nhau. Tách ra giúp:

- Dễ debug.
- Dễ scale.
- Không để lỗi ở một nguồn kéo sập toàn hệ thống.

### 8.3. Lưu snapshot thô bên cạnh dữ liệu đã chuẩn hóa

Dữ liệu đã chuẩn hóa phục vụ dashboard, còn snapshot thô phục vụ truy vết và backtest. Đây là thiết kế tốt cho các hệ thống thu thập dữ liệu thực tế.

### 8.4. Bổ sung provenance cho fuel metrics

Thay vì chỉ lưu giá trị, hệ thống lưu thêm nguồn gốc và fallback status. Quyết định này giúp dashboard trung thực hơn và giúp người vận hành phân biệt dữ liệu thật với dữ liệu thay thế.

## 9. Kết quả đạt được

Tại thời điểm báo cáo này, hệ thống đã đạt được các kết quả chính:

- Dashboard chạy thành công trên cổng `8502`.
- Scraper-service gọi thành công endpoint availability và lưu dữ liệu giá vé vào PostgreSQL.
- Fuel-worker cập nhật giá Brent và USD/VND theo chu kỳ, đồng thời có fallback chain hoạt động.
- Dashboard hiển thị đồng thời giá vé, fuel metrics và daily index.

Nói cách khác, dự án đã đi từ mức prototype script đơn lẻ thành một hệ thống monitoring có cấu trúc rõ ràng.

## 10. Hạn chế hiện tại

Dự án vẫn còn một số hạn chế thực tế:

- Endpoint availability hiện tại có tính session-bound.
- Cookie và URL có thể cần refresh sau một thời gian.
- Dashboard hiện đang thiên về monitoring nội bộ, chưa phải sản phẩm dashboard doanh nghiệp hoàn chỉnh.
- Chưa có cơ chế loại bỏ duplicate theo logic nghiệp vụ cao hơn.

Đây là những hạn chế bình thường với bài toán reverse engineering request web trong môi trường thật.

## 11. Hướng phát triển tiếp theo

Có thể phát triển thêm theo các hướng sau:

1. Tự động hóa bước tạo session hoặc refresh cookie.
2. Bổ sung cơ chế deduplicate nâng cao cho dữ liệu giá vé.
3. Mở rộng theo dõi nhiều route nội địa hơn.
4. Bổ sung cảnh báo khi giá vé hoặc fuel cost biến động vượt ngưỡng.
5. Tách dashboard sang một giao diện production-ready nếu cần phục vụ nhiều người dùng hơn.

## 12. Kết luận

Dự án này chọn hướng tiếp cận đúng với bản chất bài toán: không crawl HTML một cách mù quáng, mà reverse-engineer request availability và gọi lại endpoint thật bằng `httpx`. Đây là lý do công cụ trung tâm của hệ thống là HTTP client, PostgreSQL, Streamlit và Docker Compose, thay vì các công cụ crawl HTML hay browser automation làm runtime chính.

So với Beautiful Soup, Scrapy, Selenium, Playwright hay các GUI client như RapidAPI Client, hướng hiện tại có lợi thế rõ ràng về sự gọn nhẹ, ổn định, dễ debug và phù hợp hơn với bài toán theo dõi API theo lịch. Các công cụ kia vẫn có giá trị, nhưng nên được dùng đúng vai trò: discovery, bootstrap, hỗ trợ debug, hoặc mở rộng trong các bài toán lớn hơn.

Với cách thiết kế này, dự án đã tạo được một nền tảng hợp lý để tiếp tục mở rộng thành hệ thống theo dõi giá vé và nhiên liệu có khả năng phân tích, truy vết và vận hành tốt hơn trong thực tế.