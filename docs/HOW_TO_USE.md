# How to use PS2 TOOLKIT 2000X

## 1. Connect external storage

Connect a USB flash drive, external USB HDD or external USB SSD. Open the application and click **Refresh Devices**. Only storage whose physical connection is verified as USB appears.

Windows asks for Administrator permission whenever the application starts. Click **Yes** so it can manage external storage safely.

Check the device model, drive letter, capacity and filesystem before continuing.

## 2. Import PS2 games

1. Open **Import Games**.
2. Select the destination device.
3. Select one or more PS2 ISO files.
4. Review the game count, required space and available space.
5. Click **Import Games**.

If an ISO is too large for one FAT32 file, the app automatically prepares it in the split USBExtreme format that OPL can read. No extra tool or manual splitting is required.

The app copies to temporary `.part` files and renames them only after completion. Cancelling removes incomplete output. Existing games are skipped unless **Replace games that already exist** is selected. If an import fails, the Import page explains the cause and what to do next without asking the user to read a log.

## 3. Manage games

Open **Games & Artwork**. The page rechecks the connected USB and automatically refreshes the library. It shows cover, name, game ID, CD/DVD type and file size. Deleting always opens a confirmation containing the exact game and filename.

## 4. Upload artwork

1. Open **Games & Artwork** and use the Artwork section below the game list.
2. Select a game.
3. Click **Choose Image** and select PNG, JPG, JPEG or WEBP.
4. Review the new artwork preview.
5. Click **Save Artwork**.

Use **Remove Artwork** to delete the selected game's cover after confirmation.

## 5. Prepare OPL folders

Open **USB / Storage** and select **Create / Repair OPL Structure**. Missing folders are created without deleting existing files, so this operation can safely be repeated.

## Formatting warning

**Format Storage permanently deletes all files on the selected physical disk.** The app only permits a verified external USB disk and asks you to type its drive letter. Administrator permission may be required. Never unplug storage during import or formatting.

## Language

The top-right language button shows the language it will switch to. When the interface is Thai it displays **English**; when the interface is English it displays **ไทย**.
