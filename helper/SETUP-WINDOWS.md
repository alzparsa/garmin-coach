# Garmin sync for Coach: Windows setup (about 15 minutes, all free)

You do this once. After that, open Coach in the Claude desktop app on this laptop and tap **Sync Garmin** whenever you want fresh watch data. Your phone shows it everywhere afterwards.

## 1. Install Python (if you don't have it)
1. Go to https://www.python.org/downloads/ and download the latest Python for Windows.
2. Run the installer. On the first screen, **tick "Add python.exe to PATH"**, then click Install Now.
3. Check it: open **Command Prompt** and type `python --version`. You should see `Python 3.x`.
   If the Microsoft Store opens instead, the box in step 2 wasn't ticked. Re-run the installer and choose Modify.

## 2. Put the helper in a folder
1. Unzip this package to a simple folder, for example `C:\CoachHelper`.
   It should contain `garmin_coach_mcp.py`, `test-garmin.bat` and this guide.

## 3. Create your Garmin key
1. On the laptop, sign in at https://connect.garmin.com.
2. Open the **Personal API Key** page and choose **Create Key**. Accept the terms and pick **1 year**.
3. Copy the key. Garmin shows it only once.
4. In `C:\CoachHelper`, create a text file named **`garmin_key.txt`** and paste the key into it, with nothing else. Save it.
   In Notepad, choose "Save as type: All files" so it doesn't become `garmin_key.txt.txt`.

## 4. Test it
Double-click **`test-garmin.bat`**. You should see something like:
```
"message": "Garmin key works."
Last 7 days: 4 activities, 7 days of recovery data
```
If it says PROBLEM, the message tells you what to fix (usually the key file).

## 5. Add the helper to the Claude desktop app
1. Install the Claude desktop app for Windows from https://claude.ai/download and sign in, if you haven't already.
2. In the app, open **Settings → Developer → Edit Config**. This opens a file called `claude_desktop_config.json`.
3. Replace its contents with the text below. If the file already has other `mcpServers`, add just the `garmin-coach` part inside them. Change the path if your folder isn't `C:\CoachHelper`, and keep the double backslashes:
```json
{
  "mcpServers": {
    "garmin-coach": {
      "command": "python",
      "args": ["C:\\CoachHelper\\garmin_coach_mcp.py"]
    }
  }
}
```
4. Save the file, then **quit Claude completely** (right-click its icon by the clock → Quit) and open it again.
5. In Settings → Developer you should now see **garmin-coach** listed as running.

## 6. Sync
1. In the Claude desktop app, open the Coach page: https://claude.ai/artifact/BBbpr6bPnzR8r2JDQsYRYf
2. On **Today**, tap **Sync Garmin**. Claude asks you once to allow the page to use the helper; choose Allow.
3. First time: in **Settings (⚙️) → Garmin**, tap **Sync last year** to bring in your history.

After that, tap **Sync Garmin** whenever you're at the laptop. Each sync picks up from the last one. Synced runs and rides that match a planned session on the same day are marked done automatically.

## If something goes wrong
- **"Sync works from the Claude desktop app…"**: you're in a browser or on the phone, or the helper isn't running. Check step 5.
- **"Garmin rejected the API key"**: the key expired or was deleted. Create a new one (step 3) and replace the text in `garmin_key.txt`. No restart is needed.
- **garmin-coach shows an error in Settings → Developer**: the Python path is wrong. Run `where python` in Command Prompt and put that full path in `"command"`, with double backslashes, e.g. `"C:\\Users\\Parsa\\AppData\\Local\\Programs\\Python\\Python313\\python.exe"`.
- **Some numbers missing after a sync**: Garmin hasn't documented every field name. Settings → Garmin lists any problems; tell Claude in the Garmin project and it can adjust the helper.

## Privacy
Your Garmin key stays in `garmin_key.txt` on this laptop. The helper only reads from Garmin, and Garmin's Personal API can't change anything in your account. Synced data is saved to the Coach page in your Claude account, visible only to you.
