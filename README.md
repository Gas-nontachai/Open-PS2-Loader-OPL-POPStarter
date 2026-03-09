# PS2 TOOLKIT 2000X

Desktop app สำหรับจัดการเกม PS2 บน USB เพื่อใช้งานกับ Open PS2 Loader (OPL)
สร้างด้วย **Flet + Python** และรองรับการทำงานแบบข้ามแพลตฟอร์ม

- จัดการโฟลเดอร์ OPL อัตโนมัติ (`CD`, `DVD`, `ART`, `CFG`, ...)
- นำเข้า ISO และตั้งชื่อไฟล์ตามรูปแบบ OPL
- สแกน/ลบเกม พร้อมสรุปพื้นที่ใช้งาน
- จัดการ ART แบบ Manual และ Auto (RAWG)
- แสดงสถานะ + progress + event log ระหว่างทำงาน

---

## 1) Requirements

- macOS / Windows / Linux
- Python 3.9+
- สิทธิ์อ่าน/เขียน USB drive
- อินเทอร์เน็ต (เฉพาะโหมดค้นหา ART อัตโนมัติ)

> แนะนำให้ใช้ virtual environment แยกสำหรับโปรเจกต์

---

## 2) Setup

### 2.1 Clone และเข้าโฟลเดอร์

```bash
git clone <your-repo-url>
cd PS2_FD
```

### 2.2 สร้าง virtual environment และติดตั้ง dependencies

```bash
python3 -m venv .venv_flet
source .venv_flet/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2.3 ตั้งค่า `.env`

ตัวอย่างไฟล์อยู่ที่ `.env.example`

ค่าที่สำคัญ:

- `RAWG_API_KEY`
- `ART_SEARCH_CACHE_TTL_SEC`
- `ART_SEARCH_CACHE_MAX_SIZE`
- `ART_SEARCH_RATE_LIMIT_PER_MIN`
- `ART_SEARCH_MIN_INTERVAL_SEC`

---

## 3) Run (Development)

```bash
source .venv_flet/bin/activate
flet run app/main.py
```

หากเจอปัญหา `flet: command not found` ให้รันใน venv เดิมตามคำสั่งด้านบน (อย่าเรียกจาก global python)

---

## 4) การใช้งานหลักในแอป

1. เลือกโฟลเดอร์ปลายทาง (USB)
2. กดตรวจสอบปลายทาง
3. เลือกไฟล์ ISO แล้วนำเข้า
4. กดสแกนเกมเพื่อตรวจรายการ
5. ไปแท็บ ART เพื่อค้นหา/อัปโหลดภาพ
6. บันทึก ART ลงโฟลเดอร์ `ART`

---

## 5) Build สำหรับแจกจ่าย

### 5.1 Build macOS `.app`

```bash
source .venv_flet/bin/activate
pip install pyinstaller
flet pack app/main.py --name "PS2 Toolkit" -y
```

ผลลัพธ์อยู่ใน `dist/PS2 Toolkit.app`

### 5.2 สร้าง `.dmg` แบบลากลง Applications

```bash
# ติดตั้งเครื่องมือครั้งเดียว
brew install create-dmg

# สร้าง dmg พร้อม layout
create-dmg \
  --volname "PS2 Toolkit" \
  --window-pos 200 120 \
  --window-size 760 460 \
  --icon-size 120 \
  --background "packaging/dmg/background.png" \
  --icon "PS2 Toolkit.app" 180 260 \
  --hide-extension "PS2 Toolkit.app" \
  --app-drop-link 580 260 \
  "dist/PS2-Toolkit-Installer.dmg" \
  "dist/PS2 Toolkit.app"
```

### 5.3 ฝั่ง Windows (`.exe`)

ให้ build บนเครื่อง Windows โดยตรง:

```bash
flet pack app/main.py --name "PS2 Toolkit" -y
```

---

## 6) Project Structure

```text
app/
  __init__.py
  main.py
  core/
    constants.py
    i18n.py
    schemas.py
  services/
    target_service.py
    format_service.py
    game_service.py
    art_service.py
  controllers/
    import_controller.py
    game_controller.py
    art_controller.py
  ui/
    app_layout.py
    import_tab.py
    art_tab.py
    console_panel.py
    dialogs.py
    state.py
packaging/
  dmg/
    background.png
requirements.txt
```

---

## 7) Troubleshooting

### แอปเปิดแล้วปิดทันที

- อัปเดตล่าสุดแก้แล้วด้วยการเพิ่ม `app/__init__.py`
- ให้ build ใหม่เสมอหลังดึงโค้ดล่าสุด

### `Please install PyInstaller module`

```bash
pip install pyinstaller
```

### macOS เปิดแอปครั้งแรกแล้วโดนบล็อก

- คลิกขวาแอป > `Open`
- หรือไป `System Settings > Privacy & Security` แล้วกด `Open Anyway`

### เปิดจาก DMG แล้วพอปิดหน้าต่างแอปหาย

- ต้องลาก `PS2 Toolkit.app` ไป `Applications` ก่อน
- ถ้าเปิดตรงจาก DMG แอปจะหายเมื่อ unmount

---

## 8) Development Notes

- โค้ดเดิมแบบ FastAPI/Web ถูก migrate มา Flet Desktop แล้ว
- การ format USB ใช้คำสั่งตาม OS:
  - macOS: `diskutil`
  - Windows: `diskpart`
  - Linux: `mkfs.vfat`
- ฟีเจอร์ Auto ART ต้องมี `RAWG_API_KEY` ใน `.env`

---

## 9) License

ระบุ license ตามที่ใช้งานใน repo นี้ (ถ้ามี)
