# Real-time Flight Price Tracker

Tool nay duoc dieu chinh theo workflow reverse engineering API availability: dung RapidAPI Client hoac DevTools de xac thuc request, sau do de Python worker goi truc tiep endpoint that moi 60 giay thay vi phu thuoc vao proxy trung gian.

## Kien truc Docker Compose

- `db-service`: PostgreSQL luu luong nong de dashboard doc nhanh
- `scraper-service`: worker Python async goi endpoint availability moi 60 giay
- `fuel-worker`: worker Python lay Brent + USD/VND, tinh chi phi Jet A1, va ghi snapshot CSV thang
- `dashboard-service`: Streamlit doc read-only tu PostgreSQL de ve bieu do thoi gian thuc
- `raw_data/`: luong lanh chua snapshot JSONL theo ngay cua API gia ve, de theo doi bang DVC
- `fuel_data/`: luong lanh chua snapshot CSV thang cua chi so nhien lieu, de theo doi bang DVC

## 1) Reverse engineering API availability

1. Mo trang tim chuyen bay cua Vietnam Airlines o che do an danh.
2. Nhap route vi du `HAN -> SGN`, chon ngay bay, bam tim kiem.
3. Mo `F12 -> Network -> Fetch/XHR`.
4. Tim request tra ve JSON co danh sach itinerary, legs, segments, price hoac fare option.
5. Copy cac thong tin sau vao `.env`:
   - `VNA_API_URL`
   - `VNA_API_METHOD`
  - `VNA_PARSER_MODE`
   - `VNA_HEADERS_TEMPLATE`
   - `VNA_QUERY_TEMPLATE` neu la GET
   - `VNA_PAYLOAD_TEMPLATE` neu la POST
  - `VNA_BEARER_TOKEN`, `VNA_SESSION_ID`, `VNA_COOKIE` neu request can token, cookie, hoac session

Worker se tu dong thay placeholder `{origin}`, `{destination}`, `{travel_date}` trong payload/query moi chu ky quet.

Neu dung schema itinerary availability cua Skyscanner, hay doi:

- `VNA_API_METHOD=GET`
- `VNA_PARSER_MODE=skyscanner_itineraries`
- `VNA_COOKIE` bang cookie session hien tai

Neu dung schema fare-family/brand chi tiet khac, hay doi:

- `VNA_API_URL` sang endpoint availability/offer chi tiet
- `VNA_PARSER_MODE=fare_options` neu payload tra ve danh sach fare family/brand theo tung chuyen bay
- `VNA_PARSER_MODE=auto` neu ban dang thu nghiem va muon scraper thu parser chi tiet truoc roi fallback ve `best_price_calendar`

## 2) Cau hinh route va ngay quet

Danh sach thi truong nam trong [scraper-worker/config/flights.json](c:\Lab aPhong\flight-price-tracker\scraper-worker\config\flights.json).

Luu y: voi mot so endpoint availability kieu Skyscanner, URL co the gan voi mot search session cu the. Khi do route/day trong `flights.json` chi nen de mot cau hinh khop voi request dang dung; neu muon doi ngay hoac route that su, ban can bat lai request session moi.

Vi du, worker se quet tung route voi cac moc ngay `7`, `14`, `30` ngay toi:

```json
[
  {
    "origin": "HAN",
    "destination": "SGN",
    "days_ahead": [7, 14, 30]
  }
]
```

## 3) Luong nong trong PostgreSQL

Bang nong la `flight_price_ticks` voi cau truc toi gian:

- `timestamp`
- `flight_number`
- `departure_time`
- `fare_class`
- `price`

Dashboard chi doc bang nay de ve bieu do realtime.

## 4) Luong lanh + DVC

Moi lan worker goi API, toan bo request/response duoc gom thanh mot snapshot va append vao file JSONL theo ngay:

- `raw_data/YYYY/MM/DD/vna_raw_YYYYMMDD.jsonl`

De dua vao DVC:

1. `dvc init`
2. `dvc add raw_data`
3. `git add raw_data.dvc .gitignore .dvc/`
4. Cau hinh remote va day du lieu:
   - `dvc remote add -d storage <s3-or-gdrive-or-minio-url>`
   - `dvc push`

Khi can backtest, chi can `dvc pull` dung version du lieu tho cua tung thoi diem.

## 5) Khoi dong he thong

1. Tao `.env` tu [flight-price-tracker/.env.example](c:\Lab aPhong\flight-price-tracker\.env.example).
2. Cap nhat [scraper-worker/config/flights.json](c:\Lab aPhong\flight-price-tracker\scraper-worker\config\flights.json) theo route can theo doi.
3. Chay:

```powershell
docker compose up --build -d
```

4. Xem log worker:

```powershell
docker compose logs -f scraper-service
```

5. Mo dashboard:

- `http://localhost:8501`

## 6) Fuel Worker va cong thuc Jet A1

Worker nhien lieu bo sung mot chi bao macro cho bai toan gia ve. Cong thuc duoc ap dung la:

$$
Gia\_JetA1\_VN = \left( \frac{Brent \times he\_so\_proxy \times USD/VND}{158.987} \right) + Thue\_NK + Thue\_BVMT + Phi\_Premium
$$

Trong implementation hien tai:

- `Brent` duoc lay qua `yfinance` voi ma `BZ=F`
- `USD/VND` duoc lay tu XML/JSON cua Vietcombank qua `VCB_EXCHANGE_URL`
- cac hang so thue, premium, va muc tieu thu nhien lieu cua chuyen `HAN-SGN` nam trong [fuel-worker/config/pricing.json](c:\Lab aPhong\flight-price-tracker\fuel-worker\config\pricing.json)

Bang `fuel_metrics` trong PostgreSQL luu:

- `timestamp`
- `brent_price_usd`
- `exchange_rate`
- `jet_a1_est_vnd`
- `han_sgn_fuel_cost`
- `brent_source`
- `exchange_rate_source`
- `brent_price_timestamp`
- `exchange_rate_timestamp`
- `is_fallback`
- `source_note`

Du lieu luu lanh duoc append vao file CSV theo thang:

- `fuel_data/YYYY/MM/fuel_metrics_YYYYMM.csv`

## 7) Cau hinh lich fuel worker

Bien moi trong [.env.example](c:\Lab aPhong\flight-price-tracker\.env.example):

- `FUEL_SCHEDULE_MODE=daily` de chay 1 lan/ngay, `hourly` de chay theo gio, hoac `interval` de chay theo phut
- `FUEL_DAILY_HOUR=8` de chay luc 8h sang theo `FUEL_TIMEZONE`
- `FUEL_HOURLY_INTERVAL=1` neu theo doi futures moi gio
- `FUEL_INTERVAL_MINUTES=5` neu muon cap nhat moi 5 phut o che do `interval`
- `FUEL_RUN_ON_STARTUP=true` de nap ngay mot mau khi container vua khoi dong

## 8) DVC cho fuel metrics

De dua snapshot kinh te vi mo len S3 bang DVC:

1. `dvc add fuel_data`
2. `git add fuel_data.dvc .gitignore`
3. `dvc remote add -d storage s3://<bucket-name>/<path>`
4. `dvc push`

Luc train mo hinh time-series cho gia ve, ban co the `dvc pull` dung snapshot cua thang can backtest.

## 9) Luu y van hanh

- Worker duoc boc bang `try/except`, neu request loi o phut hien tai thi chi log loi va chay tiep o phut sau.
- Parser dang dung heuristic + parser chuyen biet cho `best_price_calendar`, `fare_options`, va `skyscanner_itineraries`.
- Neu dung request availability gan voi session/cookie, can refresh `VNA_COOKIE` va co the ca `VNA_API_URL` khi session het han.
- Fuel worker cung fail-safe theo chu ky; neu Yahoo Finance hoac endpoint Vietcombank loi, worker chi log loi va doi den chu ky ke tiep.
- Luon tuan thu terms of service cua nguon du lieu.
