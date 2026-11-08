"""Generate release details and a five-page screenshot gallery from tagged source."""
from __future__ import annotations

import html
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

PAGES = {
    "home": "Home — ภาพรวมและทางลัด",
    "import": "Import Games — นำเข้าไฟล์ ISO",
    "library": "Games & Artwork — เกมและภาพปก",
    "storage": "USB / Storage — จัดการที่เก็บข้อมูล",
    "settings": "Settings — ตั้งค่าแอป",
}


def change_history(tag: str) -> tuple[str | None, str, str]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    previous = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", "--match=v*", f"--exclude={tag}", "HEAD^"],
        capture_output=True, text=True,
    )
    baseline = previous.stdout.strip() if previous.returncode == 0 else None
    revision = f"{baseline}..HEAD" if baseline else "HEAD"
    changes = subprocess.check_output(["git", "log", "--no-merges", "--format=- %s (%h)", revision], text=True).strip()
    return baseline, changes or "- ไม่มี commit ใหม่ในช่วงนี้", commit


def render_notes(repository: str, tag: str, installer: str, previous: str | None, changes: str, commit: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ValueError("Invalid repository or release tag")
    root = f"https://github.com/{repository}"
    assets = f"{root}/releases/download/{tag}"
    cards = [
        f'<a href="{assets}/windows-{page}.png"><img src="{assets}/windows-{page}.png" width="150" alt="{html.escape(label, quote=True)}"></a><br><sub>{html.escape(label)}</sub>'
        for page, label in PAGES.items()
    ]
    gallery = (
        "| | | |\n| :---: | :---: | :---: |\n"
        + "| " + " | ".join(cards[:3]) + " |\n"
        + "| " + " | ".join(cards[3:]) + " | |"
    )
    comparison = f"[ดูการเปลี่ยนแปลงทั้งหมด]({root}/compare/{quote(previous, safe='')}...{tag})" if previous else "รุ่นแรก: แสดงประวัติ commit ทั้งหมดที่นำมาสร้างรุ่นนี้"
    return f"""<div align="center">

<sub>PS2 GAME LIBRARY · USB STORAGE · OPL</sub>

# PS2 TOOLKIT 2000X

### {tag} · Windows Edition

เตรียมเกม จัดการ USB และดูแลภาพปกสำหรับ Open PS2 Loader ในแอปเดียว

**[ดาวน์โหลดสำหรับ Windows]({assets}/{quote(installer, safe='')})** &nbsp; · &nbsp; [คู่มือใช้งาน]({root}/blob/{tag}/docs/HOW_TO_USE.md) &nbsp; · &nbsp; [แจ้งปัญหา]({root}/issues)

</div>

---

| รุ่นที่เผยแพร่ | ระบบที่รองรับ | ภาษา | รูปแบบติดตั้ง |
| :--- | :--- | :--- | :--- |
| **{tag}** | Windows 10 / 11 · **64-bit** | ไทย / English | `.exe` · รวม runtime แล้ว |

## ดาวน์โหลด

**[↓ {installer}]({assets}/{quote(installer, safe='')})**

ดาวน์โหลดตัวติดตั้งด้านบน เปิดไฟล์ แล้วทำตามขั้นตอน ไม่ต้องติดตั้ง Python แยก
หากมีรุ่นเดิม ให้ปิดแอปก่อนติดตั้งรุ่นใหม่

> **ก่อนติดตั้ง:** รุ่นนี้สำหรับ Windows 64-bit และยังไม่มีลายเซ็นดิจิทัล จึงอาจพบข้อความเตือนจาก SmartScreen ตรวจสอบแหล่งดาวน์โหลดและ SHA-256 ก่อนเปิดไฟล์

## อัปเดตในรุ่นนี้

รายการจาก commit จริง{f' หลัง {previous}' if previous else ''}:

{changes}

{comparison}

## สำรวจแอป

ภาพหน้าจอจริง 5 หน้าจากแอปที่ติดตั้งบน Windows CI · **กดภาพเพื่อดูขนาดเต็ม**

{gallery}

<sub>ภาพตัวอย่างกว้างภาพละ 150 px · CI ไม่มี USB เกมจริง จึงอาจแสดงรายการว่าง</sub>

## ทำอะไรได้บ้าง

| งาน | ความสามารถ |
| :--- | :--- |
| **นำเข้าเกม** | เลือก ISO หลายไฟล์ อ่าน PS2 Game ID จัดชื่อและโฟลเดอร์ CD/DVD ให้เหมาะกับ OPL พร้อมความคืบหน้าและยกเลิกงาน |
| **จัดการไฟล์ขนาดใหญ่** | แบ่ง ISO ที่เกินขีดจำกัด FAT เป็นส่วนย่อยในรูปแบบ USBExtreme |
| **ดูแลคลังเกม** | สแกนเกม ดูพื้นที่จัดเก็บ และลบเกมผ่านหน้าจอยืนยัน |
| **ภาพปกและ artwork** | เพิ่ม เปลี่ยน ลบ PNG/JPG/WEBP หรือดาวน์โหลดจากแหล่งออนไลน์ |
| **เตรียม USB** | ตรวจสอบอุปกรณ์ภายนอก สร้างโฟลเดอร์ OPL และฟอร์แมตอุปกรณ์ที่ผ่านการตรวจสอบ |
| **ใช้งานสะดวก** | UI ไทย/อังกฤษ และแนะนำอัปเดตเมื่อมี GitHub Release ตัวเต็มที่ใหม่กว่า |

งานนำเข้าและจัดการไฟล์ใช้ได้ **ออฟไลน์** ส่วนดาวน์โหลด artwork และเช็กอัปเดตต้องใช้อินเทอร์เน็ต

## เริ่มใช้งานใน 3 ขั้นตอน

1. **ติดตั้งและเปิดแอป** — ยืนยันสิทธิ์ Administrator เมื่อ Windows ขอ
2. **ต่อ USB ภายนอก** — ตรวจสอบรุ่นอุปกรณ์ ไดรฟ์ และพื้นที่ว่างก่อนเลือกปลายทาง
3. **นำเข้า ISO** — เปิด Import Games เลือกไฟล์ และตรวจสอบผลใน Games & Artwork

> **การฟอร์แมตจะลบข้อมูลทั้งหมดบนอุปกรณ์ที่เลือก** สำรองข้อมูลและตรวจสอบปลายทางทุกครั้ง ไม่รวมไฟล์เกม ISO ใน release

<details>
<summary><strong>ตรวจสอบความถูกต้องของไฟล์ดาวน์โหลด</strong></summary>

ดาวน์โหลด [SHA256SUMS.txt]({assets}/SHA256SUMS.txt) และเปรียบเทียบค่า SHA-256 ของตัวติดตั้ง เช่น:

```powershell
Get-FileHash .\\{installer} -Algorithm SHA256
```

ค่าแฮชต้องตรงกับชื่อไฟล์เดียวกันใน `SHA256SUMS.txt` ซึ่งมีค่าของตัวติดตั้งและภาพหน้าจอทั้ง 5 รูป

</details>

<details>
<summary><strong>การทดสอบและข้อมูล build</strong></summary>

| รายการ | รายละเอียด |
| :--- | :--- |
| ชุดทดสอบ | Windows Server 2022 และ 2025 |
| ตรวจตัวติดตั้ง | ติดตั้ง เปิดแอป และถ่ายภาพทั้ง 5 หน้าบน Windows Server 2022 |
| ข้อมูลทดสอบ | ISO และอุปกรณ์จำลอง ไม่ฟอร์แมตดิสก์จริง |
| ข้อจำกัด | ไม่ใช่การรับรอง Windows 10/11 ทุกเครื่อง และยังไม่ทดสอบการเล่นเกมบน PS2 |
| เวอร์ชันในแอป | `{tag[1:]}` ใส่จาก tag เฉพาะตอน build โดยไม่มี commit เพิ่มหรือย้าย tag |

Source commit: [{commit}]({root}/commit/{commit})

</details>

---

พบปัญหา? [เปิด Issue]({root}/issues/new) พร้อมเวอร์ชันแอป รุ่น Windows และขั้นตอนที่ทำให้เกิดปัญหา
"""



def main() -> None:
    tag = os.environ["RELEASE_TAG"]
    previous, changes, commit = change_history(tag)
    installers = list(Path("dist").glob("*-Setup-*.exe"))
    if len(installers) != 1:
        raise RuntimeError("Expected exactly one Windows installer")
    for page in PAGES:
        if not (Path("dist") / f"windows-{page}.png").is_file():
            raise RuntimeError(f"Missing screenshot: {page}")
    Path("release-notes.md").write_text(render_notes(os.environ["REPOSITORY"], tag, installers[0].name, previous, changes, commit), encoding="utf-8")


if __name__ == "__main__":
    main()
